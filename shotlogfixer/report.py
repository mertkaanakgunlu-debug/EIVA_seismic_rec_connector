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
