# Analysis I - Investigating the problem

## Research question

Under which observed workload and dependency patterns might internal communication settings change resource use, and what evidence would establish a benefit without violating latency and delivery requirements?

| ID | Question | Evidence and justified method | Output / interpretation limit |
| --- | --- | --- | --- |
| Q1 | How variable are event arrivals? | INTEL-2004: count observations per hour and day, interarrival quantiles. AZURE-FUNC-2019 later checks whether burstiness also appears in serverless workloads. Use fixed windows and disclose time-zone assumptions. | Workload profiles, not measured network traffic. |
| Q2 | Are all sources equally active and complete? | INTEL-2004: per-mote counts and coverage, empty channels, invalid IDs, time gaps. Report missingness before any rate calculation. | Missing records cannot be assumed to be lost transmissions. |
| Q3 | How complex and concentrated are real service dependencies? | ALIBABA-MS-2021: deduplicate two sides of one RPC by trace/rpc ID, reconstruct parent paths, compare fan-out and call-frequency distributions. Show sensitivity to 0.5% call-graph sampling. | Descriptive production topology; no causal energy effect. |
| Q4 | What do latency and utilization look like by communication class? | ALIBABA-MS-2021: stratify RPC types and report quantiles; pair call-rate periods with service and host utilization only where join keys and intervals align. | Association does not isolate protocol or configuration effects. |
| Q5 | Does idle power make a small reduction in CPU work meaningful? | GOOGLE-POWER-2019 and SPECPOWER: plot published power versus load, distinguishing host and facility boundaries. | Context and sensitivity, not attributable energy savings. |

### First implemented analysis

`01_workload_characterization.py` implements Q1 and Q2 with INTEL-2004. It also plots **modelled** batch count and maximum hold time for several settings as an experiment-design aid. The model assumes immediate flushing at a fixed count or timeout, perfect delivery and no protocol overhead. It is labelled as a counterfactual, not a result about watts, actual packets or end-to-end latency.

# Analysis II - Controlled experiments

Freeze topology, workload replay, data payload, hardware, software version and task definition. Randomize or alternate baseline and candidate order; include idle measurements and repeated runs on the same testbed. First path: producer  broker/queue  worker  PostgreSQL. One candidate family: batch size � maximum wait. Keep delivery semantics constant.

| Question | Measured variables | Acceptance condition |
| --- | --- | --- |
| Does configuration reduce communication work? | Actual bytes and packets on each service edge; messages and completed events | Count both request and reply traffic, including retries and acknowledgements. |
| Does it reduce energy? | Timestamped wall watts, duration, idle control, joules / successful event | Report uncertainty across repeated runs; distinguish whole-host and incremental energy. |
| What does it cost users? | p50/p95/p99 end-to-end event latency, throughput, failures, duplicates and loss | Define task-specific latency/reliability thresholds before selecting a winner. |
| Does the benefit persist? | Quiet, steady and bursty profiles derived from published traces | Report each profile separately, with workload and device labels. |

Pareto dominance is assessed *only among configurations satisfying correctness*. A candidate dominates another if it uses no more joules per successful event and has no higher p95 delivery latency, with a strict improvement in at least one. Report bytes and CPU alongside rather than treating them as an energy conversion. Test protocol changes only after a working and equivalent task is defined for both protocols.

