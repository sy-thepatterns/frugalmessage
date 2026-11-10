"""Predeclare and execute randomized repeated replay runs.

The output intentionally has no energy metric until instrument samples are
provided. Failed runs remain in the plan and are never silently discarded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', required=True)
    parser.add_argument('--url', default='http://app:8765')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--machine', default='cosmos')
    parser.add_argument('--profiles', nargs='+', default=['intel_quiet', 'intel_steady', 'intel_bursty',
                                                         'azure_quiet', 'azure_steady', 'azure_bursty'])
    parser.add_argument('--configs', nargs='+', default=['1:0', '8:100', '32:500'])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--speedup', type=float, default=120)
    parser.add_argument('--seed', type=int, default=20261110)
    args = parser.parse_args()
    if args.repeats < 3 or args.speedup <= 0:
        parser.error('At least three repeats and positive speedup required')
    configs = [tuple(map(int, text.split(':'))) for text in args.configs]
    if (1, 0) not in configs:
        parser.error('Include the no-batching baseline 1:0')
    args.output.mkdir(parents=True, exist_ok=True)
    study_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6]
    plan = [{'profile': profile, 'max_count': count, 'max_wait_ms': wait,
             'repeat': repeat, 'run_id': f'{study_id}-{profile}-{count}-{wait}-r{repeat}'}
            for repeat in range(1, args.repeats + 1)
            for profile in args.profiles for count, wait in configs]
    rng = random.Random(args.seed)
    rng.shuffle(plan)
    manifest = {'study_id': study_id, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'machine': args.machine, 'profiles': args.profiles, 'configs': args.configs,
                'repeats': args.repeats, 'speedup': args.speedup, 'random_seed': args.seed,
                'experimental_limits': {'p95_latency_ms': 2000, 'p99_latency_ms': 5000,
                                        'lost': 0, 'duplicate_completions': 0, 'send_errors': 0},
                'energy_j': 'unmeasured until an instrument with declared boundary is supplied',
                'runs_in_execution_order': plan}
    (args.output / f'{study_id}-plan.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Predeclared {len(plan)} runs in {study_id}', flush=True)
    failures = 0
    for index, item in enumerate(plan, 1):
        command = [sys.executable, '-m', 'experiment.harness', 'replay',
                   '--events', args.events, '--url', args.url, '--output', str(args.output),
                   '--machine', args.machine, '--profile', item['profile'],
                   '--max-count', str(item['max_count']), '--max-wait-ms', str(item['max_wait_ms']),
                   '--speedup', str(args.speedup), '--run-id', item['run_id']]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            failures += 1
            (args.output / f"{item['run_id']}.error.txt").write_text(result.stdout + result.stderr, encoding='utf-8')
        print(f'{index}/{len(plan)} {item["profile"]} {item["max_count"]}:{item["max_wait_ms"]} '
              f'repeat {item["repeat"]}: exit {result.returncode}', flush=True)
    print(f'Completed {len(plan)} planned runs; {failures} failed', flush=True)
    if failures:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
