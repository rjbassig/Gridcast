"""Rebuild figures, Markdown findings and a typeset PDF from experiment outputs."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from gridcast.data import series

REFERENCES = [
    (
        "CAISO OASIS portal",
        "https://www.caiso.com/systems-applications/portals-applications/open-access-same-time-information-system-oasis",
    ),
    ("CAISO API specification", "https://www.caiso.com/documents/oasisapispecification.pdf"),
    ("CAISO OASIS FAQ", "https://www.caiso.com/documents/oasis-frequently-asked-questions.pdf"),
    ("CAISO terms", "https://www.caiso.com/privacy-terms-of-use"),
    ("EIA-930 methodology", "https://www.eia.gov/electricity/930-content/about.html"),
    ("Open-Meteo historical weather", "https://open-meteo.com/en/docs/historical-weather-api"),
    (
        "NOAA global hourly archive",
        "https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database",
    ),
    (
        "CEC electricity data",
        "https://www.energy.ca.gov/data-reports/energy-almanac/california-electricity-data",
    ),
    ("Forecasting: Principles and Practice - accuracy", "https://otexts.com/fpp3/accuracy.html"),
    ("Conformal prediction introduction", "https://arxiv.org/abs/2107.07511"),
]


def report(root: Path, cfg: dict) -> None:
    reports = root / "reports"
    figures = reports / "figures"
    tables = reports / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(exist_ok=True)
    summary = json.loads((root / "experiments/results/summary.json").read_text())
    scores = pd.DataFrame(summary["leaderboard"])
    test = scores[scores.split == "test"]
    predictions = pd.read_parquet(root / "experiments/results/predictions.parquet")
    demand, price = series(root, "demand"), series(root, "price")
    plt.rcParams.update(
        {
            "figure.facecolor": "#ffffff",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelcolor": "#314e48",
            "axes.titleweight": "bold",
            "grid.alpha": 0.15,
        }
    )
    captions = {}

    def save(name, fig, caption, source="CAISO OASIS; GridCast calculations"):
        fig.text(0.01, 0.015, "Source: " + source, fontsize=7, color="#526861")
        fig.tight_layout(rect=(0, 0.045, 1, 1))
        fig.savefig(figures / f"{name}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)
        captions[name] = caption

    fig, axes = plt.subplots(2, 1, figsize=(10, 6))
    demand.resample("D").mean().plot(ax=axes[0], color="#26755b", lw=1)
    axes[0].set(title="Daily mean CAISO system demand", ylabel="Demand (MW)", xlabel="")
    price.resample("D").mean().plot(ax=axes[1], color="#367a9b", lw=1)
    axes[1].axhline(0, color="#9b4444", lw=0.7)
    axes[1].set(
        title="Daily mean NP15 day-ahead total LMP", ylabel="Price (USD/MWh)", xlabel="UTC delivery date"
    )
    save(
        "market_history",
        fig,
        "Demand and prices are different products and geographies. Daily means summarize hourly observations; one demand gap is not imputed.",
    )
    local = demand.index.tz_convert("America/Los_Angeles")
    frame = pd.DataFrame(
        {
            "value": demand.to_numpy(),
            "hour": local.hour,
            "month": local.month,
            "weekend": local.day_of_week >= 5,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    mat = frame.pivot_table(index="month", columns="hour", values="value", aggfunc="mean")
    img = axes[0].imshow(mat, aspect="auto", cmap="YlGnBu", origin="lower")
    axes[0].set(title="Seasonal load profile", xlabel="Local delivery hour", ylabel="Month")
    axes[0].set_yticks(range(12), range(1, 13))
    fig.colorbar(img, ax=axes[0], label="Mean demand (MW)", shrink=0.8)
    for weekend, color in [(False, "#26755b"), (True, "#c77a3a")]:
        d = frame[frame.weekend == weekend].groupby("hour").value.mean()
        axes[1].plot(d.index, d, label="Weekend" if weekend else "Weekday", color=color)
    axes[1].set(title="Weekday and weekend demand", xlabel="Local delivery hour", ylabel="Mean demand (MW)")
    axes[1].legend(frameon=False)
    save(
        "seasonality",
        fig,
        "Calendar patterns use America/Los_Angeles time. Fall-back hours both contribute; spring-forward hours are absent.",
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].hist(price.dropna(), bins=100, color="#367a9b", alpha=0.9)
    axes[0].set_yscale("log")
    axes[0].set(
        title="Hourly NP15 price distribution",
        xlabel="Total day-ahead LMP (USD/MWh)",
        ylabel="Hours (log scale)",
    )
    price.rolling(168).std().plot(ax=axes[1], color="#c77a3a", lw=0.8)
    axes[1].set(
        title="Rolling weekly price dispersion",
        xlabel="UTC delivery date",
        ylabel="168-hour standard deviation (USD/MWh)",
    )
    save(
        "price_risk",
        fig,
        "Negative values and heavy tails remain in training and evaluation. Dispersion is descriptive, not an ex-ante volatility forecast.",
    )
    weather_path = root / "data/raw/reference/weather.json"
    weather_text = "Weather was not acquired; no weather findings are reported."
    if weather_path.exists():
        w = json.loads(weather_path.read_text())["hourly"]
        temp = pd.Series(w["temperature_2m"], index=pd.to_datetime(w["time"], utc=True), name="temperature")
        joined = pd.concat([demand.rename("demand"), temp, price.rename("price")], axis=1).dropna()
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        scatter = axes[0].hexbin(joined.temperature, joined.demand, gridsize=35, mincnt=1, cmap="YlGnBu")
        fig.colorbar(scatter, ax=axes[0], label="Hours")
        axes[0].set(
            title="Retrospective weather association",
            xlabel="Sacramento reanalysis temperature (C)",
            ylabel="CAISO demand (MW)",
        )
        corr = joined.corr()
        axes[1].imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
        axes[1].set_xticks(range(3), ["Demand", "Temp.", "Price"], rotation=30)
        axes[1].set_yticks(range(3), ["Demand", "Temp.", "Price"])
        for i in range(3):
            for j in range(3):
                axes[1].text(
                    j,
                    i,
                    f"{corr.iloc[i, j]:.2f}",
                    ha="center",
                    va="center",
                    color="white" if abs(corr.iloc[i, j]) > 0.6 else "black",
                )
        axes[1].set_title("Unadjusted hourly correlation")
        save(
            "weather",
            fig,
            "One Sacramento grid cell is an illustrative weather proxy, not load-weighted California weather. Reanalysis is excluded from forecasting; correlations do not identify causal effects.",
            "CAISO OASIS; Open-Meteo historical reanalysis (CC BY 4.0)",
        )
        weather_text = f"The retrospective demand-temperature Pearson correlation is {corr.loc['demand', 'temperature']:.3f} across {len(joined):,} matched hours. This unadjusted association mixes seasons, hours and local conditions; it is not causal."
        corr.to_csv(tables / "retrospective_correlations.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, target in zip(axes, ["demand", "price"]):
        s = test[test.target == target]
        for name in ["persistence", "seasonal_naive", "ridge_100", "xgboost", "lightgbm", "gru"]:
            q = s[s.model == name].sort_values("horizon")
            ax.plot(q.horizon, q.mae, marker="o", ms=3, label=name, lw=1)
        ax.set(
            xscale="log",
            xlabel="Forecast horizon (hours, log scale)",
            ylabel="MAE (MW)" if target == "demand" else "MAE (USD/MWh)",
            title=target.title() + " / held-out accuracy",
        )
        ax.set_xticks([1, 6, 24, 48, 168], ["1", "6", "24", "48", "168"])
        ax.grid(axis="y")
    axes[1].legend(fontsize=7, frameon=False)
    save(
        "accuracy",
        fig,
        "All reported test models use the same eligible origins per target and horizon. Horizon sample counts differ because labels crossing quarter boundaries are excluded.",
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, target in zip(axes, ["demand", "price"]):
        name = summary["selection"][f"{target}_24"]
        p = predictions[
            (predictions.target == target)
            & (predictions.horizon == 24)
            & (predictions.model == name)
            & (predictions.split == "test")
        ].tail(168)
        ax.plot(p.target_time, p.actual, color="#48695e", label="Observed", lw=1)
        ax.plot(p.target_time, p.prediction, color="#157b5c", label="Forecast", lw=1)
        ax.fill_between(p.target_time, p.lower, p.upper, color="#64af91", alpha=0.2, label="90% interval")
        ax.set(
            title=f"{target.title()} / {name} / 24h",
            ylabel="MW" if target == "demand" else "USD/MWh",
            xlabel="UTC delivery date",
        )
        ax.tick_params(axis="x", rotation=35)
    axes[1].legend(fontsize=7, frameon=False)
    save(
        "forecast_replay",
        fig,
        "The last available week is shown for the model selected on validation. Split-conformal bands are calibrated before the quarter, not arbitrarily drawn.",
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, target in zip(axes, ["demand", "price"]):
        q = test[(test.target == target) & test.selected_on_validation].sort_values("horizon")
        ax.bar(range(len(q)), q.coverage, color="#2d8063")
        ax.axhline(0.9, color="#bb6b35", ls="--", label="Nominal 90%")
        ax.set_xticks(range(len(q)), q.horizon.astype(str))
        ax.set(
            ylim=(0, 1),
            xlabel="Forecast horizon (hours)",
            ylabel="Empirical interval coverage",
            title=target.title() + " / validation-selected models",
        )
        ax.legend(fontsize=8, frameon=False)
    save(
        "coverage",
        fig,
        "Serial dependence and distribution shift invalidate a blanket exchangeability guarantee. Empirical coverage, event coverage and interval widths must guide use.",
    )
    importance = pd.read_csv(root / "experiments/results/importance.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, target in zip(axes, ["demand", "price"]):
        q = (
            importance[
                (importance.target == target) & (importance.horizon == 24) & (importance.model == "xgboost")
            ]
            .nlargest(8, "mae_increase")
            .sort_values("mae_increase")
        )
        ax.barh(q.feature, q.mae_increase, color="#2d8063", xerr=q["std"])
        ax.set(
            title=target.title() + " / XGBoost",
            xlabel="Validation MAE increase (MW)"
            if target == "demand"
            else "Validation MAE increase (USD/MWh)",
        )
    save(
        "importance",
        fig,
        "Validation-only permutation importance uses three repeats on a 12-hour subsample. Correlated lags can divide or mask importance; negative values indicate noisy attribution.",
    )
    test.drop(columns=["mae_ci95"]).to_csv(tables / "test_leaderboard.csv", index=False)
    selected = test[test.selected_on_validation].sort_values(["target", "horizon"])
    selected.to_csv(tables / "selected_results.csv", index=False)
    quality = summary["quality"]["targets"]
    peak = quality["demand"]["max"]
    negative = quality["price"]["negative_observations"]
    selected24 = selected[selected.horizon == 24]
    lines = []
    for r in selected24.to_dict("records"):
        base = test[
            (test.target == r["target"]) & (test.horizon == 24) & (test.model == "seasonal_naive")
        ].iloc[0]
        improvement = 100 * (1 - r["mae"] / base.mae)
        lines.append(
            f"{r['target'].title()}: {r['model']} achieves 24-hour held-out MAE {r['mae']:.2f} "
            f"{'MW' if r['target'] == 'demand' else 'USD/MWh'}, {improvement:.1f}% relative MAE reduction versus weekly seasonal naive; "
            f"90% nominal interval coverage is {100 * r['coverage']:.1f}%."
        )
    sections = [
        (
            "Executive summary",
            " ".join(lines)
            + " These are historical research results, not validated live operational performance.",
        ),
        (
            "Business problem",
            "The platform compares forecasting strategies for planning research, peak-load awareness and market risk analysis. It does not implement dispatch optimization, trading execution or procurement cost minimization. No dollar savings are claimed.",
        ),
        (
            "California electricity market background",
            "CAISO actual integrated load measures its balancing-area demand and excludes other California balancing authorities. NP15 total day-ahead LMP is a hub price in USD/MWh; it is neither a statewide retail rate nor real-time settlement price. OASIS labels the price value column MW; normalization corrects its unit using the market product definition [1-3].",
        ),
        (
            "Research objectives",
            "Evaluate direct predictions 1, 6, 24, 48 and 168 hours after an explicit hourly UTC issue timestamp. Compare simple baselines with statistical autoregression, linear regression, boosted trees and a small GRU under an expanding-origin protocol.",
        ),
        (
            "Data sources",
            "The primary inputs are CAISO SLD_FCST/ACTUAL for CA ISO-TAC and PRC_LMP/DAM, total LMP only, for TH_NP15_GEN-APND [1-3]. EIA-930 access was verified on a 48-hour CISO sample; it is not silently merged or substituted [5]. Open-Meteo Sacramento reanalysis supports explanatory plots only [6]. NOAA and CEC were researched as future complementary sources [7-8].",
        ),
        (
            "Data acquisition",
            "The executed window is 2024-01-01 00:00 UTC through 2026-01-01 exclusive. OASIS responses are downloaded in 28-day chunks, validated as ZIP/CSV, retained with URL, acquisition time and SHA-256, and skipped on repeat ingestion only when their checksum matches. HTTP retries handle rate limits and transient server failures. Longer OASIS windows are possible using historical bulk archives; this two-year window balances market comparability and laptop workloads.",
        ),
        (
            "Data quality assessment",
            f"Demand has {quality['demand']['rows']:,} / {quality['demand']['expected_rows']:,} expected hours; the missing interval starts 2024-08-31 17:00 UTC. Price has {quality['price']['rows']:,} / {quality['price']['expected_rows']:,} expected hours. Duplicate timestamps and invalid interval lengths cause errors. IQR flags are descriptive and do not delete extremes. Observed demand peaks at {peak:,.0f} MW; {negative:,} hourly day-ahead prices are negative.",
        ),
        (
            "Exploratory data analysis",
            weather_text
            + " Seasonal and intraday summaries are computed using local market time. Price tails and rolling dispersion are inspected without clipping. Two years do not establish a long-run structural demand trend. Renewable generation, net load and multi-hub comparisons are outside the executed scope.",
        ),
        (
            "Forecasting problem formulation",
            "For issue time t and horizon h, the target is y(t+h), where timestamps identify interval starts. Each horizon has its own fitted direct model. Demand y(s) is assumed usable at s+3h (two hours after interval end); price y(s) is deliberately withheld until s+48h. These are conservative assumptions, not verified publication vintages. For day-ahead LMP, some short-horizon targets may already be public at t; this is delivery-anchored statistical research, not a market gate-closure submission backtest.",
        ),
        (
            "Feature engineering",
            "Ten historical lags are offset by the target-specific availability delay: delay + {0,1,2,3,6,12,24,48,72,168} hours. Rolling means and standard deviations use 24/168 hours ending at the latest assumed available observation. Calendar sin/cos terms encode target local hour, weekday and day of year; weekend is binary. A weekly UTC anchor repeats the most recent fully available weekly profile. It does not correct seasonal-naive DST phase shifts. Holiday, renewable and weather-forecast predictors are deferred.",
        ),
        (
            "Leakage prevention",
            "Every fit label is assumed published before calibration starts; every calibration label is published before the evaluation quarter. Automated tests mutate all unavailable observations and verify that issue-time features stay identical for every horizon/delay pair. Rolling windows are shifted before aggregation. Realized future weather and outcomes never enter the predictor matrix. Retrospective corrected CAISO values may still differ from what was available historically; strict revision-vintage leakage cannot be ruled out.",
        ),
        (
            "Experimental design",
            "2024 initializes training. January-March and April-June 2025 are validation folds; July-September and October-December are final test folds. Models refit at each quarter using an expanding window, with stride three for CPU efficiency. The final quarter may incorporate previous-quarter labels once available, as a real expanding-origin evaluation would. It never retunes hyperparameters from those test results. Origins whose labels cross quarter boundaries are excluded. All candidate models share origins within a target/horizon.",
        ),
        (
            "Baseline models",
            "Persistence repeats the latest assumed available observation. Seasonal naive uses the latest available matching UTC weekly hour, repeating a week when horizon plus delay exceeds 168 hours. Historical mean and weekday/hour calendar means use fit data only. A baseline can win model selection; the application never forces a complex model to appear superior.",
        ),
        (
            "Statistical models",
            "The executed statistical comparator is a regularized direct seasonal autoregression over lag and weekly-anchor terms, without calendar predictors. It is not a SARIMA model. ARIMA/SARIMA, SARIMAX and exponential smoothing were considered but not executed in this release; state-space specification and repeated refits would require a separately budgeted comparison. No results are attributed to unrun models.",
        ),
        (
            "Machine learning models",
            "Ridge standardizes all features using fit data and compares alpha 1 vs 100. XGBoost uses 140 trees, depth four, learning rate .05, squared-error loss and two CPU threads. LightGBM uses 140 trees, depth five, 24 leaves, learning rate .05 and two CPU threads. Random forests were not added because two distinct boosted-tree implementations already provide nonlinear comparisons. The registry records the exact fitted estimator parameters.",
        ),
        (
            "Deep learning models",
            "The executed PyTorch GRU reads ten irregular lags ordered oldest to newest. Its 24-dimensional final hidden state is concatenated with standardized rolling/calendar context and passed through a linear output head. This is a sparse lag sequence, not a regularly sampled 168-step sequence. Five epochs use Adam (.003), batches of 256, MSE loss, gradient clipping at one, seed 42 and CPU execution. Standardization and target scaling fit on training only. LSTM, TCN and TFT are deferred, not claimed.",
        ),
        (
            "Hyperparameter optimization",
            "The bounded validation search compares two ridge penalties and fixed predeclared structural choices for all other candidates. Selection minimizes mean quarterly validation MAE independently by target/horizon and is persisted before that combination's first test fold. This is intentionally modest tuning, not an exhaustive optimization study. The full configuration and checksum are stored with results.",
        ),
        (
            "Walk-forward validation",
            "At each quarterly refit, a contiguous pre-fold calibration block of 720 eligible hourly issues is held out. Its end is offset from the fold by horizon + publication delay. Fit labels are purged at calibration start, preventing training targets from overlapping calibration availability. Quarterly retraining holds the fitted mapping fixed within each fold while features update hourly. These are repeated historical direct forecasts, not recursive trajectories.",
        ),
        (
            "Evaluation metrics",
            "MAE = mean absolute error. RMSE = square root of mean squared error. Bias = mean(prediction - actual). sMAPE = mean(200 times absolute error / (absolute actual + absolute prediction)), with both-zero pairs set to zero. MASE divides MAE by pre-evaluation weekly seasonal absolute differences [9]. Fold-level MASE scales expand; summary MASE uses the fixed pre-validation or pre-test history. Negative prices are supported. Near-zero prices make sMAPE secondary; 95th-percentile absolute error and event segments assess tails.",
        ),
        (
            "Experimental results",
            " ".join(lines)
            + " Complete per-model, per-horizon metrics, runtime and block-bootstrap MAE intervals are stored in experiments/results/summary.json. The interval on mean absolute error resamples contiguous groups of 168 ordered predictions (500 draws); it is approximate and does not establish economic value.",
        ),
        (
            "Model comparison",
            "Tables report every candidate, including weak models. Selection uses validation performance, while test tables provide an honest final comparison. A different model winning a test column does not authorize retrospective reselection. A seven-day horizon is one point prediction at t+168h, not a seven-day optimized load schedule.",
        ),
        (
            "Forecast error analysis",
            "Segments report season, local hour, weekday/weekend, high-value observations and large hourly changes. High-value thresholds are the 95th percentile of pre-fold history; volatility events use the 95th percentile of past absolute hourly changes. These are post-outcome diagnostic slices, not predictors. The H2 test only covers summer, fall and part of winter; it cannot establish spring test reliability. Extreme-weather-stratified performance remains unimplemented.",
        ),
        (
            "Model explainability",
            "Validation-only permutation importance reports MAE increases after feature shuffling, with three repeats and a 12-hour sample stride. The dashboard permits model/horizon selection. SHAP and partial-dependence studies are deferred. Shuffling correlated time-series lags can create unrealistic combinations, so importances are diagnostic predictive associations rather than independent effects or causal drivers.",
        ),
        (
            "Forecast uncertainty",
            "Split-conformal intervals add/subtract a pre-fold absolute-residual quantile with finite-sample rank correction [10]. Calibration is separate from fitting; its labels are available before each forecast fold. Nominal coverage is 90%. Report empirical coverage, widths and segment coverage. Time dependence, market shift and event rarity mean the usual exchangeability guarantee should not be asserted. Scenario predictions do not inherit these bands.",
        ),
        (
            "Scenario analysis",
            "The API scales historical lag levels, rolling means, standard deviations and the weekly anchor by 1 plus a user-selected percentage, then recomputes the prediction using the same eligible model artifact. Zero perturbation reproduces the stored forecast. This is a hypothetical feature sensitivity experiment; it is not a validated temperature response, renewable dispatch model or causal policy simulator.",
        ),
        (
            "Operational applications",
            "Supported uses are historical method comparison, peak-error assessment, demand planning research and price-risk monitoring research. Planning relevance must be assessed from the exact horizon and availability assumptions. Forecast errors are not converted to dollars because no procurement policy, settlement model or validated trading strategy exists.",
        ),
        (
            "Limitations",
            "The application is a tested local research release, not a production-certified forecasting service. Limitations include two years, a single price hub, revision-vintage uncertainty, assumed publication delays, short-horizon DAM targets possibly already public, no archived weather forecasts, limited tuning, coarse quarterly retraining, time-dependent conformal residuals, and no renewable or holiday covariates. No deployed status is claimed.",
        ),
        (
            "Future improvements",
            "Prioritize archived issue-time publication vintages and gate-closure-aware DAM evaluation, then population/load-weighted weather forecast archives, regional prices, renewable generation and net-load features. Add untouched prospective evaluation, drift alerts with calibrated thresholds, scheduled jobs with lock/atomic promotion, live inference and controlled public deployment. Compare SARIMAX/ETS and larger neural models only if their incremental value justifies laptop cost.",
        ),
        (
            "Conclusion",
            "GridCast now executes an authentic-data acquisition-to-evaluation pipeline and serves artifact-backed historical inference with explicit provenance. Its strongest contribution is a reproducible, inspectable comparison under stated information assumptions. Operational readiness requires prospective validation and the unresolved data-vintage work.",
        ),
        (
            "References",
            "References below link to official source documentation and methodological material. Data remain governed by source-specific terms; the repository's code license does not relicense CAISO or weather data.",
        ),
    ]
    markdown = [
        "# GridCast: A Reproducible Framework for California Electricity Demand and Price Forecasting",
        "",
        "Research release 0.1 | Generated from executed experiments",
        "",
        "## Verified 24-hour results",
        *["- " + s for s in lines],
        "",
    ]
    for i, (heading, body) in enumerate(sections, 1):
        markdown.extend([f"## {i}. {heading}", "", body, ""])
    markdown.extend([f"{i}. [{title}]({url})" for i, (title, url) in enumerate(REFERENCES, 1)])
    (reports / "gridcast_report.md").write_text("\n".join(markdown))
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Cover",
            fontName="Helvetica-Bold",
            fontSize=42,
            leading=46,
            textColor=colors.HexColor("#154e3e"),
            spaceAfter=24,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubtitleGC", fontSize=19, leading=27, textColor=colors.HexColor("#354c44"), spaceAfter=20
        )
    )
    styles["Heading1"].textColor = colors.HexColor("#175e49")
    styles["Heading1"].fontSize = 16
    styles["Heading1"].leading = 20
    styles["BodyText"].fontSize = 9.5
    styles["BodyText"].leading = 14
    styles["BodyText"].spaceAfter = 10
    styles.add(
        ParagraphStyle(
            name="CaptionGC", fontSize=8, leading=11, textColor=colors.HexColor("#52675d"), spaceAfter=12
        )
    )
    story = [
        Spacer(1, 0.5 * inch),
        Paragraph("GRIDCAST", styles["Cover"]),
        Paragraph(
            "A Reproducible Framework for California Electricity Demand and Price Forecasting",
            styles["SubtitleGC"],
        ),
        Paragraph("APPLIED ENERGY ANALYTICS / RESEARCH RELEASE 0.1", styles["Heading3"]),
        Spacer(1, 0.3 * inch),
        Paragraph(
            "Real CAISO observations. Explicit forecast origins. Measured performance.", styles["BodyText"]
        ),
        Spacer(1, 0.3 * inch),
    ]
    for line in lines:
        story.append(Paragraph(escape(line), styles["BodyText"]))
    story.extend(
        [
            Spacer(1, 0.25 * inch),
            Paragraph(
                "Historical dataset: 2024-2025. Final held-out issues: July-December 2025. Local CPU experiments. No live deployment or financial savings claimed.",
                styles["CaptionGC"],
            ),
            PageBreak(),
        ]
    )
    image_sections = {
        8: ["market_history", "seasonality", "price_risk", "weather"],
        20: ["accuracy"],
        21: ["forecast_replay"],
        23: ["importance"],
        24: ["coverage"],
    }
    for i, (heading, body) in enumerate(sections, 1):
        story.append(
            KeepTogether(
                [
                    Paragraph(f"{i:02d} / {escape(heading)}", styles["Heading1"]),
                    Paragraph(escape(body), styles["BodyText"]),
                ]
            )
        )
        if i == 7:
            rows = [["Target", "Observed hours", "Missing", "Min", "Max"]]
            for target, q in quality.items():
                rows.append(
                    [
                        target,
                        f"{q['rows']:,}",
                        str(q["missing_hours"]),
                        f"{q['min']:,.2f}",
                        f"{q['max']:,.2f}",
                    ]
                )
            story[-1:] = [KeepTogether(story[-1:] + [styled_table(rows, [70, 110, 65, 100, 100])])]
        if i == 20:
            for target in ["demand", "price"]:
                story.append(Paragraph(target.title() + " / validation-selected models", styles["Heading3"]))
                rows = [["Horizon", "Model", "MAE", "RMSE", "Bias", "Coverage"]]
                for r in selected[selected.target == target].to_dict("records"):
                    rows.append(
                        [
                            str(r["horizon"]) + "h",
                            r["model"],
                            f"{r['mae']:.2f}",
                            f"{r['rmse']:.2f}",
                            f"{r['bias']:.2f}",
                            f"{100 * r['coverage']:.1f}%",
                        ]
                    )
                story.append(styled_table(rows, [55, 105, 75, 75, 65, 70]))
                story.append(Spacer(1, 12))
        for name in image_sections.get(i, []):
            if name not in captions:
                continue
            path = figures / f"{name}.png"
            from PIL import Image as PILImage

            width, height = PILImage.open(path).size
            image = Image(str(path), width=6.25 * inch, height=6.25 * inch * height / width)
            story.append(KeepTogether([image, Paragraph(escape(captions[name]), styles["CaptionGC"])]))
        if i in [8, 12, 18, 29]:
            story.append(PageBreak())
    for i, (title, url) in enumerate(REFERENCES, 1):
        story.append(
            Paragraph(
                f'{i}. {escape(title)}<br/><link href="{url}" color="#1b6750">{escape(url)}</link>',
                styles["CaptionGC"],
            )
        )

    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#bcd2c6"))
        canvas.line(48, 40, 564, 40)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#4d6a5c"))
        canvas.drawString(48, 28, "GRIDCAST | REPRODUCIBLE ENERGY RESEARCH | CAISO 2024-2025")
        canvas.drawRightString(564, 28, str(doc.page))

    SimpleDocTemplate(
        str(reports / "gridcast_report.pdf"),
        pagesize=(612, 792),
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=55,
        title="GridCast - California Electricity Forecasting",
        author="GridCast Research",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    portfolio = [
        "# Review-ready portfolio materials",
        "",
        "## Concise description",
        "Built a standalone California energy forecasting research platform using real CAISO demand and NP15 day-ahead prices, leakage-aware historical validation, fitted-model replay, and measured forecast uncertainty.",
        "",
        "## Case study",
        "Acquired two years of hourly source data in retryable, checksummed batches; normalized market identifiers, units, UTC timestamps and local DST calendar features. Compared four baselines, two ridge settings, seasonal autoregression, XGBoost, LightGBM and a small PyTorch GRU at five direct horizons. Validation chose models independently for demand and price, and final held-out results remained separate from tuning.",
        "",
        *lines,
        "",
        "The dashboard exposes historical exploration, model comparisons, uncertainty, model sensitivity and quality reports through FastAPI. Publication times are conservative assumptions and historical revisions remain a limitation. This is a local research release; no public deployment or trading optimization is claimed.",
        "",
        "## Three resume bullets",
        f"- Engineered reproducible CAISO ingestion and Parquet/DuckDB storage for {quality['demand']['rows'] + quality['price']['rows']:,} authentic hourly demand and day-ahead LMP records, preserving a known demand gap and negative prices.",
        "- Implemented five-horizon expanding-origin evaluation across statistical, boosted-tree and PyTorch models, with publication-delay checks, separate conformal calibration, validation-based selection and a held-out half-year.",
        "- Delivered FastAPI artifact-backed inference and a responsive Next.js research terminal with forecast replay, empirical interval coverage, permutation importance and model-connected sensitivity scenarios.",
        "",
        "## Technical interview explanation",
        "Start with the information set at issue time. Each horizon has a direct target; all observed predictors are delayed, fit labels are purged before calibration, and calibration labels precede the evaluation fold. Explain that corrected historical values are still not authentic vintages. Describe why the simple weekly baseline is necessary, why short-horizon day-ahead prices require a gate-closure-aware future study, and why nominal interval coverage is not guaranteed under serial dependence.",
        "",
        "## Two-minute demo script",
        "1. Open Overview and point out the historical label, product, horizon and observed-data timestamps.",
        "2. Show Data quality: one demand gap, complete price coverage, negative values and dataset fingerprints.",
        "3. Compare the validation-selected model with seasonal naive on the held-out period; quote the verified metrics above.",
        "4. Replay a held-out origin and compare its forecast, actual outcome and calibrated interval.",
        "5. Run a zero and nonzero historical-level scenario to show real inference; explain that it is feature sensitivity.",
        "6. Finish with validation permutation importance and the report's operational limitations.",
        "",
        "No portfolio site was modified.",
    ]
    (root / "docs/portfolio_materials.md").write_text("\n".join(portfolio))
    (reports / "verified_findings.json").write_text(
        json.dumps({"24h_findings": lines, "selected_results": selected.to_dict("records")}, indent=2)
    )


def styled_table(rows, widths):
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#174f3f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#eef5f0"), colors.white]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#174f3f")),
            ]
        )
    )
    return table
