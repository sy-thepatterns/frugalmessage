# Alibaba microservice call-graph slices

Source: [Alibaba cluster-trace-microservices-v2021](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-microservices-v2021). The publisher releases 145 call-graph archives covering twelve hours and samples call graphs at 0.5%. We analyzed **three complete five-minute archives** at the start, middle, and end of the period. These are temporal sensitivity slices, not a census of the trace. Reproduce each with `python analysis/03_alibaba_dependencies.py --input PATH --output PATH`.

| Shard | Source time (ms) | Raw rows | Call graphs | Logical calls after pairing | Known-endpoint edges | Busiest 1% edge share | Calls missing endpoints |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [0](metrics.json) | 2–299,999 | 6,088,846 | 131,256 | 4,641,775 | 16,100 | 68.28% | 12.29% |
| [72](shard72/metrics.json) | 21,600,000–21,899,999 | 5,814,610 | 148,031 | 4,570,686 | 16,885 | 68.32% | 10.68% |
| [143](shard143/metrics.json) | 42,900,000–43,199,999 | 7,432,404 | 234,882 | 5,748,267 | 15,941 | 68.87% | 18.33% |

The busiest 1% share is calculated **within each shard** from calls whose upstream and downstream IDs are usable. The top 100 `(upstream, downstream, RPC type)` edges overlap by 88 between shards 0 and 72, 78 between 0 and 143, and 85 between 72 and 143. This makes edge concentration and many busy edges reasonably stable across the three selected periods. It does not establish a twelve-hour estimate or justify multiplying sampled counts by 200; graph inclusion, missing fields, and the choice of three shards still limit inference.

In shard 0, 1,447,071 additional records pair to an existing trace/RPC ID. The median graph has 11 logical calls and p95 has 157. The source-reported client-side RT p95 is 169 ms for RPC (1,393,343 observations), 44 ms for HTTP (96,433), and 2 ms for MC (2,329,430). Shards 72 and 143 have RPC RT p95 of 182 and 141 ms. These distributions describe different service/task mixes and are not protocol-effect estimates. A source RT of 0 can represent a value below 1 ms.

**Quality limits:** Shard 0 has 55,980 trace/RPC IDs with conflicting type labels and 570,505 calls missing two usable endpoints. Its 514,527 calls without an observed parent include possible roots and incomplete paths. Missing-endpoint fractions change across slices, especially late in the period, so path and concentration claims remain conditional on recorded fields. Payload bytes, tenant boundaries, ordering guarantees, packets, and energy are absent. The [top-edge tables](top_edges.csv) retain anonymized IDs without assigning human-readable service names.

**Deduction:** Busy routes are plausible first optimisation targets, and the three slices reduce concern that the shard-0 result was a one-off. The trace cannot say which events may legally share a batch. The controlled study fixes compatibility and delivery separately; measured task and energy outcomes remain necessary.
