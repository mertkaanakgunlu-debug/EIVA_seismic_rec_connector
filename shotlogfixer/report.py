import csv
from pathlib import Path
from .models import MatchResult

def export_csv(path: str | Path, results: list[MatchResult]) -> None:
    fields = ['eiva_ffid','eiva_easting','eiva_northing','recorder_ffid','recorder_x','recorder_y','distance_m','status','diagnostic']
    with Path(path).open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in results:
            e, rec = r.eiva_record, r.recorder_record
            w.writerow({'eiva_ffid': e.original_ffid if e else '', 'eiva_easting': e.easting_spark if e else '', 'eiva_northing': e.northing_spark if e else '', 'recorder_ffid': rec.ffid if rec else '', 'recorder_x': rec.source_x if rec else '', 'recorder_y': rec.source_y if rec else '', 'distance_m': r.distance_m if r.distance_m is not None else '', 'status': r.status, 'diagnostic': r.diagnostic})


def export_txt(path: str | Path, results: list[MatchResult], parameters=None, recorder_gaps=None) -> None:
    """Write the user-facing QC audit as UTF-8, tab-delimited text."""
    fields = ['eiva_ffid', 'eiva_easting', 'eiva_northing', 'recorder_ffid', 'recorder_x', 'recorder_y', 'distance_m', 'status', 'gap_event_id', 'diagnostic']
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t', lineterminator='\n')
        w.writeheader()
        for r in results:
            e, rec = r.eiva_record, r.recorder_record
            w.writerow({'eiva_ffid': e.original_ffid if e else '', 'eiva_easting': e.easting_spark if e else '', 'eiva_northing': e.northing_spark if e else '', 'recorder_ffid': rec.ffid if rec else '', 'recorder_x': rec.source_x if rec else '', 'recorder_y': rec.source_y if rec else '', 'distance_m': r.distance_m if r.distance_m is not None else '', 'status': r.status, 'gap_event_id': ','.join(r.gap_event_ids), 'diagnostic': r.diagnostic})
        if parameters is not None:
            f.write('\n# ShotLogFixer QC\n')
            f.write(f'# shot_interval_m={parameters.shot_interval_m:g}\n')
            f.write(f'# match_tolerance_m={parameters.match_tolerance_m:g}\n')
            f.write(f'# recorder_gap_threshold_m={parameters.recorder_gap_threshold_m:g}\n')
            f.write(f'# recorder_gap_events={len(recorder_gaps or [])}\n')
            f.write(f'# unexplained_missing_positions={sum(g.unexplained_missing_positions for g in (recorder_gaps or []))}\n')
        if parameters is not None and recorder_gaps:
            f.write('\n[RECORDER_GAPS]\n')
            gap_fields = ['event_id', 'from_ffid', 'to_ffid', 'distance_m', 'gap_span_steps', 'estimated_missing_positions', 'explicit_no_shot_count', 'unexplained_missing_positions', 'eiva_only_count', 'classification', 'diagnostic']
            f.write('\t'.join(gap_fields) + '\n')
            for gap in recorder_gaps:
                f.write('\t'.join(str(value) for value in (gap.event_id, gap.left_recorder_ffid, gap.right_recorder_ffid, gap.distance_m, gap.gap_span_steps, gap.estimated_missing_positions, gap.explicit_no_shot_count, gap.unexplained_missing_positions, len(gap.eiva_only_indices), gap.classification, gap.diagnostic)) + '\n')
