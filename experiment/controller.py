"""Conservative online configuration gate for future system-energy studies.

No energy measurements means no switching away from the baseline. This module
does not claim a measured adaptive benefit; it defines telemetry freshness,
hysteresis, dwell, and immediate rollback behavior for later validation.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Setting:
    max_count: int
    max_wait_ms: int


BASELINE = Setting(1, 0)


def eligible_settings(summary_csv: Path, profile: str) -> list[dict]:
    with summary_csv.open(newline='', encoding='utf-8') as stream:
        rows = [r for r in csv.DictReader(stream) if r['profile'] == profile and r['eligible'].lower() == 'true']
    return rows


class SafeController:
    def __init__(self, min_dwell_s: float = 60, stable_observations: int = 2,
                 max_telemetry_age_s: float = 5, latency_budget_ms: float = 2000):
        self.current = BASELINE
        self.last_switch_s = float('-inf')
        self.pending = None
        self.pending_count = 0
        self.min_dwell_s = min_dwell_s
        self.stable_observations = stable_observations
        self.max_telemetry_age_s = max_telemetry_age_s
        self.latency_budget_ms = latency_budget_ms

    def step(self, now_s: float, telemetry: dict, candidates: list[dict]) -> tuple[Setting, str]:
        unsafe = (telemetry.get('age_s', float('inf')) > self.max_telemetry_age_s or
                  telemetry.get('lost', 1) > 0 or telemetry.get('queue_depth', float('inf')) > 100 or
                  telemetry.get('recent_p95_ms', float('inf')) > self.latency_budget_ms or
                  telemetry.get('monitoring_cost_ms', float('inf')) > 5)
        if unsafe:
            self.current = BASELINE
            self.pending = None
            self.pending_count = 0
            self.last_switch_s = now_s
            return self.current, 'fallback: stale or unsafe telemetry'
        baseline = next((r for r in candidates if int(r['max_count']) == 1 and int(r['max_wait_ms']) == 0), None)
        if baseline is None or not baseline.get('min_joules_per_success'):
            self.current = BASELINE
            self.pending = None
            self.pending_count = 0
            self.last_switch_s = now_s
            return BASELINE, 'fallback: no verified system-energy baseline'
        try:
            baseline_best = float(baseline['min_joules_per_success'])
            rate = float(telemetry['expected_tasks_per_s'])
            horizon_s = float(telemetry['decision_horizon_s'])
            switching_j = float(telemetry['switch_cost_j'])
            feasible = [r for r in candidates
                        if r.get('max_joules_per_success') and
                        float(r['max_p95_ms']) <= .75 * self.latency_budget_ms and
                        (baseline_best - float(r['max_joules_per_success'])) * rate * horizon_s > switching_j]
        except (KeyError, ValueError, TypeError):
            self.current = BASELINE
            self.pending = None
            self.pending_count = 0
            self.last_switch_s = now_s
            return BASELINE, 'fallback: missing switching-cost evidence'
        if not feasible:
            target = BASELINE
        else:
            chosen = min(feasible, key=lambda r: float(r['mean_joules_per_success']))
            target = Setting(int(chosen['max_count']), int(chosen['max_wait_ms']))
        if target == self.current:
            self.pending = None
            self.pending_count = 0
            return self.current, 'hold'
        if target == BASELINE:
            self.current = BASELINE
            self.last_switch_s = now_s
            return self.current, 'fallback: no proven feasible candidate'
        self.pending_count = self.pending_count + 1 if self.pending == target else 1
        self.pending = target
        if self.pending_count < self.stable_observations or now_s - self.last_switch_s < self.min_dwell_s:
            return self.current, 'hold: hysteresis or dwell'
        self.current = target
        self.last_switch_s = now_s
        self.pending = None
        self.pending_count = 0
        return self.current, 'switch: conservative measured benefit'
