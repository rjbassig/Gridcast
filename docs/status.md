# Release status

This is a functioning local research release, **not completion of every production requirement**.

Implemented and executed: two-year authentic CAISO demand/DAM price acquisition, raw checksums, hourly filtering/schema checks, DST handling, missingness/outlier reports, Parquet/DuckDB, issue-safe direct features, four baselines, ridge/seasonal autoregression/XGBoost/LightGBM/PyTorch GRU, expanding-origin validation/test, pre-fold conformal calibration, event segments, MAE block intervals, validation permutation importance, trusted artifact serialization, API replay/sensitivity, Next.js terminal, reproducible report and review-only portfolio materials.

Implemented and checked locally: pytest behavior tests, API integration tests, Ruff lint, TypeScript validation and Next production build. GitHub Actions is configured; no remote run is claimed. Browser verification details and exact counts are recorded in verification.json after completion.

Not implemented: renewable generation/net-load ingestion, real-time or multi-hub pricing, holiday indicators, archived weather forecasts, verified point-in-time revision/publication vintages, gate-closure-aware DAM submission evaluation, SARIMA/SARIMAX/ETS, SHAP, causal temperature/renewable scenarios, automatic model promotion, scheduled ingestion/retraining, operational drift alerting, multi-user auth and public deployment. These are explicit follow-on work, not placeholder screens or fabricated outputs.

The report documents which proposed analyses are absent. The portfolio site and unrelated repositories were not touched.
