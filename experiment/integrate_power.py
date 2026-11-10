"""Attach timestamped system power data to a completed run matrix.

CSV columns: timestamp_utc,power_w. Samples must cover every run and have no
gap longer than --max-gap-s. AC input and battery output remain distinct
boundaries; CPU package energy cannot be passed as either one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd


def integrate(samples: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, max_gap_s: float) -> float:
    if end <= start:
        raise ValueError('Run end must follow start')
    ns = samples.timestamp_utc.astype('int64').to_numpy()
    watts = samples.power_w.to_numpy(dtype=float)
    a, b = start.value, end.value
    if a < ns[0] or b > ns[-1]:
        raise ValueError('Watt samples do not cover the full run interval')
    inner = ns[(ns > a) & (ns < b)]
    points = np.concatenate(([a], inner, [b]))
    if np.diff(points).max() / 1e9 > max_gap_s:
        raise ValueError('Power sampling gap exceeds declared maximum')
    interpolated = np.interp(points.astype(float), ns.astype(float), watts)
    return float(np.trapezoid(interpolated, points.astype(float) / 1e9))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--watts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--meter-id', required=True)
    parser.add_argument('--boundary', choices=['wall_ac', 'battery_dc'], default='wall_ac')
    parser.add_argument('--max-gap-s', type=float, default=5)
    parser.add_argument('--idle-watts', type=float)
    args = parser.parse_args()
    samples = pd.read_csv(args.watts)
    if not {'timestamp_utc', 'power_w'}.issubset(samples.columns):
        raise ValueError('Watt CSV requires timestamp_utc,power_w')
    samples['timestamp_utc'] = pd.to_datetime(samples.timestamp_utc, utc=True)
    samples['power_w'] = pd.to_numeric(samples.power_w, errors='raise')
    if 'boundary' in samples.columns and not samples.boundary.eq(args.boundary).all():
        raise ValueError('CSV boundary does not match --boundary')
    samples = samples.sort_values('timestamp_utc')
    if len(samples) < 2 or samples.timestamp_utc.duplicated().any() or samples.power_w.lt(0).any():
        raise ValueError('Need unique increasing timestamps and nonnegative watts')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.plan, args.output / args.plan.name)
    failures = []
    for item in plan['runs_in_execution_order']:
        name = f"{item['run_id']}.json"
        path = args.plan.parent / name
        if not path.exists():
            failures.append(f'{name}: run file missing')
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        try:
            start = pd.Timestamp(record['started_utc'])
            end = pd.Timestamp(record['ended_utc'])
            record['energy_j'] = integrate(samples, start, end, args.max_gap_s)
            record['energy_boundary'] = args.boundary
            record['meter_id'] = args.meter_id
            record['power_sample_file'] = args.watts.name
            if args.idle_watts is not None:
                record['incremental_j'] = record['energy_j'] - args.idle_watts * (end - start).total_seconds()
                record['idle_watts'] = args.idle_watts
            (args.output / name).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        except (ValueError, KeyError) as exc:
            failures.append(f'{name}: {exc}')
    (args.output / 'power_integration_status.json').write_text(
        json.dumps({'meter_id': args.meter_id, 'boundary': args.boundary,
                    'source': str(args.watts), 'failures': failures}, indent=2) + '\n',
        encoding='utf-8')
    print(f'Integrated {len(plan["runs_in_execution_order"]) - len(failures)} runs; {len(failures)} gaps/errors')
    if failures:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
