# Controlled service study

This study uses an isolated HTTP producer → bounded in-process queue → one worker → PostgreSQL path. A SQLite backend supports quick functional checks. The [contract](contract.json) fixes compatibility, acknowledgement, idempotency, and illustrative research limits before selection.

## Inputs and replay

Run `python analysis/04_replay_windows.py` after downloading the Intel and Azure archives. The resulting `analysis/results/replay/replay_events.csv` has six one-hour profiles. Intel event IDs and offsets come from original rows; Azure publishes only per-minute invocation counts, so those counts are scaled by 0.0001 and replay events are uniformly spaced *within each minute*. This spacing is constructed, not observed. The `--speedup 120` matrix compresses one source hour into about 30 wall seconds and therefore represents a stress replay, not the original arrival rate.

The Intel compatibility key is the sensor ID (`mote:<id>`). Azure has only an aggregate synthetic route because this public trace lacks inter-service paths. The Alibaba shard characterizes real routes observationally, but its anonymous service IDs do not map onto these replay events. The testbed uses fixed tenant `study`, schema `v1`, and one destination. It accepts a batch only when all events share route, tenant, and schema.

## Run locally

From the repository root, install `requirements.txt`, then:

```sh
python -m experiment.harness serve --sqlite .tmp/study.sqlite --port 8765
python -m experiment.harness replay --profile intel_steady --max-count 8 --max-wait-ms 100 --speedup 120
```

The server command stays running in the first terminal. SQLite measurements verify logic and portability, not PostgreSQL performance.

## Run with PostgreSQL on Windows, Linux, or macOS

With Docker Compose and Linux containers installed, from the repository root:

```sh
docker compose -f experiment/compose.yaml up -d --build db app
docker compose -f experiment/compose.yaml run --rm --entrypoint python runner -m experiment.matrix --events /data/replay/replay_events.csv --output /data/runs --machine YOUR_MACHINE --speedup 120 --repeats 3
```

The pinned Python and PostgreSQL image digests include x86-64 and ARM64 variants. On the Yoga, use Docker Desktop with Linux containers; the same commands work in PowerShell. The Compose project has its own network and database container; the app publishes only on loopback port 8765. The study database uses a documented local-only credential and should not be attached to a shared network. The runner writes a randomized, predeclared plan and all per-run JSON files into `analysis/results/experimental_runs/`. Preserve failed run artifacts; selection must account for them.

When finished, run `docker compose -f experiment/compose.yaml down` to stop these study containers. This command does not target other Compose projects. The study database container has no persistent volume; export any needed results first.

## What is measured

The producer records latency from event emission to the HTTP acknowledgment, which follows database commit. It verifies the exact completed ID set from PostgreSQL, and records missing/extra/duplicate completions, retry attempts, schedule lag, duration, throughput, producer CPU time, application batches, and JSON request/response body bytes. The body bytes exclude HTTP/TCP headers and lower-layer acknowledgements. On Linux containers, the runner reads its `eth0` transmit and receive byte/packet counters. The app also attempts passive capture of TCP Ethernet frames on its isolated `eth0`, classifying the producer edge by port 8765 and the database edge by port 5432. Capture availability is explicit in each run. Counters include small control-request overhead and may include unrelated traffic if the study network is reused; capture overhead needs its own ablation before energy claims.

All configurations within a profile use the same replay file. The three default configurations are no batching (`1:0`), `8:100 ms`, and `32:500 ms`. Their execution order is randomized with a recorded seed. Every repeat must satisfy p95 ≤ 2 s, p99 ≤ 5 s, zero missing/extra/duplicate completed IDs, zero send errors, and throughput at least 90% of the same-profile baseline median. These are illustrative research limits, not a production SLA.

## Power and energy

`energy_j` remains null until timestamped system-power samples supply a CSV with `timestamp_utc,power_w`, covering every run. For the preferred Lenovo Yoga study, use a plug-in AC meter with timestamped export around the laptop's charger. Keep the battery full and stable so charging does not dominate the reading, and fix screen brightness, power mode, peripherals, and background applications across runs. The measured boundary includes the adapter and its losses. A USB-C inline PD meter measures a different DC boundary and is also usable if documented consistently. A 65 W adapter is listed for Lenovo's Yoga 7i 16-inch Gen 9 family; check the exact machine type and supplied charger before choosing a meter.

On Windows, `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\experiment\windows_power_probe.ps1` runs the repository's read-only model, battery, and ACPI power-counter check without changing the machine-wide script policy. It may report no usable counters; that does not prevent external watt measurement. If the Yoga reports a plausible discharge rate, `experiment/windows_battery_sample.ps1` can collect a separate **battery-DC** power series while unplugged. This measures battery output across the laptop, not AC input; check cadence and compare integrated energy with the drop in reported remaining capacity over a long run. Intel PCM/RAPL may show CPU package energy after its driver and processor support are checked, but it is not whole-laptop system energy. The current checkout runs on the Lenovo 83DL and exposes battery discharge telemetry while unplugged; local diagnostic capture is documented below.

With watt samples available, use:

```sh
python -m experiment.integrate_power --plan analysis/results/experimental_runs/STUDY-plan.json --watts meter.csv --meter-id METER_ID --boundary wall_ac --output analysis/results/powered_runs
python analysis/05_select_configs.py --plan analysis/results/powered_runs/STUDY-plan.json
```

For an unplugged battery run, use `--boundary battery_dc` with the battery sample CSV. Never pool battery-DC with AC-wall results. The integration checks sample coverage and gaps, interpolates run boundaries, and integrates watts over time. Sample at about 1 Hz for the 30-second stress runs; otherwise lengthen runs and document the sensor's cadence. Measure an idle interval separately and pass `--idle-watts` only if it represents the same hardware state. Intel RAPL reports CPU package energy, and macOS `powermetrics` has a narrower subsystem boundary; neither can fill the system-energy field.

## Selection and limitations

`python analysis/05_select_configs.py --plan analysis/results/experimental_runs/STUDY-plan.json` reports every planned run and configuration eligibility. It computes a joules/latency Pareto frontier only when all planned runs contain one consistent AC-wall or battery-DC energy boundary. No energy winner is selected from body bytes or CPU time.

The ZOTAC study was stopped at the owner's request before its matrix completed. Its partial runs are retained only in the ignored `.tmp` directory for audit and are not used for selection. The Yoga is the preferred primary target; the M1 MacBook Air and gaming PC can provide separate hardware checks. Compare each machine's frontier separately. The [safe controller](controller.py) is an initial adaptation gate: it refuses to switch without complete system-energy evidence, requires a conservative run-range benefit and a switching-cost estimate, waits for two stable observations and a dwell period, and falls back immediately on stale telemetry, loss, queue buildup, or latency breach. Its actual switching and monitoring cost must be measured on held-out windows before it is described as an optimiser.

## Latency diagnosis

Replay records event-weighted batch hold and batch-weighted sender backlog,
HTTP-attempt, server-queue, and commit timing in `timing_ms`. These are component
distributions; their percentiles must not be added together. `max_outbound_batches`
exposes sender backlog. Additional response timing fields add instrumentation
bytes and overhead; compare runs from the same source version.

`--transport fresh` preserves the original urllib behavior. `--transport persistent`
uses one direct HTTP connection and reconnects after failures. Transport choice is
recorded in results and matrix plans; compare batching settings within one transport.
Persistent mode is for direct study endpoints and does not use HTTP proxy settings.
The initial Lenovo diagnosis found much lower sender backlog with connection reuse.

Use `python -m experiment.matrix --events analysis/results/replay/replay_events.csv
--url http://127.0.0.1:8765 --output .tmp/diagnostic --machine YOUR_MACHINE
--profiles intel_steady --limit 300 --repeats 3 --transport persistent` as one command
for a short diagnostic. A subset plan is explicitly diagnostic. SQLite runs and
subset plans are excluded from reference-study eligibility and energy selection.

## Lenovo study workflow

Install Docker Desktop with its Linux container engine and create the Python
virtual environment described in the root README. Docker must be running and
`docker info --format '{{.OSType}}'` must report `linux`. Build and download images
before a controlled measurement where possible. This session did not have Docker
installed, so the PostgreSQL matrix could not be executed here.

With a usable discharge-rate sensor and enough battery charge, unplug the Lenovo,
fix brightness and power mode, close unnecessary background jobs, and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\experiment\run_lenovo_study.ps1 -Transport persistent
```

This builds the isolated study containers, starts streaming battery samples,
records a 60-second idle control, executes all 54 randomized PostgreSQL runs,
integrates battery-DC joules, audits selection, and stops its study containers and
sampler. The default sampling budget is 3600 seconds; increase `-SampleSeconds`
if necessary. If capture stops, the runner is aborted and partial artifacts remain.
Battery capture stops below 5 Wh remaining capacity or if AC is reconnected.
Do not reconnect the charger until the workflow finishes. Logs, source hashes,
dependency versions, plan, raw watts, and selection live beneath
`analysis/results/experimental_runs/lenovo-*`.

Sampling streams to disk so errors retain preceding samples. Inspect sensor update
cadence, timestamp gaps and integrated joules against the reported capacity drop
over a long interval. One-second polling does not imply the sensor updates each
second. The integrator rejects gaps over five seconds, including a short run that
falls inside a long unsampled gap. The idle interval is retained for review; no
idle subtraction happens automatically. Whole-laptop readings include the display,
Docker, sampling process, editor and other applications. Measure capture overhead
with a separate ablation before making small energy-saving claims.

Held-out real-service payloads/compatibility rules, a second physical device, and
measured controller switching and monitoring cost remain required before claiming
an adaptive optimiser advantage. The controller now clears active and pending
settings when its energy evidence disappears.
