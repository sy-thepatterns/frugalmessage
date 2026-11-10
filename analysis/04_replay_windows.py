"""Select documented 60-minute replay windows from Intel and Azure traces.

Azure release is a sample of functions, not a service-call trace. The exported
profiles are minute counts, not raw request timestamps. No synthetic timing is
presented as an observation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

import numpy as np
import pandas as pd

from importlib.util import module_from_spec, spec_from_file_location


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def azure_minutes(path: Path) -> pd.DataFrame:
    rows = []
    with tarfile.open(path, 'r:xz') as archive:
        members = sorted((m for m in archive if re.fullmatch(r'invocations_per_function_md\.anon\.d\d\d\.csv', m.name)),
                         key=lambda m: m.name)
        if len(members) != 14:
            raise ValueError(f'Expected 14 Azure invocation days, found {len(members)}')
        for member in members:
            totals = np.zeros(1440, dtype=np.int64)
            functions = 0
            for chunk in pd.read_csv(archive.extractfile(member), chunksize=1000, low_memory=False):
                minutes = chunk.loc[:, [str(i) for i in range(1, 1441)]]
                totals += minutes.fillna(0).to_numpy(dtype=np.int64).sum(axis=0)
                functions += len(chunk)
            day = 'd' + re.search(r'd(\d\d)', member.name).group(1)
            rows.extend({'source': 'azure', 'day': day, 'minute': i, 'count': int(n),
                         'active_sources': functions} for i, n in enumerate(totals))
            print(f'Azure day {day}: {functions:,} functions, {totals.sum():,} invocations', flush=True)
    return pd.DataFrame(rows)


def intel_minutes(path: Path) -> pd.DataFrame:
    spec = spec_from_file_location('intel_workload', Path(__file__).with_name('01_workload_characterization.py'))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = module.load(path)
    accepted = raw.loc[raw.timestamp.notna() & raw.moteid.between(1, 54), ['timestamp', 'moteid']]
    accepted['day'] = accepted.timestamp.dt.date.astype(str)
    accepted['minute'] = accepted.timestamp.dt.hour * 60 + accepted.timestamp.dt.minute
    grouped = accepted.groupby(['day', 'minute']).agg(count=('moteid', 'size'), active_sources=('moteid', 'nunique'))
    days = pd.date_range(accepted.timestamp.min().floor('D'), accepted.timestamp.max().floor('D'))
    index = pd.MultiIndex.from_product([[d.date().isoformat() for d in days], range(1440)], names=['day', 'minute'])
    counts = grouped.reindex(index, fill_value=0).reset_index()
    counts['source'] = 'intel'
    return counts[['source', 'day', 'minute', 'count', 'active_sources']]


def hourly_windows(minutes: pd.DataFrame, source: str) -> pd.DataFrame:
    data = minutes[minutes.source.eq(source)].copy()
    data['hour'] = data.minute // 60
    windows = data.groupby(['day', 'hour']).agg(count=('count', 'sum'),
                                                min_active_minute=('active_sources', 'min'),
                                                mean_active_minute=('active_sources', 'mean'),
                                                peak_minute=('count', 'max')).reset_index()
    windows['peak_to_mean'] = windows.peak_minute / (windows['count'] / 60).clip(lower=1)
    return windows


def choose(windows: pd.DataFrame, source: str) -> dict:
    candidates = windows[windows['count'].gt(0)].copy()
    if source == 'intel':
        # Explicit availability gate: at least 40 motes observed in every minute.
        candidates = candidates[candidates.min_active_minute.ge(40)]
    if len(candidates) < 3:
        raise ValueError(f'Insufficient eligible {source} windows: {len(candidates)}')
    quiet = candidates.loc[candidates['count'].idxmin()]
    median = candidates['count'].median()
    steady_pool = candidates[candidates.peak_to_mean.le(candidates.peak_to_mean.median())]
    steady = steady_pool.iloc[(steady_pool['count'] - median).abs().argsort().iloc[0]]
    burst_pool = candidates[candidates['count'].ge(candidates['count'].median())]
    burst = burst_pool.loc[burst_pool.peak_to_mean.idxmax()]
    return {name: {'day': str(row.day), 'hour': int(row.hour), 'observed_count': int(row['count']),
                   'min_active_minute': int(row.min_active_minute),
                   'mean_active_minute': float(row.mean_active_minute),
                   'peak_to_mean': float(row.peak_to_mean)}
            for name, row in [('quiet', quiet), ('steady', steady), ('bursty', burst)]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intel', type=Path, default=Path('data/raw/intel/data.txt.gz'))
    parser.add_argument('--azure', type=Path, default=Path('data/raw/azure/azurefunctions_dataset2019.tar.xz'))
    parser.add_argument('--output', type=Path, default=Path('analysis/results/replay'))
    parser.add_argument('--reuse-minute-counts', action='store_true',
                        help='Reuse the prior full parse after verifying the same input checksums')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    hashes = {'intel_sha256': sha256(args.intel), 'azure_sha256': sha256(args.azure)}
    cached = args.output / 'minute_counts.csv'
    if args.reuse_minute_counts and cached.exists():
        old = json.loads((args.output / 'manifest.json').read_text(encoding='utf-8'))
        if old['input'] != hashes:
            raise ValueError('Cached minute counts belong to different source archives')
        minutes = pd.read_csv(cached, dtype={'day': 'string'})
        mask = minutes.source.eq('azure')
        minutes.loc[mask, 'day'] = minutes.loc[mask, 'day'].map(
            lambda x: x if str(x).startswith('d') else f'd{int(float(x)):02d}')
    else:
        minutes = pd.concat([intel_minutes(args.intel), azure_minutes(args.azure)], ignore_index=True)
    minutes.to_csv(cached, index=False)
    selections = {source: choose(hourly_windows(minutes, source), source) for source in ('intel', 'azure')}
    profiles = []
    events = []
    intel_raw = None
    for source, kinds in selections.items():
        for kind, choice in kinds.items():
            window = minutes[minutes.source.eq(source) & minutes.day.eq(choice['day']) &
                             minutes.minute.between(choice['hour'] * 60, choice['hour'] * 60 + 59)]
            scale = 1.0 if source == 'intel' else 0.0001
            for _, row in window.iterrows():
                count = int(row['count'])
                replay_count = int(np.floor(count * scale + .5))
                profiles.append({'profile': f'{source}_{kind}', 'source': source,
                                 'source_day': choice['day'], 'source_hour': choice['hour'],
                                 'relative_minute': int(row.minute - choice['hour'] * 60),
                                 'observed_count': count, 'scale': scale,
                                 'replay_count': replay_count})
                if source == 'azure':
                    for ordinal in range(replay_count):
                        offset = int(row.minute - choice['hour'] * 60) * 60_000 + int((ordinal + .5) * 60_000 / replay_count)
                        events.append({'profile': f'{source}_{kind}',
                                       'event_id': f"azure_{choice['day']}_{choice['hour']:02d}_{int(row.minute):04d}_{ordinal:06d}",
                                       'scheduled_offset_ms': offset, 'timestamp_basis': 'uniform_within_minute_constructed',
                                       'route_key': 'synthetic:azure-aggregate'})
            if source == 'intel':
                if intel_raw is None:
                    spec = spec_from_file_location('intel_workload', Path(__file__).with_name('01_workload_characterization.py'))
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                    intel_raw = module.load(args.intel)
                start = pd.Timestamp(choice['day']) + pd.Timedelta(hours=choice['hour'])
                selected = intel_raw.loc[intel_raw.timestamp.between(start, start + pd.Timedelta(hours=1), inclusive='left') &
                                         intel_raw.moteid.between(1, 54), ['timestamp', 'moteid']]
                for index, record in selected.iterrows():
                    events.append({'profile': f'{source}_{kind}', 'event_id': f'intel_row_{index}',
                                   'scheduled_offset_ms': int((record.timestamp - start).total_seconds() * 1000),
                                   'timestamp_basis': 'observed_source_timestamp',
                                   'route_key': f'mote:{int(record.moteid)}'})
    pd.DataFrame(profiles).to_csv(args.output / 'selected_profiles.csv', index=False)
    pd.DataFrame(events).sort_values(['profile', 'scheduled_offset_ms', 'event_id']).to_csv(args.output / 'replay_events.csv', index=False)
    report = {'input': hashes,
              'selection': selections, 'window_minutes': 60,
              'intel_availability_rule': 'at least 40 distinct mote IDs in every minute of an eligible window',
              'azure_active_sources_field': 'number of function rows in that day file; not a per-minute active-function count and not used as an availability gate',
              'quiet_rule': 'minimum positive hourly count among eligible windows',
              'steady_rule': 'nearest median hourly count among windows at or below median peak-to-mean ratio',
              'bursty_rule': 'maximum peak-to-mean ratio among windows at or above median hourly count',
              'profile_scale': {'intel': 1.0, 'azure': 0.0001},
              'azure_event_timing': 'deterministically spaced within each source minute; not observed individual timestamps',
              'intel_event_timing': 'source log timestamps, timezone unspecified',
              'event_ids': 'Intel raw row index or deterministic Azure day/hour/minute/ordinal'}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(selections, indent=2))


if __name__ == '__main__':
    main()
