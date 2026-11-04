# Forecast protocol and feature availability contract

Canonical observation time `s` is the **start** of a one-hour delivery interval. Forecast issue is `t`; target is `y(t+h)`. Direct horizons are 1, 6, 24, 48 and 168 elapsed UTC hours. The last is a single week-ahead point, not a full future trajectory. Features are target-specific; demand and prices are never accidentally mixed.

| Feature | Source time | Assumed available | Construction at issue t | Horizon use |
|---|---|---|---|---|
| Demand lag | CAISO ACTUAL interval start s | s + 3h | s = t - 3h - lag | all demand horizons |
| Price lag | NP15 DAM delivery start s | s + 48h | s = t - 48h - lag | all price horizons |
| Rolling mean/std | Historical target observations | newest s + delay | trailing 24 / 168 observations ending at t-delay | all |
| Seasonal anchor | Historical target at s | s + delay | s=t+h-ceil((h+delay)/168)*168 | all |
| Calendar | Target time t+h | known before issue | local-hour/day/year sin/cos and weekend | all |
| Label | Delivery start t+h | t+h+delay assumed | never a predictor; used for supervised fit/evaluation | direct |
| Weather reanalysis | Open-Meteo valid time s | publication vintage unavailable | **EDA only** | excluded |

Actual original publication/revision timestamps are not supplied in these OASIS extracts. `available_at` is a documented conservative assumption, not source-verified vintage metadata. Downloads in November 2026 may contain revisions unknown in 2024/2025. Thus this is availability-aware historical research, not a claim of a strict point-in-time production dataset.

For demand, the assumed three-hour interval-start delay is two hours after interval completion. DAM prices often publish before delivery, but the code conservatively withholds them until 48 hours after delivery. Consequently, short-horizon DAM target values may already be public at issue time. Those experiments are delivery-anchored statistical comparisons, not an actionable auction submission strategy. A future DAM experiment must use actual clearing/publication dates and market gate closure.

## Time and missingness

UTC is canonical and elapsed horizons are unambiguous. Local features use `America/Los_Angeles`; repeated fall hours retain different offsets, and spring gaps are not manufactured. OASIS source interval starts/ends are validated as one hour. A duplicate target timestamp fails rather than guessing which revision wins. One missing demand hour is left absent in Parquet, expanded to NaN in the hourly series, and invalid feature/label rows are dropped consistently across all models. Price outliers and negative prices are retained. Seasonal naive uses UTC weekly matching, with its DST limitation reported.

## Experimental chronology

2024 initializes the expanding window. Validation issues occupy Jan–Mar and Apr–Jun 2025. Test issues occupy Jul–Sep and Oct–Dec 2025. Each fold reserves a 720-hour calibration block ending horizon+delay before its start. Only fit labels published by calibration start may train the model; only calibration labels published by fold start may calibrate. Eligible issue labels must be within their evaluation quarter. Retraining in October can use earlier test outcomes **only for fitting**, with unchanged candidate specifications and no retuning. This simulates expanding retraining and is not future-label leakage.

Training uses every third eligible hour, seed 42. Ridge alpha candidates are 1 and 100; boosted-tree and GRU structures are predeclared. Model identity is selected independently by target/horizon using the mean MAE of the two validation quarters. Selection is frozen before evaluating that combination on test. Every candidate is reported, and a test winner does not replace the validation-selected choice.

## Model details

- Four baselines: persistence, latest available weekly profile (extended periodically if necessary), fit historical average and fit local weekday/hour average.
- Seasonal AR: direct regression on available historical lag/weekly terms; ridge alpha 100 stabilizes correlated inputs. This is not ARIMA/SARIMA.
- Ridge: training-only standardization; full feature set; separate alpha 1 and 100 candidates.
- XGBoost: 140 trees, max depth 4, learning rate .05, squared error, two threads.
- LightGBM: 140 trees, depth 5, 24 leaves, learning rate .05, two threads.
- GRU: ten irregular historical lag observations oldest-to-newest, one input channel, hidden size 24; final hidden state plus rolling/calendar context to one linear output. Adam .003, MSE, five epochs, batch 256, clip norm 1, CPU threads 2. Training-only target scaling and input standardization.

ARIMA/SARIMA/SARIMAX/ETS, random forest, LSTM, TCN and TFT were not executed; there are no invented results for them. More architectures do not resolve the dataset-vintage limitation.

## Uncertainty and metrics

Symmetric split-conformal residual radius uses pre-fold calibration errors and finite-sample quantile rank correction. Nominal 90% coverage is assessed on test, overall and by season/hour/day/event. Time dependence and distribution shift mean exchangeability cannot be assumed; empirical coverage may be below nominal. No calibrated intervals are claimed for hypothetical scenarios.

MAE/RMSE are primary. Bias is prediction minus actual. sMAPE is 200|error|/(|actual|+|prediction|), both-zero pairs zero. MASE denominator uses only past weekly differences: expanding pre-fold history for fold tables, fixed pre-validation or pre-test history for aggregate summaries. Price sMAPE is unstable near zero, so report tail absolute error too. Approximate MAE 95% intervals resample ordered 168-prediction blocks, 500 draws. They are not confidence intervals on business savings or guaranteed model improvements.

Peak/high-value and large-hourly-change thresholds use the 95th percentile of pre-fold observations or absolute differences. Event membership is a diagnostic based on the outcome, never a forecast input. H2 test does not cover spring. Weather-event performance, causal sensitivities, policy value and dollar savings are not established.

## Explainability and scenarios

Permutation importance uses validation calibration data only, three repeats, stride 12 and MAE scoring. Correlated lags and unrealistic shuffled combinations limit interpretation. SHAP is not implemented.

Scenario analysis scales historical lag values, rolling means, rolling deviations and weekly anchor by 1+pct/100, then recomputes the same eligible artifact. Calendar values stay fixed. Zero perturbation must reproduce the stored forecast. This is a hypothetical feature sensitivity, not a real future weather or demand intervention.
