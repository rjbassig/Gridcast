# Release status

This is a functioning local research release, **not completion of every production requirement**.

Implemented and executed: two-year authentic CAISO demand/DAM price acquisition, raw checksums, hourly filtering/schema checks, DST handling, missingness/outlier reports, Parquet/DuckDB, issue-safe direct features, four baselines, ridge/seasonal autoregression/XGBoost/LightGBM/PyTorch GRU, expanding-origin validation/test, pre-fold conformal calibration, event segments, MAE block intervals, validation permutation importance, trusted artifact serialization, API replay/sensitivity, Next.js terminal, reproducible report and review-only portfolio materials.

Implemented and checked locally: pytest behavior tests, API integration tests, Ruff lint, TypeScript validation and Next production build. GitHub Actions is configured; no remote run is claimed. Browser verification details and exact counts are recorded in verification.json after completion.

Not implemented: renewable generation/net-load ingestion, real-time or multi-hub pricing, holiday indicators, archived weather forecasts, verified point-in-time revision/publication vintages, gate-closure-aware DAM submission evaluation, SARIMA/SARIMAX/ETS, SHAP, causal temperature/renewable scenarios, automatic model promotion, scheduled ingestion/retraining, operational drift alerting, multi-user auth and public deployment. These are explicit follow-on work, not placeholder screens or fabricated outputs.

The report documents which proposed analyses are absent. The portfolio site and unrelated repositories were not touched.

## Runtime artifact audit (2026-11-16)

The source checkout intentionally excludes the runtime release bundle. The
following files are required by `api/main.py` but are not present in this
working copy: `data/processed/demand.parquet`,
`data/processed/price.parquet`, `data/processed/quality.json`,
`experiments/results/predictions.parquet`, and the `artifacts/*.joblib` model
registry referenced by `summary.json`. The lightweight CSV/JSON summaries and
the PDF are present.

These artifacts are reproducible from the documented CAISO OASIS acquisition
and training pipeline, but exact equality requires the preserved raw download
checksums and the same configuration. They cannot be reconstructed from the
summary files alone, so the API correctly remains not-ready instead of serving
fabricated replay values.

On macOS, XGBoost and LightGBM also require the OpenMP runtime. Install
Homebrew `libomp` (or use the repository's `scripts/python.sh` environment)
before running the full model test suite; the source tests that do not import
those native libraries remain runnable without it.
