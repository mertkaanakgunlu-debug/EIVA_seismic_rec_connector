"""Bounded, deterministic interpretation; never uses filenames or matching science."""
from collections import Counter
from dataclasses import replace
import csv
import hashlib
import json
import math
import re
import statistics

from .format_profiles import FormatProfile, Structure, ROLES, DELIMITERS, builtin_profiles, ProfileStore
from .profile_validation import finite, validate_profile
from .source_reader import sample_source
from .table_parser import parse_table

ALIASES = {
    'FFID': ('ffid', 'shot', 'shot_id', 'shot_no', 'shotno', 'record', 'record_id', 'ping', 'ping_no', 'pingno'),
    'X': ('sou_x', 'source_x', 'x', 'easting', 'east', 'e(spark)', 'spark_e', 'source_easting'),
    'Y': ('sou_y', 'source_y', 'y', 'northing', 'north', 'n(spark)', 'spark_n', 'source_northing'),
}


def normalize_header(value):
    return re.sub(r'[\s_\-]+', '', value.strip().lower())


NORMALIZED_ALIASES = {role: {normalize_header(a) for a in aliases} for role, aliases in ALIASES.items()}


def column_features(values):
    numbers = [n for v in values if (n := finite(v)) is not None]
    deltas = [b-a for a, b in zip(numbers, numbers[1:])]
    n = max(1, len(numbers))
    return {'numeric_ratio': len(numbers)/max(1, len(values)),
            'integer_ratio': sum(v.is_integer() for v in numbers)/n,
            'positive_ratio': sum(v > 0 for v in numbers)/n,
            'unique_ratio': len(set(numbers))/n,
            'monotonic_increase_ratio': sum(d > 0 for d in deltas)/max(1, len(deltas)),
            'monotonic_non_decrease_ratio': sum(d >= 0 for d in deltas)/max(1, len(deltas)),
            'median_delta': statistics.median(deltas) if deltas else None,
            'median_absolute_delta': statistics.median(abs(d) for d in deltas) if deltas else None,
            'min': min(numbers) if numbers else None, 'max': max(numbers) if numbers else None,
            'mean': statistics.mean(numbers) if numbers else None,
            'standard_deviation': statistics.pstdev(numbers) if numbers else None,
            'missing_ratio': sum(not v.strip() for v in values)/max(1, len(values)),
            'decimal_precision_distribution': dict(Counter(len(v.partition('.')[2]) for v in values if finite(v) is not None)),
            'string_pattern_distribution': dict(Counter('numeric' if finite(v) is not None else 'text' for v in values))}


def geometry(rows, x, y):
    points = [(a,b) for row in rows if max(x,y) < len(row)
              and (a := finite(row[x])) is not None and (b := finite(row[y])) is not None]
    steps = [math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(points, points[1:])]
    median = statistics.median(steps) if steps else 0
    return {'finite_pair_ratio': len(points)/max(1,len(rows)), 'median_step_distance': median,
            'step_dispersion': statistics.pstdev(steps) if steps else 0,
            'repeated_coordinate_ratio': sum(d == 0 for d in steps)/max(1,len(steps)),
            'extreme_jump_ratio': sum(d > max(1, median)*100 for d in steps)/max(1,len(steps))}


def score_delimiters(lines):
    scores = []
    for name, separator in DELIMITERS.items():
        rows, failures = [], 0
        for line in lines:
            try:
                cells = line.split() if name == 'whitespace' else next(csv.reader([line], delimiter=separator, strict=True))
                rows.append(cells)
            except csv.Error: failures += 1
        modal, frequency = Counter(len(r) for r in rows).most_common(1)[0] if rows else (0,0)
        stability = frequency/max(1,len(lines))
        empty = sum(not c.strip() for r in rows for c in r)/max(1,sum(len(r) for r in rows))
        variance = statistics.pvariance([len(r) for r in rows]) if rows else 0
        numeric = sum(finite(c) is not None for r in rows for c in r)/max(1,sum(len(r) for r in rows))
        score = (5*stability + 2*numeric + 2 - empty - min(2,variance) - failures/max(1,len(lines))) if modal >= 3 else 0
        if name == 'tab' and score: score += .01
        scores.append({'delimiter': name, 'score': score, 'column_count': modal, 'stability': stability,
                       'empty_ratio': empty, 'variance': variance, 'parse_success': 1-failures/max(1,len(lines)),
                       'numeric_ratio': numeric})
    return sorted(scores, key=lambda s: s['score'], reverse=True)


def header_evidence(first, rest):
    alias_count = sum(any(normalize_header(c) in aliases for aliases in NORMALIZED_ALIASES.values()) for c in first)
    contrast = sum(finite(c) is None and sum(i < len(row) and finite(row[i]) is not None for row in rest)/max(1,len(rest)) > .8
                   for i,c in enumerate(first))
    all_text = all(finite(c) is None for c in first)
    return .98 if alias_count >= 2 else (.8 if all_text and contrast >= 3 and len(set(first)) == len(first) else .1)


def infer_roles(header, rows, input_type):
    mapping, warnings = {}, []
    roles = ROLES[input_type]
    width = max([len(header)] + [len(r) for r in rows], default=0)
    features = [column_features([r[i] if i < len(r) else '' for r in rows]) for i in range(width)]
    for role, kind in zip(roles, ('FFID', 'X', 'Y')):
        hits = [i for i,h in enumerate(header) if normalize_header(h) in NORMALIZED_ALIASES[kind]]
        if len(hits) == 1: mapping[role] = hits[0]
        elif len(hits) > 1: warnings.append(f'Multiple header aliases for {role}')
    if len(mapping) == 3:
        return mapping, .98, features, warnings
    if warnings: return mapping, .2, features, warnings
    if width == 3 and features[0]['integer_ratio'] >= .8 and features[0]['numeric_ratio'] >= .8 and all(f['numeric_ratio'] >= .8 for f in features):
        xmean, ymean = features[1]['mean'], features[2]['mean']
        projected = 100000 <= xmean <= 900000 and 1000000 <= ymean <= 10000000
        reverse = 100000 <= ymean <= 900000 and 1000000 <= xmean <= 10000000
        proposed = dict(zip(roles, (0,2,1) if reverse else (0,1,2)))
        for role, index in proposed.items(): mapping.setdefault(role,index)
        if not projected and not reverse: warnings.append('Coordinate orientation needs review; projected ranges are supporting evidence only')
        return mapping, .92 if projected or reverse else .65, features, warnings
    candidates = [(i,f) for i,f in enumerate(features) if f['numeric_ratio'] >= .8 and i not in mapping.values()]
    if rows and any(finite(row[0]) is None for row in rows if row) and roles[0] not in mapping:
        warnings.append('FFID column is not integer-like')
        return mapping, .1, features, warnings
    if roles[0] not in mapping:
        ids = sorted(candidates, key=lambda item: item[1]['integer_ratio']*.6 + item[1]['unique_ratio']*.2 + item[1]['monotonic_non_decrease_ratio']*.2, reverse=True)
        if ids and ids[0][1]['integer_ratio'] >= .8: mapping[roles[0]] = ids[0][0]
    numeric = [i for i,f in candidates if i not in mapping.values()]
    for role,index in zip([r for r in roles[1:] if r not in mapping], numeric): mapping[role]=index
    warnings.append('Column roles are ambiguous; inspect and confirm the mapping')
    return mapping, .55 if len(mapping)==3 else .2, features, warnings


def fingerprint(profile, header, rows, width):
    types = ['integer' if (f := column_features([r[i] if i<len(r) else '' for r in rows]))['integer_ratio'] >= .8 and f['numeric_ratio'] >= .8 else 'numeric' if f['numeric_ratio'] >= .8 else 'text' for i in range(width)]
    data = [profile.input_type, profile.structure.delimiter, width, profile.structure.header_mode,
            [normalize_header(h) for h in header], types]
    return hashlib.sha256(json.dumps(data, separators=(',',':')).encode()).hexdigest()


def detect_text(text, input_type, encoding='utf-8', user_profiles=()):
    if input_type not in ROLES: raise ValueError('Choose EIVA or RECORDER input type')
    lines = [line for line in text.splitlines(keepends=True) if line.strip() and not line.lstrip().startswith(('#','%','//'))][:70]
    if not lines: raise ValueError('Input file has no meaningful rows')
    scores = score_delimiters(lines)
    selected = scores[0]
    structure = Structure(selected['delimiter'], 'ABSENT', encoding=encoding)
    skip = 0
    from .table_parser import tokenize
    for n,line in enumerate(text.splitlines(keepends=True)):
        if not line.strip() or line.lstrip().startswith(structure.comment_prefixes): continue
        try: cells=tokenize(line,structure)
        except (ValueError,csv.Error): cells=[]
        if len(cells) == selected['column_count']: break
        skip=n+1
    structure = replace(structure,skip_rows=skip)
    temporary = FormatProfile('detected', 'Detected format',input_type,structure,())
    table = parse_table(text, temporary)
    cells = [r.cells for r in table.rows][:70]
    hscore = header_evidence(cells[0],cells[1:]) if cells else 0
    if hscore >= .8:
        structure=replace(structure,header_mode='PRESENT')
        table=parse_table(text,replace(temporary,structure=structure))
    mapping, confidence, features, warnings = infer_roles(table.header,[r.cells for r in table.rows],input_type)
    score=min(selected['stability'],confidence)
    state='High confidence' if score>=.85 else 'Review recommended' if len(mapping)==3 else 'Unresolved'
    name, identity, source = 'Detected format',f'detected-{input_type.lower()}','DETECTED'
    if table.header and confidence>=.9:
        known=builtin_profiles()[0 if input_type=='EIVA' else 1]
        name,identity,source=known.name,known.id,'BUILTIN'
    elif input_type=='RECORDER' and structure.delimiter=='comma' and structure.header_mode=='ABSENT' and mapping==dict(zip(ROLES[input_type],(0,1,2))):
        known=builtin_profiles()[2]; name,identity,source=known.name,known.id,'BUILTIN'
    p=FormatProfile(identity,name,input_type,structure,tuple(sorted(mapping.items())),source,
                    confidence=state,warnings=tuple(warnings),matched_profile_id=identity if source=='BUILTIN' else None)
    fp=fingerprint(p,table.header,[r.cells for r in table.rows],table.column_count)
    p=replace(p,fingerprint=fp)
    for saved in sorted(user_profiles,key=lambda p:p.id):
        if saved.input_type==input_type and saved.fingerprint==fp:
            candidate=replace(saved,structure=replace(saved.structure,encoding=encoding),confidence='High confidence',confirmed=False,matched_profile_id=saved.id)
            if validate_profile(candidate,parse_table(text,candidate))['valid']:
                p=candidate; break
    meta={'confidence_score':score,'delimiter_scores':scores,'header_confidence':hscore,
          'column_features':features,'geometry':geometry([r.cells for r in table.rows],mapping[ROLES[input_type][1]],mapping[ROLES[input_type][2]]) if len(mapping)==3 else {},
          'column_count':table.column_count,'skipped_lines':[{'line':n,'raw':raw} for n,raw in table.skipped_lines]}
    return p,meta


def detect_file(path,input_type):
    groups,encoding,signature=sample_source(path)
    text=''.join(raw for group in groups for _,raw in group)
    p,meta=detect_text(text,input_type,encoding,ProfileStore().load())
    meta['source_signature']=signature
    return p,meta,text


def cross_file_plausibility(points, other):
    """Bounded nearest-coordinate sanity check; does not inspect FFIDs."""
    def score(candidate):
        distances=[min(math.hypot(x-a,y-b) for a,b in other[:70]) for x,y in candidate[:70]] if other and candidate else []
        return statistics.median(distances) if distances else None
    direct=score(points); swapped=score([(y,x) for x,y in points])
    warning = direct is not None and swapped is not None and swapped < direct*.1 and swapped < 100
    agreement=direct is not None and direct<100 and (swapped is None or direct<swapped*.1)
    return {'direct_median_distance':direct,'swapped_median_distance':swapped,
            'state':'swapped orientation warning' if warning else 'supporting agreement' if agreement else 'inconclusive'}
