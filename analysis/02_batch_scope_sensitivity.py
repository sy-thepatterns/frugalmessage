"""Recompute batching sensitivity with each Intel sensor as a separate stream.

This is a hypothetical application-send model, not network or energy data.
Run after downloading data/raw/intel/data.txt.gz.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workload', root / 'analysis/01_workload_characterization.py')
workload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workload)
raw = workload.load(root / 'data/raw/intel/data.txt.gz')
events = raw.loc[raw.timestamp.notna() & raw.moteid.between(1, 54), ['timestamp', 'moteid']].sort_values('timestamp', kind='stable')
daily = events.groupby(events.timestamp.dt.floor('D')).agg(readings=('moteid', 'size'), active_motes=('moteid', 'nunique'))
gaps = events.groupby('moteid').timestamp.diff().dt.total_seconds().dropna()
groups = [g.timestamp.astype('int64').to_numpy() / 1e9 for _, g in events.groupby('moteid')]
scenarios = []
for count in (1, 8, 32):
    for wait in (1, 10, 60):
        batches = 0
        holds = []
        for times in groups:
            n, h = workload.model_batches(times, count, wait)
            batches += n
            holds.append(h)
        holds = np.concatenate(holds)
        scenarios.append({'max_count': count, 'max_wait_s': wait, 'per_mote_batches': batches,
                          'per_mote_reduction_pct': 100 * (1 - batches / len(events)),
                          'per_mote_p95_hold_s': float(np.quantile(holds, .95)),
                          'per_mote_p99_hold_s': float(np.quantile(holds, .99))})
out = {'rows': len(events), 'unique_timestamps': int(events.timestamp.nunique()),
       'same_timestamp_fraction': float(1 - events.timestamp.nunique() / len(events)),
       'gap_p99_s': float(gaps.quantile(.99)), 'gap_max_s': float(gaps.max()),
       'daily_lowest': daily.sort_values('readings').head(6).reset_index().astype(str).to_dict('records'),
       'daily_active_motes_min': int(daily.active_motes.min()),
       'daily_active_motes_max': int(daily.active_motes.max()),
       'scenarios': scenarios}
(root / 'analysis/results/extended_metrics.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
print(json.dumps(out, indent=2))
