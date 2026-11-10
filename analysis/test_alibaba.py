import importlib.util
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


def test_pairing_edges_and_parent_fanout():
    spec = importlib.util.spec_from_file_location('alibaba', Path(__file__).with_name('03_alibaba_dependencies.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = pd.DataFrame([
        {'traceid': 't', 'timestamp': 1, 'rpcid': '0.1', 'um': 'a', 'dm': 'b', 'rpctype': 'rpc', 'rt': 10},
        {'traceid': 't', 'timestamp': 2, 'rpcid': '0.1', 'um': 'a', 'dm': 'b', 'rpctype': 'rpc', 'rt': -4},
        {'traceid': 't', 'timestamp': 3, 'rpcid': '0.1.1', 'um': 'b', 'dm': 'c', 'rpctype': 'http', 'rt': 5},
    ])
    state = {'traces': 0, 'raw_rows': 0, 'paired_rows': 0, 'calls': 0,
             'type_conflicts': 0, 'missing_endpoints': 0, 'missing_parent_calls': 0,
             'max_depth': 0, 'edges': Counter(), 'types': Counter(),
             'latency': defaultdict(list), 'fanout': Counter(),
             'calls_per_trace': [], 'timestamp_min_ms': None, 'timestamp_max_ms': None}
    module.summarize_chunk(rows, state)
    assert (state['traces'], state['raw_rows'], state['calls'], state['paired_rows']) == (1, 3, 2, 1)
    assert state['edges'][('a', 'b', 'rpc')] == 1
    assert state['fanout'][1] == 1
    assert state['latency']['rpc'] == [10.0]
