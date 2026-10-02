import csv
from pathlib import Path

from .analysis import Analysis, row_confidence
from .presentation import ASSOCIATION_LABELS, SEVERITY_LABELS, qc_label
from .qc import summarise

ROW_FIELDS = ['reference_ffid', 'target_original_ffid', 'corrected_ffid', 'reference_x', 'reference_y', 'target_x', 'target_y',
              'distance_m', 'association', 'association_code', 'confidence', 'qc_status', 'qc_codes', 'diagnostic']


def _number(value):
    return '' if value is None else value


def export_txt(path: str | Path, analysis: Analysis, input_formats=None) -> None:
    """Write the user-facing QC audit as UTF-8, tab-delimited text.

    The correction decision (association) and the QC observations are separate columns and separate sections: a QC
    warning never changes an association, and only a correction blocker prevents the corrected copy."""
    params, plan = analysis.parameters, analysis.plan
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=ROW_FIELDS, delimiter='\t', lineterminator='\n')
        w.writeheader()
        for row in analysis.rows:
            ref, tgt = row.reference, row.target
            severity = row.qc_severity
            w.writerow({
                'reference_ffid': ref.original_ffid if ref else '',
                'target_original_ffid': tgt.original_ffid if tgt else '',
                'corrected_ffid': row.corrected_ffid or '',
                'reference_x': _number(ref.x if ref else None), 'reference_y': _number(ref.y if ref else None),
                'target_x': _number(tgt.x if tgt else None), 'target_y': _number(tgt.y if tgt else None),
                'distance_m': _number(row.pair.distance_m if row.pair else None),
                'association': ASSOCIATION_LABELS[row.association], 'association_code': row.association,
                'confidence': row_confidence(row, params) or '',
                'qc_status': SEVERITY_LABELS[severity],
                'qc_codes': ','.join(dict.fromkeys(f_.code for f_ in row.findings)),
                'diagnostic': ' | '.join(f_.message for f_ in row.findings[:2]),
            })
        f.write('\n# ShotLogFixer QC\n')
        for key, value in params.as_dict().items():
            f.write(f'# {key}={value:g}\n')
        f.write('# direction=reference_to_target (the recorder is authoritative; the target file is corrected)\n')
        f.write('\n[CORRECTION]\n')
        f.write(f'status={"READY" if plan.safe_to_build and analysis.validation.passed else "BLOCKED"}\n')
        f.write(f'reference_valid_records={plan.reference_valid}\n')
        f.write(f'assigned={plan.assigned}\n')
        f.write(f'target_only_removed={plan.target_only_removed}\n')
        f.write(f'invalid_target_removed={plan.invalid_target_removed}\n')
        f.write(f'corrected_rows={plan.corrected_rows}\n')
        f.write(f'expected_rows={plan.expected_rows}\n')
        for blocker in plan.blockers:
            f.write(f'blocker\t{blocker.code}\t{blocker.message}\n')
        summary = summarise(analysis.findings)
        f.write('\n[QC_SUMMARY]\n')
        for severity in ('SEVERE', 'WARNING', 'INFO'):
            f.write(f'{severity.lower()}={summary["by_severity"].get(severity, 0)}\n')
        for code, count in summary['by_code'].items():
            f.write(f'code\t{code}\t{qc_label(code)}\t{count}\n')
        if input_formats:
            f.write('\n[INPUT_FORMATS]\n')
            for key in ("reference", "target"):
                profile = input_formats.get(key)
                if not profile:
                    continue
                prefix = key + "_"
                structure = profile.get("structure", {})
                mapping = profile.get("column_mapping", {})
                headers = profile.get("header_columns", [])
                f.write(f'{prefix}profile_name={profile.get("name", "")}\n')
                f.write(f'{prefix}profile_id={profile.get("id", "")}\n')
                f.write(f'{prefix}profile_hash={profile.get("profile_hash", "")}\n')
                f.write(f'{prefix}delimiter={profile.get("delimiter", structure.get("delimiter", ""))}\n')
                f.write(f'{prefix}header={profile.get("header", structure.get("header_mode", ""))}\n')
                for role, label in (("FFID", "ffid_column"), ("EIVA_EASTING", "x_column"), ("RECORDER_X", "x_column"),
                                    ("EIVA_NORTHING", "y_column"), ("RECORDER_Y", "y_column")):
                    if role in mapping:
                        index = mapping[role]
                        value = headers[index] if headers and isinstance(index, int) and index < len(headers) else index + 1
                        f.write(f'{prefix}{label}={value}\n')
        f.write('\n[QC_FINDINGS]\n')
        f.write('\t'.join(['scope', 'code', 'severity', 'recorder_ffid', 'recorder_line', 'target_original_ffid', 'target_line', 'message']) + '\n')
        for finding in analysis.findings:
            ref = analysis.reference[finding.reference_row] if finding.reference_row is not None else None
            tgt = analysis.target[finding.target_row] if finding.target_row is not None else None
            f.write('\t'.join(str(v) for v in (
                finding.scope, finding.code, SEVERITY_LABELS[finding.severity],
                ref.original_ffid if ref else '', ref.source_line_number if ref else '',
                tgt.original_ffid if tgt else '', tgt.source_line_number if tgt else '', finding.message)) + '\n')
