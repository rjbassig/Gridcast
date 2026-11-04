# Review-ready portfolio materials

## Concise description
Built a standalone California energy forecasting research platform using real CAISO demand and NP15 day-ahead prices, leakage-aware historical validation, fitted-model replay, and measured forecast uncertainty.

## Case study
Acquired two years of hourly source data in retryable, checksummed batches; normalized market identifiers, units, UTC timestamps and local DST calendar features. Compared four baselines, two ridge settings, seasonal autoregression, XGBoost, LightGBM and a small PyTorch GRU at five direct horizons. Validation chose models independently for demand and price, and final held-out results remained separate from tuning.

Demand: lightgbm achieves 24-hour held-out MAE 1191.45 MW, 31.2% relative MAE reduction versus weekly seasonal naive; 90% nominal interval coverage is 93.2%.
Price: ridge_100 achieves 24-hour held-out MAE 6.03 USD/MWh, 7.1% relative MAE reduction versus weekly seasonal naive; 90% nominal interval coverage is 90.7%.

The dashboard exposes historical exploration, model comparisons, uncertainty, model sensitivity and quality reports through FastAPI. Publication times are conservative assumptions and historical revisions remain a limitation. This is a local research release; no public deployment or trading optimization is claimed.

## Three resume bullets
- Engineered reproducible CAISO ingestion and Parquet/DuckDB storage for 35,087 authentic hourly demand and day-ahead LMP records, preserving a known demand gap and negative prices.
- Implemented five-horizon expanding-origin evaluation across statistical, boosted-tree and PyTorch models, with publication-delay checks, separate conformal calibration, validation-based selection and a held-out half-year.
- Delivered FastAPI artifact-backed inference and a responsive Next.js research terminal with forecast replay, empirical interval coverage, permutation importance and model-connected sensitivity scenarios.

## Technical interview explanation
Start with the information set at issue time. Each horizon has a direct target; all observed predictors are delayed, fit labels are purged before calibration, and calibration labels precede the evaluation fold. Explain that corrected historical values are still not authentic vintages. Describe why the simple weekly baseline is necessary, why short-horizon day-ahead prices require a gate-closure-aware future study, and why nominal interval coverage is not guaranteed under serial dependence.

## Two-minute demo script
1. Open Overview and point out the historical label, product, horizon and observed-data timestamps.
2. Show Data quality: one demand gap, complete price coverage, negative values and dataset fingerprints.
3. Compare the validation-selected model with seasonal naive on the held-out period; quote the verified metrics above.
4. Replay a held-out origin and compare its forecast, actual outcome and calibrated interval.
5. Run a zero and nonzero historical-level scenario to show real inference; explain that it is feature sensitivity.
6. Finish with validation permutation importance and the report's operational limitations.

No portfolio site was modified.