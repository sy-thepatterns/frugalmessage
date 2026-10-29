"""Reproducible descriptive analysis of the original Intel Lab event log.

No simulated quantity in this module is a measured packet, server latency, or joule.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

SOURCE = "https://db.lcs.mit.edu/labdata/labdata.html"
COLUMNS = ["date", "time", "epoch", "moteid", "temperature", "humidity", "light", "voltage"]


def load(path: Path) -> pd.DataFrame:
    # Explicit single-space separation preserves empty sensor channels. Regex
    # whitespace separation silently shifts values on incomplete records.
    df = pd.read_csv(path, sep=" ", names=COLUMNS, header=None, compression="infer",
                     dtype={"date": "string", "time": "string"}, low_memory=False)
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
    for col in COLUMNS[2:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def model_batches(times: np.ndarray, max_count: int, max_wait_s: float) -> tuple[int, np.ndarray]:
    """Flush on count or scheduled timeout; return count and event hold times."""
    if max_count < 1 or max_wait_s < 0:
        raise ValueError("Invalid batching settings")
    if not len(times):
        return 0, np.array([])
    waits = np.empty(len(times), dtype=float)
    start = 0
    batches = 0
    for i in range(len(times)):
        if i > start and times[i] >= times[start] + max_wait_s:
            waits[start:i] = times[start] + max_wait_s - times[start:i]
            batches += 1
            start = i
        if i - start + 1 == max_count:
            waits[start:i + 1] = times[i] - times[start:i + 1]
            batches += 1
            start = i + 1
    if start < len(times):
        # The finite observation window ends before the last scheduled timeout.
        # Flush at the scheduled timeout to preserve the stated model.
        waits[start:] = times[start] + max_wait_s - times[start:]
        batches += 1
    return batches, waits


def save(fig: go.Figure, directory: Path, name: str) -> None:
    fig.update_layout(template="plotly_white", title_x=0.03)
    fig.write_html(directory / f"{name}.html", include_plotlyjs=True, full_html=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path, help="Original Intel data.txt or data.txt.gz")
    p.add_argument("--output", default=Path("analysis/results"), type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    figures = args.output / "figures"
    figures.mkdir(exist_ok=True)

    raw = load(args.input)
    total = len(raw)
    invalid_time = int(raw.timestamp.isna().sum())
    missing_mote = int(raw.moteid.isna().sum())
    out_of_roster = int((raw.moteid.notna() & ~raw.moteid.between(1, 54)).sum())
    incomplete = int(raw[["temperature", "humidity", "light", "voltage"]].isna().any(axis=1).sum())
    valid = raw.loc[raw.timestamp.notna() & raw.moteid.between(1, 54), ["timestamp", "moteid"]].copy()
    valid = valid.sort_values("timestamp", kind="stable")
    if valid.empty:
        raise ValueError("No timestamped readings with mote IDs 1-54")

    daily = valid.groupby(valid.timestamp.dt.floor("D")).size().rename("readings")
    hourly = valid.groupby(valid.timestamp.dt.hour).size().rename("readings").reindex(range(24), fill_value=0)
    by_mote = valid.groupby("moteid").size().reindex(range(1, 55), fill_value=0).rename("readings")
    gaps = valid.groupby("moteid").timestamp.diff().dt.total_seconds().dropna()
    gaps = gaps[gaps >= 0]
    times = valid.timestamp.astype("int64").to_numpy() / 1e9

    save(px.line(x=daily.index, y=daily.values, labels={"x": "Calendar day", "y": "Logged readings"},
                 title="1. Logged readings by day"), figures, "01_daily_volume")
    save(px.bar(x=hourly.index, y=hourly.values, labels={"x": "Hour of day in source timestamps", "y": "Logged readings"},
                title="2. Logged readings by hour of day (aggregated across dates)"), figures, "02_hour_of_day")
    save(px.bar(x=by_mote.index, y=by_mote.values, labels={"x": "Mote ID", "y": "Logged readings"},
                title="3. Unequal coverage across sensors"), figures, "03_mote_coverage")
    cutoff = float(gaps.quantile(.99))
    counts, edges = np.histogram(gaps[gaps <= cutoff], bins=90)
    save(px.bar(x=(edges[:-1] + edges[1:]) / 2, y=counts,
                labels={"x": "Seconds between logged readings from one mote", "y": "Frequency"},
                title="4. Within-mote gaps (0-99th percentile; tail excluded from view)"), figures, "04_within_mote_gaps")
    # Aggregate to 101 quantiles rather than embedding millions of raw values
    # in a multi-megabyte HTML plot. Include the upper tail in the quantiles.
    probabilities = np.linspace(0, 1, 101)
    save(px.line(x=gaps.quantile(probabilities).to_numpy(), y=probabilities,
                 labels={"x": "Seconds between logged readings", "y": "Cumulative proportion"},
                 title="5. Within-mote gap quantiles (entire observed range)"), figures, "05_gap_ecdf")

    scenarios = []
    for count in (1, 8, 32):
        for wait_s in (1, 10, 60):
            batches, waits = model_batches(times, count, wait_s)
            scenarios.append({"max_count": count, "max_wait_s": wait_s, "modelled_batches": batches,
                              "modelled_reduction_pct": 100 * (1 - batches / len(times)),
                              "modelled_p95_hold_s": float(np.quantile(waits, .95))})
    sim = pd.DataFrame(scenarios)
    fig = px.line(sim, x="modelled_p95_hold_s", y="modelled_batches", color="max_count", symbol="max_wait_s",
                  hover_data=["modelled_reduction_pct"], markers=True,
                  labels={"modelled_p95_hold_s": "Modelled p95 holding time (s)",
                          "modelled_batches": "Modelled batches flushed"},
                  title="6. Hypothetical batch count versus holding time; no network or energy measurement")
    save(fig, figures, "06_modelled_batch_tradeoff")
    save(px.bar(sim, x="max_count", y="modelled_reduction_pct", color="max_wait_s", barmode="group",
                labels={"max_count": "Maximum records per batch", "modelled_reduction_pct": "Modelled reduction in sends (%)"},
                title="7. Hypothetical reduction in sends; assumes one send per batch"), figures, "07_modelled_send_reduction")

    metrics = {"source": SOURCE, "input": str(args.input), "raw_rows": total,
               "invalid_timestamps": invalid_time, "missing_mote_ids": missing_mote,
               "out_of_roster_mote_ids": out_of_roster, "rows_with_missing_sensor_channel": incomplete,
               "valid_timestamped_roster_rows": len(valid), "first_timestamp": str(valid.timestamp.min()),
               "last_timestamp": str(valid.timestamp.max()), "median_per_mote_gap_s": float(gaps.median()),
               "p95_per_mote_gap_s": float(gaps.quantile(.95)),
               "daily_min": int(daily.min()), "daily_max": int(daily.max()),
               "sensor_min": int(by_mote.min()), "sensor_max": int(by_mote.max()),
               "batch_scenarios": scenarios}
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    sim.to_csv(args.output / "batch_scenarios.csv", index=False)
    report = f"""# Analysis I - first quantitative findings

Source: [original Intel Lab Data]({SOURCE}). Input: `{args.input}`. All counts below are calculated from that file. Times are as recorded by the source; a timezone is not asserted.

## Data validation and scope

Raw records: **{total:,}**; valid timestamp and roster ID (1-54): **{len(valid):,}**; invalid timestamps: **{invalid_time:,}**; missing mote IDs: **{missing_mote:,}**; out-of-roster IDs: **{out_of_roster:,}**; rows with =1 missing sensor channel: **{incomplete:,}**. Observation interval: {valid.timestamp.min()} to {valid.timestamp.max()}.

**Technical interpretation:** Counts are log observations after an explicit single-space parse. The source has missing epochs and incomplete sensors. Neither a missing reading nor a long gap identifies a network packet loss without independent packet-level evidence.

**Plain language:** We know when readings were recorded. We cannot tell why an expected reading might be absent.

## Q1 - How variable is the arrival workload?

Daily recorded volume ranges from **{int(daily.min()):,}** to **{int(daily.max()):,}** readings. The median and p95 of nonnegative consecutive *within-mote* gaps are **{gaps.median():.1f} s** and **{gaps.quantile(.95):.1f} s**. See figures 1, 2, 4 and 5.

**Technical interpretation:** These are empirical arrival and within-source interval distributions conditional on records being logged. Daily endpoint days may be partial. Aggregating all 54 motes would conceal per-source gaps, so the gap distribution is calculated separately for each mote.

**Plain language:** The flow of recorded readings changes over time, and each sensor has its own pattern. That gives us a realistic input schedule to replay in later experiments.

## Q2 - Is sensor coverage uniform?

The least and most represented roster IDs have **{int(by_mote.min()):,}** and **{int(by_mote.max()):,}** logged readings. See figure 3.

**Technical interpretation:** Per-mote coverage varies. Any configuration comparison must replay the *same* filtered events in the same order; otherwise differences in input composition could be mistaken for configuration effects.

**Plain language:** Some sensors contribute far more readings than others. We must feed identical data to every version we compare.

## Hypothesis generator - batching model

Figures 6 and 7 and `batch_scenarios.csv` show a deterministic count-or-timeout model. The modelled number of sends equals the number of flushed batches; modelled hold is time between an event's arrival and its batch flush. **These are not observed packets, latency, bytes, watts, or joules.** The model ignores acknowledgements, headers, failures and processing cost. It selects candidate settings for Analysis II, where those quantities must be measured.

## What this analysis cannot conclude

It cannot establish that batching saves energy, that MQTT is preferable to HTTP, or that the Intel wireless deployment resembles a particular homelab. Next: use Alibaba traces to characterize real service edges, then replay fixed workloads on an instrumented service path and measure wall energy, bytes, delivery and latency.
"""
    (args.output / "report.md").write_text(report, encoding="utf-8")
    print(f"Analysed {total:,} records; wrote report, metrics and 7 Plotly figures to {args.output}")


if __name__ == "__main__":
    main()

