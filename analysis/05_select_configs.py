"""Summarize complete repeated runs without hiding failures or inventing energy.

Reads one predeclared matrix plan and the matching per-run JSON files. Only
complete, consistent system-energy boundaries may support a Pareto frontier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def summarize(plan_path: Path, output: Path) -> pd.DataFrame:
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    rows = []
    for entry in plan['runs_in_execution_order']:
        path = plan_path.parent / f"{entry['run_id']}.json"
        record = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        rows.append({**entry, 'machine': plan.get('machine', 'unspecified'), 'present': bool(record),
                     'successful_tasks': record.get('successful_tasks', 0),
                     'expected_tasks': record.get('expected_tasks'),
                     'database': record.get('database'),
                     'lost': record.get('lost'), 'extra': record.get('extra'),
                     'duplicate_completions': record.get('duplicate_completions'),
                     'send_errors': len(record.get('send_errors', [])) if record else None,
                     'p95_latency_ms': record.get('p95_latency_ms'),
                     'p99_latency_ms': record.get('p99_latency_ms'),
                     'throughput_tasks_s': record.get('throughput_tasks_s'),
                     'request_body_bytes': record.get('request_body_bytes'),
                     'response_body_bytes': record.get('response_body_bytes'),
                     'application_batches': record.get('application_batches'),
                     'producer_cpu_s': record.get('producer_cpu_s'),
                     'wire_capture_available': record.get('wire_capture_available'),
                     'producer_wire_packets': (record.get('wire_counter_delta') or {}).get('producer_packets'),
                     'producer_wire_frame_bytes': (record.get('wire_counter_delta') or {}).get('producer_frame_bytes'),
                     'database_wire_packets': (record.get('wire_counter_delta') or {}).get('database_packets'),
                     'database_wire_frame_bytes': (record.get('wire_counter_delta') or {}).get('database_frame_bytes'),
                     'energy_j': record.get('energy_j'),
                     'energy_boundary': record.get('energy_boundary')})
    runs = pd.DataFrame(rows)
    limits = plan['experimental_limits']
    runs['valid_run'] = (runs.present & runs.successful_tasks.eq(runs.expected_tasks) &
                         runs.lost.eq(limits['lost']) & runs.extra.eq(0) &
                         runs.duplicate_completions.eq(limits['duplicate_completions']) &
                         runs.send_errors.eq(limits['send_errors']) &
                         runs.p95_latency_ms.le(limits['p95_latency_ms']) &
                         runs.p99_latency_ms.le(limits['p99_latency_ms']))
    baseline = (runs[runs.max_count.eq(1) & runs.max_wait_ms.eq(0)]
                .groupby('profile').throughput_tasks_s.median())
    runs['throughput_floor_met'] = runs.apply(
        lambda r: bool(pd.notna(r.throughput_tasks_s) and
                       r.throughput_tasks_s >= .9 * baseline.loc[r.profile]), axis=1)
    runs['valid_run'] &= runs.throughput_floor_met
    grouped = runs.groupby(['profile', 'max_count', 'max_wait_ms'], as_index=False).agg(
        repeats=('run_id', 'count'), completed_runs=('present', 'sum'),
        all_runs_valid=('valid_run', 'all'),
        mean_p95_ms=('p95_latency_ms', 'mean'), min_p95_ms=('p95_latency_ms', 'min'),
        max_p95_ms=('p95_latency_ms', 'max'), sd_p95_ms=('p95_latency_ms', 'std'),
        mean_p99_ms=('p99_latency_ms', 'mean'),
        mean_throughput=('throughput_tasks_s', 'mean'),
        mean_batches=('application_batches', 'mean'),
        mean_request_body_bytes=('request_body_bytes', 'mean'),
        mean_response_body_bytes=('response_body_bytes', 'mean'),
        mean_producer_cpu_s=('producer_cpu_s', 'mean'),
        mean_producer_wire_packets=('producer_wire_packets', 'mean'),
        mean_database_wire_packets=('database_wire_packets', 'mean'),
        mean_producer_wire_frame_bytes=('producer_wire_frame_bytes', 'mean'),
        mean_database_wire_frame_bytes=('database_wire_frame_bytes', 'mean'))
    grouped['eligible'] = grouped.all_runs_valid & grouped.repeats.ge(plan['repeats']) & grouped.completed_runs.eq(plan['repeats'])
    functional_only = bool(plan.get('diagnostic_only') or runs.database.eq('sqlite').any())
    if functional_only:
        grouped['eligible'] = False
    grouped['mean_app_body_bytes'] = grouped.mean_request_body_bytes + grouped.mean_response_body_bytes
    base = grouped[grouped.max_count.eq(1) & grouped.max_wait_ms.eq(0)].set_index('profile')
    grouped['batch_reduction_vs_baseline_pct'] = grouped.apply(
        lambda r: 100 * (1 - r.mean_batches / base.loc[r.profile, 'mean_batches']), axis=1)
    grouped['app_body_reduction_vs_baseline_pct'] = grouped.apply(
        lambda r: 100 * (1 - r.mean_app_body_bytes / base.loc[r.profile, 'mean_app_body_bytes']), axis=1)
    boundaries = runs.energy_boundary.dropna().unique().tolist()
    system_energy = (not functional_only and len(boundaries) == 1 and boundaries[0] in ('wall_ac', 'battery_dc') and
                     runs.energy_j.notna().all() and runs.energy_j.ge(0).all())
    if system_energy and not runs.empty:
        grouped['energy_boundary'] = boundaries[0]
        runs['joules_per_success'] = runs.energy_j / runs.successful_tasks.replace(0, pd.NA)
        energy = runs.groupby(['profile', 'max_count', 'max_wait_ms'], as_index=False).agg(
            mean_joules_per_success=('joules_per_success', 'mean'),
            min_joules_per_success=('joules_per_success', 'min'),
            max_joules_per_success=('joules_per_success', 'max'),
            sd_joules_per_success=('joules_per_success', 'std'))
        grouped = grouped.merge(energy, on=['profile', 'max_count', 'max_wait_ms'])
        grouped['pareto'] = False
        for _, indices in grouped[grouped.eligible].groupby('profile').groups.items():
            candidates = grouped.loc[list(indices)]
            for i in indices:
                own = grouped.loc[i]
                dominated = ((candidates.mean_joules_per_success.le(own.mean_joules_per_success)) &
                             (candidates.mean_p95_ms.le(own.mean_p95_ms)) &
                             ((candidates.mean_joules_per_success.lt(own.mean_joules_per_success)) |
                              (candidates.mean_p95_ms.lt(own.mean_p95_ms)))).any()
                grouped.loc[i, 'pareto'] = not dominated
        status = f'Measured {boundaries[0]} energy Pareto computed among eligible configurations; do not pool with other boundaries.'
    else:
        status = 'No complete, consistent AC-wall or battery-DC joules for every run; energy Pareto intentionally omitted.'
    if functional_only:
        status = 'Functional SQLite or diagnostic study only; all configurations are ineligible for reference-study selection and no energy winner is selected.'
    output.mkdir(parents=True, exist_ok=True)
    runs.to_csv(output / 'run_audit.csv', index=False)
    grouped.to_csv(output / 'configuration_summary.csv', index=False)
    (output / 'selection_status.md').write_text(
        f'# Study selection status\n\nPlan: `{plan_path.name}`. {status}\n\n'
        f'Predeclared limits: p95 ≤ {limits["p95_latency_ms"]} ms, '
        f'p99 ≤ {limits["p99_latency_ms"]} ms, no missing/extra/duplicate completions or send errors, '
        'throughput at least 90% of that profile’s baseline median. Every repeat must pass.\n\n'
        'Application body bytes exclude transport headers and acknowledgements at lower layers. '
        'Optional wire counters include TCP Ethernet frame traffic and small control-request overhead. '
        'CPU time is producer process time only. Run-level records and observed min/max/SD expose variation; '
        'three repeats are too few for a narrow confidence interval. Background server activity can confound comparisons.\n',
        encoding='utf-8')
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('analysis/results/selection'))
    args = parser.parse_args()
    summary = summarize(args.plan, args.output)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
