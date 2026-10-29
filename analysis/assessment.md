# Assessment after the first full run

## What we actually observed

The [generated report](results/report.md) and seven [interactive figures](results/figures/) come from the original 34.4 MB Intel archive, with a recorded SHA-256 and 2,313,682 parsed rows. Of those, 2,303,286 have both a valid timestamp and a roster ID from 1 to 54. The median interval between consecutive logged readings **from the same mote** is 33.2 seconds; the 95th percentile is 149.0 seconds. Sensor coverage is highly uneven: 35 to 65,693 records per ID. These are descriptive properties of this historical collection system.

Across interior calendar days the count ranges from 279 to 101,207. Such a low interior-day count may represent downtime or truncated logging; without an external uptime record it must not be interpreted as an intrinsic low-demand pattern. The plotted hour-of-day total also aggregates multiple dates and does not correct for which sensors were online.

The batching model predicts fewer *application sends* when events are combined. Its p95 holding time near zero at some settings follows the log's clustered timestamps; it is **not** evidence of negligible delivery latency. Source timestamps are observed log times, not necessarily application arrival times at a queue. Zero failed transmissions, acknowledgements, serialization overhead, and power are assumptions in this model.

## Missing evidence, in priority order

| Gap | Why it matters | Specific next action |
| --- | --- | --- |
| Real internal service paths | Sensor readings alone do not identify east-west dependencies, protocol or message size | Analyze sampled Alibaba call graphs: deduplicate paired RPC records, reconstruct edge and path frequency, show response time by call type with sampling caveats. |
| A justified workload selection | A 2004 wireless lab is only one old source and has serious uptime/coverage effects | Compare its burst structure with Azure per-minute function invocations, then select quiet, steady and burst profiles with recorded selection rules. Do not claim representativeness of all homelabs. |
| Actual traffic and correctness | One modelled batch is not one measured network packet | In a version-pinned queue/worker/DB testbed, record packet and byte counts per edge, successful record IDs, loss, duplicates, retry counts and acknowledgment policy. |
| Whole-host power | The current analysis contains no power measurement | Record wall watts for the complete testbed, including idle, under an identical completed-task workload; integrate watts over time and report joules per successful task with repeated-run uncertainty. |
| Latency and fairness | Holding time excludes processing, queueing and storage | Measure timestamped end-to-end p50/p95/p99 latency. Randomize the order of baseline and candidate runs and report resource contention and instrumentation cost. |
| Robustness and generalization | One device and one workload cannot establish a universal optimum | Repeat on at least a small homelab system and a larger host if available; show separate Pareto frontiers by workload and hardware rather than pooling them. |

## Decision for the next analysis

Treat the Intel results as a documented replay input for an IoT ingestion use case. Make Alibaba's service-to-service trace the primary observational evidence for the east-west research question. For the sustainability claim, use controlled measured experiments, not an inferred watts-per-message factor. Report any null or adverse result, including settings that reduce sends but increase total energy or violate latency.

