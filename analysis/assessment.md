# Optimiser reassessment and execution status

## Findings that change the design

The original Intel log has 2,313,682 parsed rows and 2,303,286 timestamped readings with roster IDs. Median, p95, and p99 within-mote gaps are 33.2, 149.0, and 320.2 seconds. Coverage ranges from 35 to 65,693 readings per mote. The 279-reading interior day has only three active motes, so low logged volume must not be equated with low demand. [Analysis I](01_observed_workloads.ipynb) records the audit.

Batching is governed by its **compatibility domain and deadline**. At an eight-record cap and ten-second deadline, pooling all Intel events models 85.44% fewer sends with p95 hold 9.80 seconds; per-mote streams model only 0.383% fewer sends with p95 hold 10 seconds. At 60 seconds, per-mote sends fall 48.98%, while p95 hold reaches 60 seconds. These are application-send and hold calculations, not packets or energy. [Analysis II](02_models_and_experiments.ipynb) shows the sensitivity.

Three five-minute slices of the [Alibaba 2021 call-graph trace](results/alibaba/report.md), near the start, middle, and end of its twelve hours, contain 19,335,860 raw rows and 14,960,728 logical calls after pairing. In each slice, the busiest 1% of observed known-endpoint edges carry about 68–69% of calls. Top-100 edge overlap across slices is 78–88. This supports targeting busy routes, but the source samples call graphs at 0.5%, we analyzed only three of 145 archives, and 10.68–18.33% of logical calls in those slices lack two usable endpoints. The trace cannot specify batching legality, payloads, or causal energy effects.

The [replay selection](results/replay/report.md) processes all 14 Azure invocation-day files and chooses availability-gated Intel windows. It exports 24,066 stable replay IDs across six quiet/steady/bursty labels. Azure's within-minute timestamps are constructed from published counts, and its counts are scaled by 0.0001; the testbed accelerates each source hour 120-fold. Those choices are recorded and are not claims of native production traffic.

## First optimiser scope

Build a constrained, measured configuration optimiser for **one isolated producer → HTTP → bounded queue → worker → PostgreSQL path**. Its initial controls are maximum batch count and wait, scoped by route, tenant, and schema. The [contract](../experiment/contract.json) fixes ordering, idempotent completion IDs, retry and acknowledgement behavior. The predeclared research limits are p95 delivery ≤ 2 s, p99 ≤ 5 s, zero missing/extra/duplicate completed IDs, zero send errors, and throughput ≥ 90% of that profile's baseline median. These are illustrative limits, not a production SLA.

The preferred first device is the **Lenovo Yoga 7i Gen 9 Windows laptop**, followed by the M1 MacBook Air as a separate hardware profile. A ZOTAC PostgreSQL smoke test verified 100 completed IDs, but its randomized matrix was stopped at the owner's request before completion. Its partial files are retained only in ignored `.tmp` for audit and are excluded from selection. No FrugalMessage study containers remain running on that server.

## Missing work, in dependency order

| Priority | Status | Next action | Why it still matters |
| --- | --- | --- | --- |
| 1. Service routes and compatibility | Three Alibaba time slices analyzed; testbed compatibility fixed | Validate a selected route with real payload and ordering requirements before claiming deployability. Analyze more shards if a twelve-hour estimate is required. | Anonymized call edges do not reveal legal batch boundaries. |
| 2. Replay workloads | Six documented windows exported and checksummed | Add a held-out, per-function or real-service trace before generalizing. Keep Azure constructed timing and acceleration explicit. | Aggregate counts smooth route-level bursts; Intel coverage still limits quiet profiles. |
| 3. Correctness and latency contract | Implemented and tested locally; illustrative limits predeclared | Run the full three-repeat matrix on the Yoga. Preserve failures. Replace research limits if a real service SLA becomes available. | A failed repeat disqualifies its configuration. |
| 4. Traffic and system energy | HTTP completion/latency/body-byte instrumentation implemented; optional isolated-edge packet capture coded | On the Yoga, check battery discharge-rate telemetry, then run on battery for a long enough interval **or** attach a timestamped AC watt meter. Validate packet-capture availability and its overhead. | Body bytes, CPU time, and processor-package watts cannot establish whole-device joules. AC-wall and battery-DC boundaries must remain separate. |
| 5. Selection and uncertainty | Strict all-repeat selector and watt-integration tool implemented with tests | Import a complete Yoga run plan and matching power samples; report run-level ranges/SD and compare eligible settings on joules per successful task and latency. | The interrupted ZOTAC plan has missing repeats, and no measured energy Pareto exists. |
| 6. Generalization and adaptation | Multi-architecture images pinned; safe fallback/hysteresis controller scaffold tested | Run the same study on the MacBook Air; use held-out windows to measure controller telemetry overhead, switching cost, rollback, and performance against the best fixed feasible setting. | A static or single-device result does not establish an adaptive optimum. |

## Human intervention and claim boundary

No data API key is needed: the Intel, Azure, and selected Alibaba archives are public and have been downloaded. To finish a measured optimiser, open this checkout on the Yoga and run the [Windows power probe](../experiment/windows_power_probe.ps1); the current session is on Lenovo model 83DL and successfully reads discharge watts when unplugged. SQLite diagnostic energy is measured, while the reference PostgreSQL energy study remains pending. Docker Desktop with Linux containers is needed for the pinned PostgreSQL setup on Windows. If battery discharge rate is unavailable or too coarse, provide an AC plug meter with timestamped watt export. Opening the same checkout on the MacBook Air is needed for the second-device study.

Current evidence supports workload characterization, real sampled service-edge concentration, reproducible replay, and a functional testbed. It does **not** yet support a measured energy saving or an adaptive optimiser advantage. Report null and adverse outcomes along with improvements.

## Latest Lenovo implementation work

The local test suite now exercises HTTP rejection, acknowledgement after commit,
idempotent retry, persistent connections, queue saturation, database failure,
invalid power samples, and controller rollback when energy evidence disappears.
Windows/Linux CI and a development dependency file make these checks repeatable.
The instrumented harness separates hold, sender backlog, HTTP, server queue and
commit timing; direct persistent HTTP is an explicit transport ablation.

Battery samples were captured on Lenovo Yoga 7 2-in-1 16IML9 (83DL), with results
and limitations in [Lenovo testing](lenovo-testing.md). SQLite and diagnostic plans
cannot select a reference-study energy winner. Docker is absent in this session;
the guarded `experiment/run_lenovo_study.ps1` prepares the 54-run PostgreSQL study
once a working Linux Docker engine is installed. A real-service held-out trace,
second-device study, capture-overhead ablation, and measured online controller
switching/monitoring costs remain outstanding, rather than being inferred from
local functional runs.
