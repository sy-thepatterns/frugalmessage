# Analysis I - first quantitative findings

Source: [original Intel Lab Data](https://db.lcs.mit.edu/labdata/labdata.html). Input: `data\raw\intel\data.txt.gz`; SHA-256: `d99288c8f406ca6604d359ceaa0d8adfffa79e7095061a1e27dc4399f48c7225`. All counts below are calculated from that file. Times are as recorded by the source; a timezone is not asserted.

## Data validation and scope

Raw records: **2,313,682**; valid timestamp and roster ID (1-54): **2,303,286**; invalid timestamps: **4**; missing mote IDs: **526**; out-of-roster IDs: **9,866**; rows with at least one missing sensor channel: **93,879**. Observation interval: 2004-02-28 00:58:46.002832 to 2004-04-03 16:51:34.171452.

**Technical interpretation:** Counts are log observations after an explicit single-space parse. The source has missing epochs and incomplete sensors. Neither a missing reading nor a long gap identifies a network packet loss without independent packet-level evidence.

**Plain language:** We know when readings were recorded. We cannot tell why an expected reading might be absent.

## Q1 - How variable is the arrival workload?

Across interior calendar days, recorded volume ranges from **279** to **101,207** readings. The median and p95 of nonnegative consecutive *within-mote* gaps are **33.2 s** and **149.0 s**. See figures 1, 2, 4 and 5.

**Technical interpretation:** These are empirical arrival and within-source interval distributions conditional on records being logged. The daily range excludes the first and last calendar day because they are partial; other days may still contain outages. Aggregating all 54 motes would conceal per-source gaps, so the gap distribution is calculated separately for each mote.

**Plain language:** The flow of recorded readings changes over time, and each sensor has its own pattern. That gives us a realistic input schedule to replay in later experiments.

## Q2 - Is sensor coverage uniform?

The least and most represented roster IDs have **35** and **65,693** logged readings. See figure 3.

**Technical interpretation:** Per-mote coverage varies. Any configuration comparison must replay the *same* filtered events in the same order; otherwise differences in input composition could be mistaken for configuration effects.

**Plain language:** Some sensors contribute far more readings than others. We must feed identical data to every version we compare.

## Hypothesis generator - batching model

Figures 6 and 7 and `batch_scenarios.csv` show a deterministic count-or-timeout model. The modelled number of sends equals the number of flushed batches; modelled hold is time between an event's arrival and its batch flush. **These are not observed packets, latency, bytes, watts, or joules.** The model ignores acknowledgements, headers, failures and processing cost. It selects candidate settings for Analysis II, where those quantities must be measured.

## What this analysis cannot conclude

It cannot establish that batching saves energy, that MQTT is preferable to HTTP, or that the Intel wireless deployment resembles a particular homelab. Next: use Alibaba traces to characterize real service edges, then replay fixed workloads on an instrumented service path and measure wall energy, bytes, delivery and latency.

## Interactive figures

Download an HTML file and open it in a browser with internet access for the Plotly library.

| Figure | Technical reading | Plain-language reading |
| --- | --- | --- |
| [1. Daily volume](figures/01_daily_volume.html) | Timestamped row count by calendar day; boundary days are partial and low interior days may reflect downtime. | The recorded flow varies; low counts need investigation. |
| [2. Hourly volume](figures/02_hour_of_day.html) | Row count by source hour aggregated across dates, without uptime normalization. | Some hours have more recorded events, but this alone does not prove a daily demand cycle. |
| [3. Sensor coverage](figures/03_mote_coverage.html) | Marginal event counts per valid mote ID. | Sensors contributed different amounts of data. |
| [4. Gap frequency](figures/04_within_mote_gaps.html) | Consecutive within-mote gaps, with values above the 99th percentile omitted from the plotted histogram. | Most observed gaps are short; this view hides the longest ones. |
| [5. Gap quantiles](figures/05_gap_ecdf.html) | Empirical interval quantiles including the upper tail. | This shows how unusual the longer gaps are. |
| [6. Modelled tradeoff](figures/06_modelled_batch_tradeoff.html) | Batch count versus p95 modelled holding time under explicit count/timeout rules. | Combining records could mean fewer sends but some records wait; neither outcome has been measured on a server. |
| [7. Modelled send reduction](figures/07_modelled_send_reduction.html) | Reduction relative to one modelled send per accepted log event. | This is a planning calculation, not an electricity saving. |

