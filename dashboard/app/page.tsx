"use client";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Database,
  FlaskConical,
  Layers,
  ShieldCheck,
  Zap,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  BarChart,
  Bar,
} from "recharts";

type Target = "demand" | "price";
type Point = {
  timestamp?: string;
  target_time?: string;
  value?: number;
  actual?: number;
  prediction?: number;
  lower?: number;
  upper?: number;
};
type Score = {
  model: string;
  split: string;
  mae: number;
  rmse: number;
  bias: number;
  coverage: number;
  training_seconds: number;
  selected_on_validation: boolean;
};
type Quality = {
  rows: number;
  expected_rows: number;
  missing_hours: number;
  start: string;
  end: string;
  min: number;
  max: number;
  negative_observations: number;
  dataset_sha256: string;
  last_acquisition: string;
};
type Overview = {
  latest: Record<Target, { value: number; timestamp: string }>;
  selection: Record<string, string>;
  replay_only: boolean;
  quality: { targets: Record<Target, Quality> };
};
const tabs = [
  "Overview",
  "Historical explorer",
  "Forecast lab",
  "Model comparison",
  "Scenario analysis",
  "Explainability",
  "Data quality",
  "Research findings",
];
const fmt = (n: number | undefined, d = 0) =>
  n === undefined
    ? "—"
    : n.toLocaleString("en-US", { maximumFractionDigits: d });
async function get<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(
    path,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  if (!r.ok) {
    const j = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(
      typeof j.detail === "string"
        ? j.detail
        : JSON.stringify(j.detail || r.statusText),
    );
  }
  return r.json();
}
function Chart({
  data,
  history = false,
  unit,
}: {
  data: Point[];
  history?: boolean;
  unit: string;
}) {
  return (
    <div
      className="chart"
      role="img"
      aria-label={`${history ? "Historical observations" : "Held-out actuals and forecasts"} in ${unit}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke="#203331" vertical={false} />
          <XAxis
            dataKey={history ? "timestamp" : "target_time"}
            tickFormatter={(v) =>
              new Date(v).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })
            }
            minTickGap={65}
            stroke="#819b96"
            fontSize={11}
          />
          <YAxis
            width={65}
            tickFormatter={(v) => fmt(v)}
            domain={["auto", "auto"]}
            stroke="#819b96"
            fontSize={11}
          />
          <Tooltip
            contentStyle={{
              background: "#11221f",
              border: "1px solid #34514a",
              borderRadius: 8,
            }}
            labelFormatter={(v) => new Date(String(v)).toLocaleString()}
          />
          <Legend />
          {history ? (
            <Line
              type="monotone"
              dataKey="value"
              name={unit}
              stroke="#bcf57a"
              dot={false}
              strokeWidth={2}
            />
          ) : (
            <>
              <Line
                dataKey="actual"
                name="Observed"
                stroke="#789b92"
                dot={false}
              />
              <Line
                dataKey="prediction"
                name="Forecast"
                stroke="#bcf57a"
                dot={false}
                strokeWidth={2}
              />
              <Line
                dataKey="lower"
                name="90% interval · lower"
                stroke="#4e8b7b"
                dot={false}
                strokeDasharray="3 4"
              />
              <Line
                dataKey="upper"
                name="90% interval · upper"
                stroke="#4e8b7b"
                dot={false}
                strokeDasharray="3 4"
              />
            </>
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export default function Terminal() {
  const [tab, setTab] = useState("Overview"),
    [target, setTarget] = useState<Target>("demand"),
    [horizon, setHorizon] = useState(24),
    [overview, setOverview] = useState<Overview>(),
    [scores, setScores] = useState<Score[]>([]),
    [replay, setReplay] = useState<Point[]>([]),
    [history, setHistory] = useState<Point[]>([]),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [loading, setLoading] = useState(true),
    [model, setModel] = useState(""),
    [origins, setOrigins] = useState<string[]>([]),
    [origin, setOrigin] = useState(""),
    [forecast, setForecast] = useState<Record<string, unknown>>(),
    [change, setChange] = useState(5),
    [scenario, setScenario] = useState<{
      baseline: number;
      scenario: number;
      delta: number;
      limitation: string;
    }>(),
    [importance, setImportance] = useState<
      { feature: string; mae_increase: number }[]
    >([]),
    [start, setStart] = useState("2025-12-01"),
    [end, setEnd] = useState("2026-01-01");
  const unit = target === "demand" ? "MW" : "USD/MWh";
  const replayOnly = overview?.replay_only ?? false;
  const error = Object.values(errors)[0] || "";
  const setRequestError = (request: string, message?: string) => {
    setErrors((current) => {
      const next = { ...current };
      if (message) next[request] = message;
      else delete next[request];
      return next;
    });
  };
  useEffect(() => {
    get<Overview>("/api/overview")
      .then((value) => {
        setRequestError("overview");
        setOverview(value);
      })
      .catch((e) => setRequestError("overview", e.message));
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setRequestError("selection");
    setForecast(undefined);
    setScenario(undefined);
    Promise.all([
      get<Score[]>(`/api/comparisons?target=${target}&horizon=${horizon}`),
      get<Point[]>(`/api/replay?target=${target}&horizon=${horizon}`),
      get<{ origins: string[]; models: string[] }>(
        `/api/origins?target=${target}&horizon=${horizon}`,
      ),
    ])
      .then(([s, r, o]) => {
        if (active) {
          setRequestError("selection");
          setScores(s);
          setReplay(r);
          setOrigins(o.origins);
          setOrigin(o.origins.at(-1) || "");
          setModel(
            s.find((x) => x.selected_on_validation)?.model || "ridge_100",
          );
        }
      })
      .catch((e) => {
        if (active) setRequestError("selection", e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [target, horizon]);
  useEffect(() => {
    let active = true;
    get<{ rows: Point[] }>(
      `/api/history/${target}?start=${start}T00:00:00Z&end=${end}T00:00:00Z&limit=20000`,
    )
      .then((j) => {
        if (active) {
          setRequestError("history");
          setHistory(j.rows);
        }
      })
      .catch((e) => {
        if (active) setRequestError("history", e.message);
      });
    return () => {
      active = false;
    };
  }, [target, start, end]);
  useEffect(() => {
    let active = true;
    get<{ rows: { feature: string; mae_increase: number }[] }>(
      `/api/importance?target=${target}&horizon=${horizon}&model_name=${model}`,
    )
      .then((j) => {
        if (active) {
          setRequestError("importance");
          setImportance(j.rows.slice(0, 10));
        }
      })
      .catch((e) => {
        if (active) setRequestError("importance", e.message);
      });
    return () => {
      active = false;
    };
  }, [target, horizon, model]);
  useEffect(() => {
    if (!model) return;
    let active = true;
    get<Point[]>(
      `/api/replay?target=${target}&horizon=${horizon}&model_name=${model}`,
    )
      .then((r) => {
        if (active) {
          setRequestError("replay");
          setReplay(r);
        }
      })
      .catch((e) => {
        if (active) setRequestError("replay", e.message);
      });
    return () => {
      active = false;
    };
  }, [target, horizon, model]);
  async function execute(isScenario = false) {
    setRequestError("action");
    try {
      const body = { target, horizon, model, issue_time: origin };
      if (isScenario) {
        setScenario(
          await get("/api/scenario", {
            ...body,
            historical_level_change_pct: change,
          }),
        );
      } else if (replayOnly) {
        const rows = await get<Point[]>(
          `/api/replay?target=${target}&horizon=${horizon}&model_name=${encodeURIComponent(model)}&issue_time=${encodeURIComponent(origin)}&limit=1`,
        );
        if (!rows[0]) throw new Error("No stored held-out forecast is available for that selection.");
        setForecast(rows[0] as Record<string, unknown>);
      } else {
        setForecast(await get("/api/forecast", body));
      }
    } catch (e) {
      setRequestError("action", (e as Error).message);
    }
  }
  const selected = scores.find(
    (s) => s.selected_on_validation && s.split === "test",
  );
  const controls = (
    <div className="controls">
      <label>
        MODEL
        <select
          value={model}
          onChange={(e) => {
            setModel(e.target.value);
            setScenario(undefined);
            setForecast(undefined);
          }}
        >
          {scores
            .filter((s) => s.split === "test")
            .map((s) => (
              <option key={s.model}>{s.model}</option>
            ))}
        </select>
      </label>
      <label>
        ELIGIBLE ISSUE TIME (UTC)
        <select
          value={origin}
          onChange={(e) => {
            setOrigin(e.target.value);
            setScenario(undefined);
            setForecast(undefined);
          }}
        >
          {origins.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/">
          <span>
            <Zap size={22} />
          </span>{" "}
          GRIDCAST<i>RESEARCH TERMINAL</i>
        </a>
        <div className="navlabel">WORKSPACE</div>
        <nav>
          {tabs.map((t, i) => (
            <button
              key={t}
              className={t === tab ? "active" : ""}
              onClick={() => setTab(t)}
            >
              <span className="navicon">
                {i === 0 ? (
                  <Activity size={16} />
                ) : i === 1 ? (
                  <Database size={16} />
                ) : i === 2 ? (
                  <FlaskConical size={16} />
                ) : i === 6 ? (
                  <ShieldCheck size={16} />
                ) : (
                  <Layers size={16} />
                )}
              </span>
              {t}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="dot" /> LOCAL RESEARCH ENVIRONMENT
          <p>
            CAISO · California
            <br />
            Historical data / 2024–2025
          </p>
          <small>Results, never simulated observations.</small>
        </div>
      </aside>
      <main>
        <header>
          <span>
            ENERGY INTELLIGENCE <span className="slash">/</span> CALIFORNIA
          </span>
          <div className="badge">
            <span className="dot" /> HISTORICAL REPLAY
          </div>
        </header>
        <div className="title-row">
          <div>
            <div className="eyebrow">CAISO / NP15 DAY-AHEAD MARKET</div>
            <h1>{tab === "Overview" ? "The grid, in perspective." : tab}</h1>
            <p className="sub">
              Observed markets. Measured forecasts. Explicit uncertainty.
            </p>
          </div>
          <div className="selectors">
            <label>
              TARGET
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value as Target)}
              >
                <option value="demand">System demand</option>
                <option value="price">NP15 day-ahead LMP</option>
              </select>
            </label>
            <label>
              HORIZON
              <select
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
              >
                {[1, 6, 24, 48, 168].map((h) => (
                  <option key={h} value={h}>
                    {h === 168 ? "7 days" : `${h} hours`}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {error && (
          <div role="alert" className="error">
            {error} · The dashboard could not load verified research data.
          </div>
        )}
        {loading && (
          <div role="status" className="notice">
            Loading verified experiment outputs…
          </div>
        )}
        {tab === "Overview" && (
          <>
            <div className="kpis">
              <article>
                <div className="metric-label">
                  LAST OBSERVED DEMAND <Zap size={14} />
                </div>
                <strong>
                  {fmt(overview?.latest.demand.value)}
                  <small> MW</small>
                </strong>
                <p>
                  {overview?.latest.demand.timestamp.slice(0, 16) ||
                    "Awaiting data"}{" "}
                  UTC
                </p>
              </article>
              <article>
                <div className="metric-label">
                  NP15 DAY-AHEAD PRICE <ArrowUpRight size={14} />
                </div>
                <strong>
                  {fmt(overview?.latest.price.value, 2)}
                  <small> $/MWh</small>
                </strong>
                <p>Total locational marginal price · DAM</p>
              </article>
              <article>
                <div className="metric-label">
                  HELD-OUT MAE <Activity size={14} />
                </div>
                <strong>
                  {fmt(selected?.mae, 2)}
                  <small> {unit}</small>
                </strong>
                <p>{selected?.model || "—"} · selected on validation</p>
              </article>
              <article>
                <div className="metric-label">
                  90% INTERVAL COVERAGE <ShieldCheck size={14} />
                </div>
                <strong>
                  {selected ? fmt(selected.coverage * 100, 1) : "—"}
                  <small> %</small>
                </strong>
                <p>Empirical coverage · not a guarantee</p>
              </article>
            </div>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>Demand & market outlook</h2>
                  <p>
                    {horizon}h direct forecast · final available week · {unit}
                  </p>
                </div>
                <span className="tag">HELD-OUT / 2025 H2</span>
              </div>
              <Chart data={replay} unit={unit} />
              <div className="chart-footer">
                SOURCE: CAISO OASIS{" "}
                <span>
                  Prediction bands: pre-fold split conformal · availability
                  delays enforced
                </span>
              </div>
            </section>
            <div className="bottom-grid">
              <section className="panel">
                <h2>A measured research system</h2>
                <p>
                  Expanding-window experiments compare calendar baselines,
                  regularized models, boosted trees and a small recurrent
                  network. Every chart reads from actual observations or stored
                  predictions.
                </p>
                <button
                  className="text-button"
                  onClick={() => setTab("Model comparison")}
                >
                  Explore model performance <ArrowUpRight size={14} />
                </button>
              </section>
              <section className="panel">
                <h2>Know the boundary</h2>
                <p>
                  Demand covers CAISO, not all California. Price is one
                  day-ahead trading hub, not real-time settlement. Historical
                  revisions and assumed publication delays limit operational
                  claims.
                </p>
                <a
                  className="text-button"
                  href="/api/report"
                  target="_blank"
                  rel="noreferrer"
                >
                  Read the research report <ArrowUpRight size={14} />
                </a>
              </section>
            </div>
          </>
        )}
        {tab === "Historical explorer" && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Historical observations</h2>
                <p>
                  CAISO OASIS ·{" "}
                  {target === "demand"
                    ? "CA ISO-TAC actual integrated load"
                    : "TH_NP15_GEN-APND / DAM total LMP"}{" "}
                  · {unit}
                </p>
              </div>
              <div className="controls">
                <label>
                  FROM
                  <input
                    type="date"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <label>
                  TO (EXCLUSIVE)
                  <input
                    type="date"
                    value={end}
                    onChange={(e) => setEnd(e.target.value)}
                  />
                </label>
              </div>
            </div>
            <Chart data={history} history unit={unit} />
            <p>
              {fmt(history.length)} authentic hourly observations. Gaps remain
              missing; no target imputation.
            </p>
          </section>
        )}
        {tab === "Forecast lab" && (
          <section className="panel">
            <h2>{replayOnly ? "View an eligible historical forecast" : "Replay an eligible forecast"}</h2>
            <p>
              {replayOnly
                ? "Shows the stored forecast generated before the selected held-out outcome."
                : "Uses the artifact trained before the selected held-out quarter. Actual outcomes appear only for evaluation."}
            </p>
            {controls}
            <button
              className="primary"
              disabled={!origin}
              onClick={() => execute()}
            >
              {replayOnly ? "View stored historical forecast" : "Generate historical forecast"} <ArrowUpRight size={16} />
            </button>
            {forecast && (
              <div className="result">
                <strong>
                  {fmt(Number(forecast.prediction), 2)} {unit}
                </strong>
                <p>
                  Target: {String(forecast.target_time)} · Actual:{" "}
                  {fmt(Number(forecast.actual), 2)} {unit}
                </p>
                <p>
                  90% interval: {fmt(Number(forecast.lower), 2)} –{" "}
                  {fmt(Number(forecast.upper), 2)} {unit}
                </p>
                <code>{String(forecast.artifact_id)}</code>
              </div>
            )}
            <Chart data={replay} unit={unit} />
          </section>
        )}
        {tab === "Model comparison" && (
          <section className="panel">
            <h2>Final held-out model comparison</h2>
            <p>
              July–December 2025 · lower MAE is better · selection fixed using
              January–June validation.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>MODEL</th>
                    <th>MAE ({unit})</th>
                    <th>RMSE</th>
                    <th>BIAS</th>
                    <th>COVERAGE</th>
                    <th>FIT + PREDICT</th>
                  </tr>
                </thead>
                <tbody>
                  {scores
                    .filter((s) => s.split === "test")
                    .sort((a, b) => a.mae - b.mae)
                    .map((s) => (
                      <tr key={s.model}>
                        <td>
                          {s.model}
                          {s.selected_on_validation && (
                            <span className="selected">SELECTED</span>
                          )}
                        </td>
                        <td className="lime">{fmt(s.mae, 2)}</td>
                        <td>{fmt(s.rmse, 2)}</td>
                        <td>{fmt(s.bias, 2)}</td>
                        <td>{fmt(s.coverage * 100, 1)}%</td>
                        <td>{fmt(s.training_seconds, 1)}s</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p>
              All comparisons are reported; held-out results were not used to
              retune models. Runtime includes prediction; CPU timings depend on
              hardware.
            </p>
          </section>
        )}
        {tab === "Scenario analysis" && (
          <section className="panel">
            <span className="tag">HYPOTHETICAL SENSITIVITY</span>
            <h2>Change the historical level assumption</h2>
            <p>
              Scales observed lags, rolling means, rolling deviations and the
              seasonal anchor; runs the same fitted model again. This is feature
              sensitivity, not a causal weather forecast.
            </p>
            {replayOnly ? (
              <div className="notice">
                Scenario analysis is unavailable in this public historical replay release. It intentionally excludes model checkpoints and does not represent causal interventions.
              </div>
            ) : (
              <>
                {controls}
                <label className="slider">
                  HISTORICAL LEVEL CHANGE: {change}%
                  <input
                    type="range"
                    min="-20"
                    max="20"
                    value={change}
                    onChange={(e) => {
                      setChange(Number(e.target.value));
                      setScenario(undefined);
                    }}
                  />
                </label>
                <button className="primary" onClick={() => execute(true)}>
                  Run model sensitivity
                </button>
                {scenario && (
                  <div className="result">
                    <strong>
                      {fmt(scenario.scenario, 2)} {unit}
                    </strong>
                    <p>
                      Baseline {fmt(scenario.baseline, 2)} · Change{" "}
                      {fmt(scenario.delta, 2)} {unit}
                    </p>
                    <p>{scenario.limitation}</p>
                  </div>
                )}
              </>
            )}
          </section>
        )}
        {tab === "Explainability" && (
          <section className="panel">
            <h2>Which features improved validation accuracy?</h2>
            {controls}
            <p>
              Permutation importance measured as the increase in validation MAE
              ({unit}). Correlated predictors share importance. This describes
              predictive association.
            </p>
            {importance.length ? (
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={importance}
                    layout="vertical"
                    margin={{ left: 55, right: 35 }}
                  >
                    <XAxis type="number" stroke="#819b96" />
                    <YAxis
                      type="category"
                      dataKey="feature"
                      width={100}
                      stroke="#819b96"
                      fontSize={11}
                    />
                    <Tooltip contentStyle={{ background: "#11221f" }} />
                    <Bar
                      dataKey="mae_increase"
                      name={`MAE increase (${unit})`}
                      fill="#bcf57a"
                      radius={[0, 3, 3, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="notice">
                This baseline has no fitted feature importance. Choose a fitted
                model.
              </div>
            )}
          </section>
        )}
        {tab === "Data quality" && (
          <>
            <div className="bottom-grid">
              {(["demand", "price"] as Target[]).map((t) => {
                const q = overview?.quality.targets[t];
                return (
                  <section className="panel" key={t}>
                    <h2>
                      {t === "demand"
                        ? "System demand"
                        : "NP15 day-ahead price"}
                    </h2>
                    <dl>
                      <dt>Observations / expected</dt>
                      <dd>
                        {fmt(q?.rows)} / {fmt(q?.expected_rows)}
                      </dd>
                      <dt>Missing hours</dt>
                      <dd>{q?.missing_hours ?? "—"}</dd>
                      <dt>Period (UTC)</dt>
                      <dd>
                        {q?.start}
                        <br />
                        {q?.end}
                      </dd>
                      <dt>Last successful acquisition</dt>
                      <dd>{q?.last_acquisition}</dd>
                      <dt>Negative observations</dt>
                      <dd>{q?.negative_observations}</dd>
                      <dt>Dataset SHA-256</dt>
                      <dd className="hash">{q?.dataset_sha256}</dd>
                    </dl>
                  </section>
                );
              })}
            </div>
            <div className="notice">
              Historical coverage is not live freshness. Acquisition time
              records the download, not the original publication time. See
              methodology for revision-vintage limitations.
            </div>
          </>
        )}
        {tab === "Research findings" && (
          <section className="panel research">
            <span className="tag">REPRODUCIBLE RESEARCH / V0.1</span>
            <h2>
              A Reproducible Framework for California Electricity Demand and
              Price Forecasting
            </h2>
            <p>
              The report contains dataset quality, real exploratory figures,
              baseline comparisons, direct-horizon validation, interval coverage
              and limitations. Metrics are generated from experiment outputs.
            </p>
            <a
              className="primary"
              href="/api/report"
              target="_blank"
              rel="noreferrer"
            >
              Open technical report <ArrowUpRight size={16} />
            </a>
            <h3>Supported applications</h3>
            <p>
              Historical forecast strategy comparisons, demand planning
              research, peak error analysis and price risk monitoring research.
            </p>
            <h3>Research boundaries</h3>
            <p>
              No validated trading optimizer, realized financial savings, live
              operation, archived forecast vintages or causal weather scenario
              engine. Summer 2025 test results do not establish reliability in
              unseen regimes.
            </p>
          </section>
        )}
        <footer>
          GRIDCAST{" "}
          <span>
            CAISO OASIS · UTC CANONICAL / AMERICA–LOS ANGELES CALENDAR
          </span>
          <span>RESEARCH BUILD 0.1</span>
        </footer>
      </main>
    </div>
  );
}
