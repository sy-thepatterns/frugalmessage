"""Correctness checks for the study database contract."""
from experiment.harness import Store


def test_idempotent_completed_ids(tmp_path):
    store = Store(str(tmp_path / 'study.sqlite'), None)
    events = [
        {'event_id': 'a', 'route_key': 'mote:1', 'sequence': 0},
        {'event_id': 'b', 'route_key': 'mote:1', 'sequence': 1},
    ]
    assert store.insert('run-1', events) == 0
    assert store.insert('run-1', events) == 2
    assert [event['event_id'] for event in store.events('run-1')] == ['a', 'b']
    assert store.insert('run-2', events) == 0
    assert len(store.events('run-2')) == 2
