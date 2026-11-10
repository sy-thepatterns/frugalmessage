# Selected replay windows

Sources: [Intel Lab Data](https://db.csail.mit.edu/labdata/labdata.html) and [Azure Functions Trace 2019](https://github.com/Azure/AzurePublicDataset/blob/master/AzureFunctionsDataset2019.md). Full source archive checksums, rules, and exact window identifiers are in [manifest.json](manifest.json). Reproduce with `python analysis/04_replay_windows.py`.

| Profile | Source window | Observed count | Replay count | Peak minute / mean minute |
| --- | --- | ---: | ---: | ---: |
| Intel quiet | 2004-03-06 04:00 | 3,926 | 3,926 | 1.15 |
| Intel steady | 2004-03-08 00:00 | 4,557 | 4,557 | 1.15 |
| Intel bursty | 2004-03-10 06:00 | 4,582 | 4,582 | 1.24 |
| Azure quiet | day 08, hour 01 | 29,937,581 | 2,995 | 1.16 |
| Azure steady | day 13, hour 21 | 37,363,901 | 3,736 | 1.14 |
| Azure bursty | day 09, hour 18 | 42,726,264 | 4,270 | 1.68 |

The Intel candidates require at least **40 distinct sensor IDs in every minute** of the hour. This gate excludes conspicuous low-volume periods with sparse sensor coverage, but it leaves only modest variation: the selected Intel 'bursty' hour is mildly bursty. Azure selection uses all 14 per-minute invocation-day files; its `active_sources` field is merely the number of function rows in each day file and is not a per-minute availability measure. Azure's published data are a small, unspecified sample of functions and do not describe service calls.

The [selected profiles](selected_profiles.csv) give observed and scaled counts per minute. The [replay events](replay_events.csv) give 24,066 stable event IDs, route keys, and offsets. Intel offsets come from original log timestamps and raw row IDs. Azure counts are multiplied by 0.0001, rounded per minute, and individual event offsets are deterministically spaced within each minute. Those Azure event times are **constructed for a controlled replay**, not observed. The testbed additionally compresses each hour 120-fold, which creates a stress workload with a higher arrival rate than the original source. Only matched configurations within a profile can be compared.
