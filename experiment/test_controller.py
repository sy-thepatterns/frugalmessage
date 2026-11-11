from experiment.controller import BASELINE, SafeController, Setting


def test_no_wall_energy_means_baseline():
    controller = SafeController()
    telemetry = {'age_s': 0, 'lost': 0, 'queue_depth': 0, 'recent_p95_ms': 100,
                 'monitoring_cost_ms': 1}
    setting, reason = controller.step(0, telemetry, [])
    assert setting == BASELINE and 'no verified' in reason


def test_hysteresis_then_immediate_rollback():
    controller = SafeController(min_dwell_s=0, stable_observations=2)
    candidates = [
        {'max_count': '1', 'max_wait_ms': '0', 'min_joules_per_success': '10',
         'max_joules_per_success': '10', 'mean_joules_per_success': '10', 'max_p95_ms': '100'},
        {'max_count': '8', 'max_wait_ms': '100', 'min_joules_per_success': '7',
         'max_joules_per_success': '8', 'mean_joules_per_success': '7.5', 'max_p95_ms': '500'}]
    good = {'age_s': 0, 'lost': 0, 'queue_depth': 0, 'recent_p95_ms': 100,
            'monitoring_cost_ms': 1, 'expected_tasks_per_s': 1,
            'decision_horizon_s': 60, 'switch_cost_j': 1}
    assert controller.step(0, good, candidates)[0] == BASELINE
    assert controller.step(1, good, candidates)[0] == Setting(8, 100)
    assert controller.step(2, {**good, 'lost': 1}, candidates)[0] == BASELINE


def test_lost_energy_evidence_clears_active_setting():
    controller = SafeController()
    controller.current = Setting(8, 100)
    controller.pending = Setting(32, 500)
    controller.pending_count = 1
    good = {'age_s': 0, 'lost': 0, 'queue_depth': 0, 'recent_p95_ms': 100,
            'monitoring_cost_ms': 1}
    assert controller.step(10, good, [])[0] == BASELINE
    assert controller.current == BASELINE
    assert controller.pending is None
    assert controller.pending_count == 0
