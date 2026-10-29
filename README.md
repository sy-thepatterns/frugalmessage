# FrugalMessage

Quantitative research into communication between services. This repository begins with **Analysis I: workload characterization**. It does not claim an energy saving from observational data.

## Run the first analysis

1. Install Python 3.10+ and `pip install -r requirements.txt`.
2. Download `data.txt.gz` from the [Intel Lab Data original source](https://db.lcs.mit.edu/labdata/labdata.html) and place it at `data/raw/intel/data.txt.gz` (or pass its path explicitly). The download is approximately 34 MB compressed. Do not commit the raw file.
3. Run `python analysis/01_workload_characterization.py --input data/raw/intel/data.txt.gz --output analysis/results`.
4. Open `analysis/results/report.md` and the interactive Plotly HTML files in `analysis/results/figures/`.

The analysis validates the raw row count and parser assumptions, writes machine-readable metrics, and explains each result in technical and plain language. The output is generated from the downloaded data; no results are hard-coded.

## Research boundary

The Intel log is a record of wireless sensor readings and their arrival timestamps. It is useful for studying arrival patterns and constructing a reproducible *hypothetical* batching workload. It does **not** contain internal service-to-service packets, server power, or a measured batching trial. The experiment plan in [research-plan.md](analysis/research-plan.md) sets out how those claims can be tested. For genuine service dependencies, the [Alibaba microservice trace](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-microservices-v2021) is a later analysis input, but its published archives total tens of GiB and are deliberately not silently downloaded.

See [sources.md](analysis/sources.md) for dataset provenance and limitations. Raw downloads and generated results are ignored by Git.

