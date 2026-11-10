"""Analyze one or more explicitly named Alibaba 2021 MSCallGraph shards.

Reads tar.gz members in chunks; never treats the 0.5% call-graph sample as a
complete population. Run with --input data/raw/alibaba/MSCallGraph_0.tar.gz.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tarfile

import numpy as np
import pandas as pd

COLS = ['traceid', 'timestamp', 'rpcid', 'um', 'rpctype', 'dm', 'interface', 'rt']


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def summarize_chunk(frame: pd.DataFrame, state: dict) -> None:
    if frame.empty:
        return
    state['traces'] += frame.traceid.nunique()
    state['raw_rows'] += len(frame)
    frame = frame.copy()
    timestamps = pd.to_numeric(frame.timestamp, errors='coerce').dropna()
    if len(timestamps):
        low, high = int(timestamps.min()), int(timestamps.max())
        state['timestamp_min_ms'] = low if state['timestamp_min_ms'] is None else min(state['timestamp_min_ms'], low)
        state['timestamp_max_ms'] = high if state['timestamp_max_ms'] is None else max(state['timestamp_max_ms'], high)
    frame = frame[frame.rpcid.notna() & frame.rpcid.ne('')]
    if frame.empty:
        return
    key = ['traceid', 'rpcid']
    frame['rpctype'] = frame.rpctype.fillna('unknown').str.lower()
    frame['rt'] = pd.to_numeric(frame.rt, errors='coerce')
    state['type_conflicts'] += int((frame.groupby(key).rpctype.nunique() > 1).sum())
    valid_endpoint = (frame.um.notna() & frame.dm.notna() &
                      ~frame.um.isin(['', '(?)', 'NAN']) &
                      ~frame.dm.isin(['', '(?)', 'NAN']))
    frame['valid_endpoint'] = valid_endpoint
    logical = frame.sort_values('valid_endpoint', ascending=False, kind='stable').drop_duplicates(key).copy()
    state['calls'] += len(logical)
    state['paired_rows'] += len(frame) - len(logical)
    state['missing_endpoints'] += int((~logical.valid_endpoint).sum())
    state['types'].update(logical.rpctype.value_counts().to_dict())
    edges = logical.loc[logical.valid_endpoint].groupby(['um', 'dm', 'rpctype']).size()
    state['edges'].update(edges.to_dict())
    client = frame.loc[frame.rt.ge(0), key + ['rt']].groupby(key, sort=False).rt.max().reset_index()
    client = client.merge(logical[key + ['rpctype']], on=key, how='left')
    for kind, values in client.groupby('rpctype').rt:
        state['latency'][kind].extend(values.to_numpy(dtype=float))
    state['max_depth'] = max(state['max_depth'], int(logical.rpcid.str.count(r'\.').max()))
    counts = logical.groupby('traceid').size()
    state['calls_per_trace'].extend(counts.to_numpy().tolist())
    logical['parent'] = logical.rpcid.str.rsplit('.', n=1).str[0]
    ids = pd.MultiIndex.from_frame(logical[key])
    parent_ids = pd.MultiIndex.from_frame(logical[['traceid', 'parent']])
    has_parent = parent_ids.isin(ids)
    has_prefix = logical.parent.ne(logical.rpcid) & logical.parent.ne('')
    state['missing_parent_calls'] += int((has_prefix & ~has_parent).sum())
    fanout = logical.loc[has_prefix & has_parent].groupby(['traceid', 'parent']).size().value_counts()
    state['fanout'].update(fanout.to_dict())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, default=Path('analysis/results/alibaba'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {'traces': 0, 'raw_rows': 0, 'paired_rows': 0, 'calls': 0,
             'empty_rpc_traces': 0, 'type_conflicts': 0, 'missing_endpoints': 0,
             'missing_parent_calls': 0, 'max_depth': 0, 'edges': Counter(),
             'types': Counter(), 'latency': defaultdict(list), 'fanout': Counter(),
             'calls_per_trace': [], 'timestamp_min_ms': None, 'timestamp_max_ms': None}
    provenance = []
    for path in args.input:
        provenance.append({'file': path.name, 'sha256': sha256(path), 'compressed_bytes': path.stat().st_size})
        with tarfile.open(path, 'r:gz') as archive:
            members = [m for m in archive if m.isfile() and m.name.endswith('.csv')]
            if len(members) != 1:
                raise ValueError(f'Expected one CSV in {path}, found {len(members)}')
            source = archive.extractfile(members[0])
            carry = pd.DataFrame()
            chunks = 0
            for chunk in pd.read_csv(source, usecols=COLS, chunksize=100_000,
                                     dtype={'traceid': 'string', 'rpcid': 'string',
                                            'um': 'string', 'dm': 'string',
                                            'rpctype': 'string', 'interface': 'string'},
                                     low_memory=False):
                chunk = pd.concat([carry, chunk], ignore_index=True)
                last = chunk.traceid.iloc[-1]
                carry = chunk[chunk.traceid.eq(last).fillna(False)].copy()
                complete = chunk[~chunk.traceid.eq(last).fillna(False)]
                summarize_chunk(complete, state)
                chunks += 1
                if chunks % 10 == 0:
                    print(f'{path.name}: {chunks * 100_000:,} input rows scanned', flush=True)
            summarize_chunk(carry, state)
    edge_rows = [{'um': um, 'dm': dm, 'rpctype': kind, 'sampled_calls': n}
                 for (um, dm, kind), n in state['edges'].most_common()]
    pd.DataFrame(edge_rows).head(100).to_csv(args.output / 'top_edges.csv', index=False)
    total_edge_calls = sum(state['edges'].values())
    top_1pct = max(1, int(np.ceil(len(edge_rows) * .01))) if edge_rows else 0
    latency = {kind: {'count': len(values), 'p50_ms': float(np.quantile(values, .5)),
                      'p95_ms': float(np.quantile(values, .95)),
                      'p99_ms': float(np.quantile(values, .99))}
               for kind, values in state['latency'].items() if values}
    counts = state['calls_per_trace']
    output = {'source': 'Alibaba cluster-trace-microservices-v2021',
              'scope': 'Only explicitly listed MSCallGraph shards; 0.5% call-graph sampling in published collection',
              'input': provenance, 'raw_rows': state['raw_rows'],
              'timestamp_min_ms': state['timestamp_min_ms'],
              'timestamp_max_ms': state['timestamp_max_ms'],
              'sampled_call_graphs': state['traces'], 'logical_calls': state['calls'],
              'additional_paired_rows': state['paired_rows'],
              'type_conflicts': state['type_conflicts'],
              'calls_with_missing_endpoint': state['missing_endpoints'],
              'calls_without_observed_parent': state['missing_parent_calls'],
              'max_rpcid_depth': state['max_depth'],
              'calls_per_trace_p50': float(np.quantile(counts, .5)) if counts else None,
              'calls_per_trace_p95': float(np.quantile(counts, .95)) if counts else None,
              'fanout': dict(sorted(state['fanout'].items())),
              'rpc_types': dict(state['types']), 'client_rt_by_type': latency,
              'distinct_edges': len(edge_rows),
              'top_1pct_edge_call_share': (sum(x['sampled_calls'] for x in edge_rows[:top_1pct]) / total_edge_calls
                                           if total_edge_calls else None)}
    (args.output / 'metrics.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: output[k] for k in ('raw_rows', 'sampled_call_graphs', 'logical_calls',
                                             'distinct_edges', 'top_1pct_edge_call_share')}, indent=2))


if __name__ == '__main__':
    main()
