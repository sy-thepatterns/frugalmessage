"""Describe local measurements without selecting a reference-study energy winner."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from experiment.integrate_power import integrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', type=Path, required=True)
    parser.add_argument('--watts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    samples = pd.read_csv(args.watts)
    samples['timestamp_utc'] = pd.to_datetime(samples.timestamp_utc, utc=True)
    gaps = samples.timestamp_utc.diff().dt.total_seconds().dropna()
    rows = []
    for directory in args.runs:
        for path in directory.glob('*.json'):
            run = json.loads(path.read_text())
            if 'configuration' not in run:
                continue
            row = {key: run.get(key) for key in (
                'run_id', 'configuration', 'database', 'expected_tasks', 'successful_tasks',
                'lost', 'extra', 'duplicate_completions', 'energy_j', 'elapsed_s',
                'p95_latency_ms', 'p99_latency_ms', 'application_batches', 'max_outbound_batches')}
            row.update(study=directory.name, transport=run.get('transport', 'fresh'),
                       send_errors=len(run['send_errors']))
            for key, values in run['timing_ms'].items():
                row[key + '_p95'] = values['p95']
            rows.append(row)
    runs = pd.DataFrame(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    runs.to_csv(args.output / 'diagnostic_runs.csv', index=False)
    summary = runs.groupby(['study', 'transport', 'configuration'], as_index=False).agg(
        repeats=('run_id', 'count'), total_events=('successful_tasks', 'sum'),
        lost=('lost', 'sum'), extra=('extra', 'sum'), duplicates=('duplicate_completions', 'sum'),
        send_errors=('send_errors', 'sum'), mean_p95_ms=('p95_latency_ms', 'mean'),
        worst_p95_ms=('p95_latency_ms', 'max'), mean_p99_ms=('p99_latency_ms', 'mean'),
        mean_energy_j=('energy_j', 'mean'), mean_elapsed_s=('elapsed_s', 'mean'),
        mean_batches=('application_batches', 'mean'), mean_backlog_p95_ms=('sender_backlog_ms_p95', 'mean'),
        mean_http_p95_ms=('http_attempt_ms_p95', 'mean'),
        mean_commit_p95_ms=('database_commit_ms_p95', 'mean'))
    summary.to_csv(args.output / 'diagnostic_summary.csv', index=False)
    interval_j = integrate(samples, samples.timestamp_utc.iloc[0], samples.timestamp_utc.iloc[-1], 5)
    capacity_drop_j = float(samples.remaining_capacity.iloc[0] - samples.remaining_capacity.iloc[-1]) * 3.6
    qc = dict(samples=len(samples), duration_s=(samples.timestamp_utc.iloc[-1] - samples.timestamp_utc.iloc[0]).total_seconds(),
              median_poll_gap_s=float(gaps.median()), max_poll_gap_s=float(gaps.max()),
              distinct_watt_values=int(samples.power_w.nunique()),
              unchanged_adjacent_fraction=float(samples.power_w.diff().eq(0).iloc[1:].mean()),
              integrated_capture_j=interval_j, reported_capacity_drop_j=capacity_drop_j,
              capacity_comparison_relative_difference=(abs(interval_j-capacity_drop_j)/capacity_drop_j if capacity_drop_j > 0 else None),
              boundary='battery_dc', calibration='Capacity comparison is a coarse consistency check, not external calibration.',
              limitations='SQLite functional runs; short runs and uncontrolled background activity; no energy winner or adaptive advantage established.')
    (args.output / 'battery_quality.json').write_text(json.dumps(qc, indent=2) + '\n')
    print(summary.round(3).to_string(index=False))
    print(json.dumps(qc, indent=2))


if __name__ == '__main__':
    main()
