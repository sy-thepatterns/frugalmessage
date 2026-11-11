# Lenovo local validation

Tested on the Lenovo Yoga 7 2-in-1 16IML9, model 83DL, during the 11 November 2026 work session (Singapore date). Machine-generated UTC timestamps are retained unchanged in raw artifacts; verify host clock synchronization before combining with an external meter.

## Implemented and checked

- 25 automated tests passed locally, including HTTP correctness, queue-full/database-failure rejection, persistent connections, power-integrator validation, selection boundaries and controller fallback.
- Windows/Linux CI, requirements-dev.txt, source hashes, runtime metadata, streaming battery samples and a guarded PostgreSQL/battery study runner were added. CI and Docker execution have not been run in this session.
- Timing separates event hold, sender backlog, HTTP attempts, server queue wait and transaction commit. Parent directories for SQLite are created automatically.

## Local experiments

All 27 SQLite replays completed with zero missing/extra/duplicate completed IDs and zero send errors. Eighteen used 300-event subsets to compare fresh and persistent HTTP; nine used all 4,557 Intel steady events, with three randomized repeats per setting and 120-fold acceleration. There were 46,413 successful event completions across these runs.

Fresh-connection diagnostic baseline mean p95 was 1,626.8 ms, compared with 120.0 ms for persistent connections. HTTP-attempt p95 fell from about 29.6 to 8.4 ms, while server queue wait was about 0.16 ms and commit p95 about 6-7 ms. This points to producer transport/sender backlog as the main local bottleneck. The original 62.56-second p95 run is retained separately and is not part of this randomized comparison.

Full-profile results below all use persistent HTTP. Latencies, durations and joules are means of three runs; component percentiles are not additive.

| Setting | Mean p95 (ms) | Worst repeat p95 (ms) | Mean p99 (ms) | Mean duration (s) | Mean battery-DC joules |
| --- | ---: | ---: | ---: | ---: | ---: |
| count=1,wait_ms=0 | 273.5 | 559.9 | 347.9 | 30.01 | 390.9 |
| count=8,wait_ms=100 | 209.6 | 211.7 | 243.7 | 30.12 | 375.2 |
| count=32,wait_ms=500 | 630.1 | 794.2 | 788.8 | 30.45 | 372.9 |

Every full-profile repeat met the illustrative latency, correctness and relative-throughput checks. SQLite remains a functional backend: the selector excludes it from reference PostgreSQL eligibility and does not choose an energy winner.

## Battery measurement quality

The unplugged Lenovo supplied 614 samples over 649.6 seconds. Median poll spacing was 1.054 s and maximum spacing 2.575 s; every run had full coverage below the five-second gap limit. Charging readings and zero ACPI power-meter readings were rejected as consumption evidence.

Across the capture, integrated battery output was 8059.0 J versus 8640.0 J from the reported remaining-capacity drop: a 6.7% relative difference. This is a coarse sensor consistency check, not calibration. 76.5% of adjacent watt readings were unchanged, so one-second polling does not establish independent one-second sensor updates.

The apparent roughly 4-5% mean energy differences between full-profile settings are smaller than that coarse discrepancy. Background applications and this development session were not controlled. No energy-saving claim, statistical winner, capture-overhead correction or adaptive advantage is established. Battery-DC energy includes the whole laptop and is not AC-wall energy.

## Reproduce and inspect

- Raw watt series: `.tmp/lenovo-battery-testing.csv`.
- Original plans/results: `.tmp/lenovo-diagnostics/`, `.tmp/lenovo-persistent-diagnostics/`, `.tmp/lenovo-full-intel-steady/`.
- Matching integrated results: each directory with the `-powered` suffix. Each contains the exact watt-file snapshot and its SHA-256 in run records.
- Per-run and grouped timing/energy CSVs and battery-quality JSON: `.tmp/lenovo-summary/`.
- Full-profile audit: `.tmp/lenovo-full-intel-steady-selection/`.
- Regenerate summaries with `python -m experiment.summarize_diagnostics --runs .tmp/lenovo-diagnostics-powered .tmp/lenovo-persistent-diagnostics-powered .tmp/lenovo-full-intel-steady-powered --watts .tmp/lenovo-battery-testing.csv --output .tmp/lenovo-summary`.

Raw local runs remain ignored; preserve them before cleaning `.tmp`. The capture and local server have been stopped.

## Remaining work and blockers

1. WSL and Docker are absent. `wsl.exe --status` explicitly reports that WSL is not installed. A working Linux Docker engine is required for the 54-run reference matrix; operating-system setup may require administrator access, firmware virtualization configuration and a restart. The runner has been syntax-checked but cannot be integration-tested without that engine.
2. Run `experiment/run_lenovo_study.ps1` after Docker setup, with the Lenovo unplugged and background activity controlled. Inspect sensor update cadence, idle control and capture overhead before interpreting small differences; an external calibrated meter would strengthen validation.
3. Supply a held-out real-service workload with payload, tenant, ordering and batching requirements before claiming deployability. Public aggregate traces cannot establish those semantics.
4. Repeat on the actual second device and measure online monitoring/switching/rollback costs against the best fixed feasible setting. No second device is connected to this session.
