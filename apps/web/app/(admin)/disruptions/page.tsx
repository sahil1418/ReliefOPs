"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Activity,
  Route,
  AlertTriangle,
  TrendingUp,
  Zap,
  RefreshCw,
  ChevronRight,
  Database,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

/* ── Types ──────────────────────────────────────────────────────────────── */

type AnomalyEvent = {
  id: string;
  anomaly_type: string;
  score: number;
  confidence: number;
  recommended_action: string;
  lat: number;
  lng: number;
  volunteer_id: string | null;
  shipment_id: string | null;
  detected_at: string | null;
  features: Record<string, number>;
};

type CorridorRisk = {
  corridor_id: string;
  corridor_name: string;
  center_lat: number;
  center_lng: number;
  risk_score: number;
  risk_level: string;
  factors: string[];
  recommended_action: string;
  affected_shipment_ids: string[];
  predicted_delay_min: number;
  confidence: number;
};

type DisruptionPrediction = {
  timestamp: string;
  corridors: CorridorRisk[];
  model_version: string;
  total_at_risk_shipments: number;
  auto_reroutes_triggered: number;
};

type ModelStatus = {
  anomaly_detector: {
    version: string;
    fitted: boolean;
    trained_at: string | null;
    n_training_samples: number;
    algorithm: string;
    n_estimators: number;
    features: string[];
  };
  graph_router: {
    algorithm: string;
    graph_stats: {
      nodes: number;
      edges: number;
      blocked_edges: number;
      disrupted_edges: number;
    };
    demo_nodes: string[];
  };
  disruption_predictor: {
    model: string;
    corridors_monitored: number;
  };
};

/* ── Constants ──────────────────────────────────────────────────────────── */

const RISK_CONFIG: Record<string, { color: string; bg: string; border: string }> = {
  critical: { color: "#dc2626", bg: "rgba(220,38,38,0.06)", border: "rgba(220,38,38,0.18)" },
  high:     { color: "#ea580c", bg: "rgba(234,88,12,0.06)", border: "rgba(234,88,12,0.18)" },
  medium:   { color: "#ca8a04", bg: "rgba(202,138,4,0.06)", border: "rgba(202,138,4,0.18)" },
  low:      { color: "#16a34a", bg: "rgba(22,163,74,0.06)", border: "rgba(22,163,74,0.18)" },
};

const ANOMALY_COLORS: Record<string, string> = {
  stuck: "#dc2626",
  drift: "#ea580c",
  slowdown: "#ca8a04",
  congestion: "#7c3aed",
  spoofing: "#db2777",
  unknown: "#6b7280",
};

/* ── Page ───────────────────────────────────────────────────────────────── */

export default function DisruptionsPage() {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [prediction, setPrediction] = useState<DisruptionPrediction | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [a, r, m] = await Promise.all([
        api.get<AnomalyEvent[]>("/api/ml/anomalies?hours=4&limit=50"),
        api.get<DisruptionPrediction>("/api/ml/risk-corridors"),
        api.get<ModelStatus>("/api/ml/model-status"),
      ]);
      setAnomalies(a);
      setPrediction(r);
      setModelStatus(m);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiCallError ? err.message : "Failed to load ML data"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
    const id = window.setInterval(loadData, 15_000);
    return () => window.clearInterval(id);
  }, [loadData]);

  const runPrediction = async () => {
    setPredicting(true);
    try {
      const result = await api.post<DisruptionPrediction>(
        "/api/ml/predict-disruptions"
      );
      setPrediction(result);
    } catch (err) {
      setError(
        err instanceof ApiCallError ? err.message : "Prediction failed"
      );
    } finally {
      setPredicting(false);
    }
  };

  const seedDemoData = async () => {
    setSeeding(true);
    setSeedResult(null);
    try {
      const result = await api.post<{
        anomalies_created: number;
        tracking_events_created: number;
      }>("/api/ml/seed-demo");
      setSeedResult(
        `${result.anomalies_created} anomalies + ${result.tracking_events_created} tracking events seeded`
      );
      await loadData();
    } catch (err) {
      setError(
        err instanceof ApiCallError ? err.message : "Seeding failed"
      );
    } finally {
      setSeeding(false);
    }
  };

  /* ── Derived ──────────────────────────────────────────────────────────── */

  const typeBarData = Object.entries(
    anomalies.reduce(
      (acc, a) => {
        const t = a.anomaly_type || "unknown";
        acc[t] = (acc[t] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    )
  ).map(([type, count]) => ({
    type: type.charAt(0).toUpperCase() + type.slice(1),
    count,
  }));

  const radarData =
    prediction?.corridors.map((c) => ({
      corridor: c.corridor_name.split(/[\s–-]/)[0],
      risk: Math.round(c.risk_score * 100),
    })) ?? [];

  const highestRisk =
    prediction && prediction.corridors.length > 0
      ? prediction.corridors.reduce((max, c) =>
          c.risk_score > max.risk_score ? c : max
        )
      : null;

  /* ── Render ──────────────────────────────────────────────────────────── */

  return (
    <>
      <AdminTopbar title="Supply Chain Intelligence" />

      <main className="flex-1 space-y-5 p-6">
        {/* ── Page header ────────────────────────────────────────────── */}
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Disruption Detection
            </h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              ML-powered transit anomaly detection and corridor risk assessment
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={seedDemoData}
              disabled={seeding}
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
            >
              {seeding ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Database className="h-3 w-3" />
              )}
              Seed Data
            </button>
            <button
              onClick={runPrediction}
              disabled={predicting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3.5 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {predicting ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Zap className="h-3 w-3" />
              )}
              Predict
            </button>
          </div>
        </header>

        {seedResult && (
          <p className="text-xs text-emerald-600">{seedResult}</p>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* ── KPI strip ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard
            label="Anomalies"
            value={anomalies.length}
            sub="last 4 h"
            trend={anomalies.length > 5 ? "up" : "stable"}
          />
          <MetricCard
            label="Corridors"
            value={prediction?.corridors.length ?? 0}
            sub="monitored"
          />
          <MetricCard
            label="At Risk"
            value={prediction?.total_at_risk_shipments ?? 0}
            sub="shipments"
            trend={
              (prediction?.total_at_risk_shipments ?? 0) > 0 ? "up" : "stable"
            }
          />
          <MetricCard
            label="Model"
            value={modelStatus?.anomaly_detector.fitted ? "Online" : "Offline"}
            sub={modelStatus?.anomaly_detector.version ?? "—"}
            valueColor={
              modelStatus?.anomaly_detector.fitted
                ? "text-emerald-600"
                : "text-rose-500"
            }
          />
        </div>

        {/* ── Corridor risk grid ─────────────────────────────────────── */}
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium">Corridor Risk</h2>
            <span className="text-[11px] text-muted-foreground">
              auto-refresh 15 s
            </span>
          </div>

          {!prediction ? (
            <Skeleton />
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {prediction.corridors.map((c) => {
                const cfg = RISK_CONFIG[c.risk_level] ?? RISK_CONFIG.low;
                return (
                  <div
                    key={c.corridor_id}
                    className="group relative rounded-xl border p-4 transition-all duration-200 hover:shadow-sm"
                    style={{ borderColor: cfg.border, background: cfg.bg }}
                  >
                    {/* header */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-semibold leading-snug">
                          {c.corridor_name}
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          {c.center_lat.toFixed(2)}°N,{" "}
                          {c.center_lng.toFixed(2)}°E
                        </p>
                      </div>
                      <span
                        className="shrink-0 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                        style={{ color: cfg.color, background: cfg.bg }}
                      >
                        {c.risk_level}
                      </span>
                    </div>

                    {/* risk bar */}
                    <div className="mt-3.5">
                      <div className="flex items-baseline justify-between">
                        <span className="text-[11px] text-muted-foreground">
                          Risk
                        </span>
                        <span
                          className="font-mono text-lg font-semibold tabular-nums leading-none"
                          style={{ color: cfg.color }}
                        >
                          {(c.risk_score * 100).toFixed(1)}
                          <span className="text-[11px] font-normal">%</span>
                        </span>
                      </div>
                      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-border/60">
                        <div
                          className="h-full rounded-full transition-all duration-700 ease-out"
                          style={{
                            width: `${Math.max(c.risk_score * 100, 2)}%`,
                            backgroundColor: cfg.color,
                          }}
                        />
                      </div>
                    </div>

                    {/* metrics row */}
                    <div className="mt-3 flex items-center gap-4 text-[11px]">
                      <div>
                        <span className="text-muted-foreground">Delay</span>
                        <p className="font-medium">{c.predicted_delay_min} min</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Confidence</span>
                        <p className="font-medium">
                          {(c.confidence * 100).toFixed(0)}%
                        </p>
                      </div>
                      {c.affected_shipment_ids.length > 0 && (
                        <div>
                          <span className="text-muted-foreground">Affected</span>
                          <p className="font-medium text-rose-600">
                            {c.affected_shipment_ids.length}
                          </p>
                        </div>
                      )}
                    </div>

                    {/* factors */}
                    {c.factors.length > 0 && (
                      <div className="mt-2.5 space-y-0.5">
                        {c.factors.slice(0, 2).map((f, i) => (
                          <p
                            key={i}
                            className="text-[11px] leading-relaxed text-muted-foreground"
                          >
                            {f}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ── Charts ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Anomaly Distribution
              </CardTitle>
              <CardDescription className="text-[11px]">
                By category, last 4 hours
              </CardDescription>
            </CardHeader>
            <CardContent>
              {typeBarData.length === 0 ? (
                <div className="flex h-44 items-center justify-center text-xs text-muted-foreground">
                  No anomalies in window
                </div>
              ) : (
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={typeBarData}
                      margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="hsl(var(--border))"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="type"
                        tick={{ fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 10 }}
                        allowDecimals={false}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          fontSize: 11,
                          borderRadius: 8,
                          border: "1px solid hsl(var(--border))",
                          boxShadow: "0 4px 12px rgba(0,0,0,.08)",
                        }}
                      />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]} barSize={28}>
                        {typeBarData.map((e) => (
                          <Cell
                            key={e.type}
                            fill={
                              ANOMALY_COLORS[e.type.toLowerCase()] ?? "#94a3b8"
                            }
                            fillOpacity={0.85}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Corridor Risk Radar
              </CardTitle>
              <CardDescription className="text-[11px]">
                Comparative risk levels
              </CardDescription>
            </CardHeader>
            <CardContent>
              {radarData.length === 0 ? (
                <div className="flex h-44 items-center justify-center text-xs text-muted-foreground">
                  Loading...
                </div>
              ) : (
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} cx="50%" cy="50%">
                      <PolarGrid stroke="hsl(var(--border))" />
                      <PolarAngleAxis
                        dataKey="corridor"
                        tick={{ fontSize: 9 }}
                      />
                      <PolarRadiusAxis
                        tick={{ fontSize: 8 }}
                        domain={[0, 100]}
                        axisLine={false}
                      />
                      <Radar
                        dataKey="risk"
                        stroke="#7c3aed"
                        fill="#7c3aed"
                        fillOpacity={0.15}
                        strokeWidth={1.5}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Anomaly table ──────────────────────────────────────────── */}
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium">Anomaly Feed</h2>
            <span className="text-[11px] text-muted-foreground">
              {anomalies.length} events
            </span>
          </div>

          {anomalies.length === 0 ? (
            <div className="flex h-28 items-center justify-center rounded-xl border border-dashed text-xs text-muted-foreground">
              {loading ? "Loading..." : "No anomalies detected"}
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border">
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-2.5 text-left font-medium">
                        Type
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium">
                        Score
                      </th>
                      <th className="hidden px-4 py-2.5 text-left font-medium sm:table-cell">
                        Confidence
                      </th>
                      <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">
                        Location
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium">
                        Action
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium">
                        Time
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.map((a, i) => (
                      <tr
                        key={a.id}
                        className={`border-b border-border/50 transition-colors hover:bg-muted/30 ${
                          i % 2 === 0 ? "" : "bg-muted/15"
                        }`}
                      >
                        <td className="px-4 py-2.5">
                          <span
                            className="inline-block rounded-md px-2 py-0.5 text-[10px] font-semibold"
                            style={{
                              color:
                                ANOMALY_COLORS[a.anomaly_type] ?? "#6b7280",
                              background: `${ANOMALY_COLORS[a.anomaly_type] ?? "#6b7280"}12`,
                            }}
                          >
                            {a.anomaly_type}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono tabular-nums">
                          {(a.score * 100).toFixed(1)}%
                        </td>
                        <td className="hidden px-4 py-2.5 font-mono tabular-nums sm:table-cell">
                          {(a.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="hidden px-4 py-2.5 text-muted-foreground md:table-cell">
                          {a.lat.toFixed(3)}, {a.lng.toFixed(3)}
                        </td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {a.recommended_action.replaceAll("_", " ")}
                        </td>
                        <td className="px-4 py-2.5 tabular-nums text-muted-foreground">
                          {a.detected_at
                            ? new Date(a.detected_at).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* ── Pipeline status ────────────────────────────────────────── */}
        <section>
          <h2 className="mb-3 text-sm font-medium">Pipeline</h2>
          {!modelStatus ? (
            <Skeleton />
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <PipelineCard
                title="Anomaly Detector"
                accent="#7c3aed"
                entries={[
                  ["Algorithm", modelStatus.anomaly_detector.algorithm],
                  ["Estimators", String(modelStatus.anomaly_detector.n_estimators)],
                  ["Samples", String(modelStatus.anomaly_detector.n_training_samples)],
                  ["Version", modelStatus.anomaly_detector.version],
                  [
                    "Status",
                    modelStatus.anomaly_detector.fitted ? "Active" : "Offline",
                  ],
                ]}
              />
              <PipelineCard
                title="Graph Router"
                accent="#0284c7"
                entries={[
                  ["Algorithm", modelStatus.graph_router.algorithm],
                  ["Nodes", String(modelStatus.graph_router.graph_stats.nodes)],
                  ["Edges", String(modelStatus.graph_router.graph_stats.edges)],
                  ["Blocked", String(modelStatus.graph_router.graph_stats.blocked_edges)],
                  ["Disrupted", String(modelStatus.graph_router.graph_stats.disrupted_edges)],
                ]}
              />
              <PipelineCard
                title="Disruption Predictor"
                accent="#ea580c"
                entries={[
                  ["Model", "Gemini 2.5 Flash + heuristic"],
                  ["Corridors", String(modelStatus.disruption_predictor.corridors_monitored)],
                  ["Threshold", "0.7 (auto-reroute)"],
                  ["Cadence", "15 s real-time"],
                ]}
              />
            </div>
          )}
        </section>
      </main>
    </>
  );
}

/* ── Sub-components ─────────────────────────────────────────────────────── */

function MetricCard({
  label,
  value,
  sub,
  trend,
  valueColor,
}: {
  label: string;
  value: number | string;
  sub: string;
  trend?: "up" | "stable";
  valueColor?: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-semibold tabular-nums leading-none tracking-tight ${valueColor ?? ""}`}
      >
        {value}
      </p>
      <p className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground">
        {trend === "up" && (
          <TrendingUp className="h-3 w-3 text-amber-500" />
        )}
        {sub}
      </p>
    </div>
  );
}

function PipelineCard({
  title,
  accent,
  entries,
}: {
  title: string;
  accent: string;
  entries: [string, string][];
}) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2">
        <div
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: accent }}
        />
        <h3 className="text-xs font-semibold">{title}</h3>
      </div>
      <dl className="mt-3 space-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between text-[11px]">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-medium tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex h-28 items-center justify-center rounded-xl border border-dashed text-xs text-muted-foreground">
      Loading...
    </div>
  );
}
