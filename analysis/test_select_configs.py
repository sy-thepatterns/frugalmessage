import json
import pytest

@pytest.mark.parametrize('mode', ['reference', 'subset', 'sqlite'])
def test_failed_repeat_disqualifies_configuration(tmp_path, mode):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).with_name('05_select_configs.py')
    spec = importlib.util.spec_from_file_location('selection', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = []
    for count, wait in [(1, 0), (8, 100)]:
        for repeat in range(3):
            run_id = f'{count}-{repeat}'
            entries.append({'profile': 'steady', 'max_count': count,
                            'max_wait_ms': wait, 'repeat': repeat, 'run_id': run_id})
            result = {'database': 'sqlite' if mode == 'sqlite' else 'postgres', 'successful_tasks': 10, 'expected_tasks': 10,
                      'lost': int(count == 8 and repeat == 2), 'extra': 0,
                      'duplicate_completions': 0, 'send_errors': [],
                      'p95_latency_ms': 100, 'p99_latency_ms': 200,
                      'throughput_tasks_s': 10, 'application_batches': 10,
                      'request_body_bytes': 100, 'response_body_bytes': 20,
                      'producer_cpu_s': 1, 'energy_j': None,
                      'energy_boundary': 'unmeasured'}
            (tmp_path / f'{run_id}.json').write_text(json.dumps(result))
    plan = {'diagnostic_only': mode == 'subset', 'repeats': 3, 'experimental_limits': {'p95_latency_ms': 2000,
            'p99_latency_ms': 5000, 'lost': 0, 'duplicate_completions': 0,
            'send_errors': 0}, 'runs_in_execution_order': entries}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    summary = module.summarize(plan_path, tmp_path / 'out')
    assert summary[summary.max_count.eq(1)].eligible.item() == (mode == 'reference')
    assert not summary[summary.max_count.eq(8)].eligible.item()
    assert 'pareto' not in summary.columns
