# FrugalMessage

Quantitative research into communication between services. This repository begins with **Analysis I: workload characterization**. It does not claim an energy saving from observational data.

## Research notebooks

- [Analysis I: Observed workloads](analysis/01_observed_workloads.ipynb) contains the original source, questions, validation, five Plotly figures, and technical and plain-language interpretations.
- [Analysis II: Models and experiments](analysis/02_models_and_experiments.ipynb) compares pooled and per-sensor batching boundaries, checks model behavior, and defines a correctness-gated measured-results/Pareto workflow. No experimental energy results exist yet.

The notebooks are the primary reading path. The Python scripts and published figures and metrics remain available for non-notebook execution and for browsing the current findings without downloading the raw archives.

## Run the notebooks

1. Install Python 3.10+ and `pip install -r requirements.txt`, then launch `jupyter lab` from the `analysis/` directory.
2. Download [`data.txt.gz` from MIT CSAIL](https://db.csail.mit.edu/labdata/data.txt.gz) and place it at `data/raw/intel/data.txt.gz` (or pass its path explicitly). The download is approximately 34 MB compressed. Do not commit the raw file.
3. Open and run `01_observed_workloads.ipynb`, then `02_models_and_experiments.ipynb`.
4. Alternatively run `python analysis/01_workload_characterization.py --input data/raw/intel/data.txt.gz --output analysis/results` and `python analysis/02_batch_scope_sensitivity.py`, then open the report and interactive Plotly HTML figures. The HTML figures load Plotly from a CDN and need an internet connection.

The analysis validates the raw row count and parser assumptions, writes machine-readable metrics, and explains each result in technical and plain language. The output is generated from the downloaded data; no results are hard-coded.

The current-code rerun found that previously checked-in batching figures were stale. At an 8-record cap and 10-second timeout, the pooled model gives 85.44% fewer application sends, while the per-sensor boundary gives 0.383%. These are sensitivity calculations, not measured communication or energy savings. The [reassessment](analysis/assessment.md) sets the narrower experimental scope for a credible optimiser.

## Expanded study

- [Alibaba shard analysis](analysis/results/alibaba/report.md) describes real service edges and source-reported call times in three five-minute slices at the start, middle and end of the published trace. Run `python analysis/03_alibaba_dependencies.py --input data/raw/alibaba/MSCallGraph_0.tar.gz --output analysis/results/alibaba` and repeat for shards 72 and 143 with their own output directories; the [publisher's fetch script](https://github.com/alibaba/clusterdata/blob/master/cluster-trace-microservices-v2021/fetchData.sh) lists the archive URLs.
- [Replay selection](analysis/results/replay/report.md) uses all 14 Azure invocation-day files and availability-gated Intel windows. Run `python analysis/04_replay_windows.py` after downloading the [Azure release](https://github.com/Azure/AzurePublicDataset/releases/download/dataset-functions-2019/azurefunctions_dataset2019_azurefunctions-dataset2019.tar.xz). The 24,066 replay events have stable IDs; Azure within-minute timing is constructed and labelled.
- [Controlled service study](experiment/README.md) supplies a portable HTTP/queue/worker/database harness, isolated PostgreSQL Compose setup, randomized run plan, strict repeat-level eligibility, and a whole-host watt-sample integration path. Run `python analysis/05_select_configs.py --plan PATH_TO_PLAN` after repeated results are available.

The Lenovo Yoga 7i is the preferred first hardware target; an M1 MacBook Air is planned as a second target when this checkout is opened there. A partial ZOTAC run was stopped at the owner's request and is excluded from selection. **Whole-host energy remains unmeasured** until timestamped AC-wall or battery-DC power samples are supplied; the study does not infer joules from application sends or CPU time.

## Research boundary

The Intel log is a record of wireless sensor readings and their arrival timestamps. It is useful for studying arrival patterns and constructing a reproducible *hypothetical* batching workload. It does **not** contain internal service-to-service packets, server power, or a measured batching trial. The experiment plan in [research-plan.md](analysis/research-plan.md) sets out how those claims can be tested. For genuine service dependencies, the [Alibaba microservice trace](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-microservices-v2021) is a later analysis input, but its published archives total tens of GiB and are deliberately not silently downloaded.

See [sources.md](analysis/sources.md) for dataset provenance and limitations. Raw downloads and generated results are ignored by Git.

