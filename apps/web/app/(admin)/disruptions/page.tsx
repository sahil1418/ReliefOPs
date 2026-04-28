"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert,
  Activity,
  Brain,
  Route,
  AlertTriangle,
  TrendingUp,
  Zap,
  Eye,
  RefreshCw,
} from "lucide-react";
import {
  Area,
  AreaChart,
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
    graph_stats: { nodes: number; edges: number; blocked_edges: number; disrupted_edges: number };
    demo_nodes: string[];
  };
  disruption_predictor: {
    model: string;
    corridors_monitored: number;
  };
};

/* ── Main Page ──────────────────────────────────────────────────────────── */

export default function DisruptionsPage() {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [prediction, setPrediction] = useState<DisruptionPrediction | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);

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
      setError(err instanceof ApiCallError ? err.message : "Failed to load ML data");
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
      const result = await api.post<DisruptionPrediction>("/api/ml/predict-disruptions");
      setPrediction(result);
    } catch (err) {
      setError(err instanceof ApiCallError ? err.message : "Prediction failed");
    } finally {
      setPredicting(false);
    }
  };

  /* ── Derived data for charts ──────────────────────────────────────────── */

  const anomalyTypeData = anomalies.reduce(
    (acc, a) => {
      const type = a.anomaly_type || "unknown";
      acc[type] = (acc[type] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const typeBarData = Object.entries(anomalyTypeData).map(([type, count]) => ({
    type: type.charAt(0).toUpperCase() + type.slice(1),
    count,
  }));

  const corridorRadarData =
    prediction?.corridors.map((c) => ({
      corridor: c.corridor_name.split(" ")[0],
      risk: Math.round(c.risk_score * 100),
      delay: c.predicted_delay_min,
    })) ?? [];

  const riskColors: Record<string, string> = {
    critical: "#ef4444",
    high: "#f97316",
    medium: "#eab308",
    low: "#22c55e",
  };

  const anomalyTypeColors: Record<string, string> = {
    stuck: "#ef4444",
    drift: "#f97316",
    slowdown: "#eab308",
    congestion: "#8b5cf6",
    spoofing: "#ec4899",
    unknown: "#6b7280",
  };

  return (
    <>
      <AdminTopbar title="Supply Chain Intelligence" />
      <main className="flex-1 space-y-6 p-6">
        {/* ── Header Badge ────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 shadow-lg">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">ML-Powered Disruption Detection</h2>
              <p className="text-xs text-muted-foreground">
                Isolation Forest anomaly detection · Gemini risk scoring · Dijkstra graph routing
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={runPrediction}
              disabled={predicting}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {predicting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Zap className="h-4 w-4" />
              )}
              {predicting ? "Predicting…" : "Run Prediction"}
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error} — is FastAPI running on{" "}
            <code>{process.env.NEXT_PUBLIC_API_BASE_URL || "localhost:8000"}</code>?
          </div>
        )}

        {/* ── KPI Row ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            icon={<ShieldAlert className="h-5 w-5 text-violet-500" />}
            title="Anomalies Detected"
            value={anomalies.length}
            sublabel="last 4 hours"
            accent="violet"
          />
          <KpiCard
            icon={<Route className="h-5 w-5 text-amber-500" />}
            title="Corridors Monitored"
            value={prediction?.corridors.length ?? 0}
            sublabel="real-time risk scoring"
            accent="amber"
          />
          <KpiCard
            icon={<AlertTriangle className="h-5 w-5 text-rose-500" />}
            title="At-Risk Shipments"
            value={prediction?.total_at_risk_shipments ?? 0}
            sublabel="across all corridors"
            accent="rose"
          />
          <KpiCard
            icon={<Activity className="h-5 w-5 text-emerald-500" />}
            title="Model Status"
            value={modelStatus?.anomaly_detector.fitted ? "Active" : "Offline"}
            sublabel={modelStatus?.anomaly_detector.algorithm ?? "—"}
            accent="emerald"
          />
        </div>

        {/* ── Corridor Risk Cards ───────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-violet-500" />
              Corridor Risk Assessment
            </CardTitle>
            <CardDescription>
              Predictive risk scores for transit corridors — updated every 15s.
              Risk &gt; 0.7 triggers pre-emptive reroute recommendation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!prediction ? (
              <p className="text-sm text-muted-foreground">Loading corridors…</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {prediction.corridors.map((c) => (
                  <div
                    key={c.corridor_id}
                    className="relative overflow-hidden rounded-lg border bg-gradient-to-br from-background to-muted/30 p-4 transition-shadow hover:shadow-md"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="text-sm font-semibold">{c.corridor_name}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {c.center_lat.toFixed(2)}°N, {c.center_lng.toFixed(2)}°E
                        </p>
                      </div>
                      <span
                        className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
                        style={{
                          backgroundColor: `${riskColors[c.risk_level]}20`,
                          color: riskColors[c.risk_level],
                        }}
                      >
                        {c.risk_level.toUpperCase()}
                      </span>
                    </div>

                    {/* Risk bar */}
                    <div className="mt-3">
                      <div className="flex items-baseline justify-between text-xs">
                        <span className="text-muted-foreground">Risk Score</span>
                        <span className="font-mono font-semibold">
                          {(c.risk_score * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${c.risk_score * 100}%`,
                            backgroundColor: riskColors[c.risk_level],
                          }}
                        />
                      </div>
                    </div>

                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-muted-foreground">Predicted delay</span>
                        <p className="font-semibold">{c.predicted_delay_min} min</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Confidence</span>
                        <p className="font-semibold">{(c.confidence * 100).toFixed(0)}%</p>
                      </div>
                    </div>

                    {c.factors.length > 0 && (
                      <div className="mt-2">
                        {c.factors.slice(0, 2).map((f, i) => (
                          <p key={i} className="text-xs text-muted-foreground">
                            • {f}
                          </p>
                        ))}
                      </div>
                    )}

                    {c.affected_shipment_ids.length > 0 && (
                      <p className="mt-2 text-xs font-medium text-rose-600">
                        ⚠ {c.affected_shipment_ids.length} shipment(s) affected
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Charts Row ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Anomaly Types Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Anomaly Type Distribution</CardTitle>
              <CardDescription>Breakdown by detected anomaly category (last 4h)</CardDescription>
            </CardHeader>
            <CardContent>
              {typeBarData.length === 0 ? (
                <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                  No anomalies detected — fleet operating normally ✓
                </div>
              ) : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={typeBarData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="type" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ fontSize: 12 }} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {typeBarData.map((entry) => (
                          <Cell
                            key={entry.type}
                            fill={anomalyTypeColors[entry.type.toLowerCase()] ?? "#6b7280"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Corridor Risk Radar */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Corridor Risk Radar</CardTitle>
              <CardDescription>Comparative risk levels across monitored corridors</CardDescription>
            </CardHeader>
            <CardContent>
              {corridorRadarData.length === 0 ? (
                <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                  Loading corridor data…
                </div>
              ) : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={corridorRadarData}>
                      <PolarGrid stroke="#e2e8f0" />
                      <PolarAngleAxis dataKey="corridor" tick={{ fontSize: 10 }} />
                      <PolarRadiusAxis tick={{ fontSize: 9 }} domain={[0, 100]} />
                      <Radar
                        name="Risk %"
                        dataKey="risk"
                        stroke="#8b5cf6"
                        fill="#8b5cf6"
                        fillOpacity={0.3}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Anomaly Feed ───────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-amber-500" />
              Live Anomaly Feed
            </CardTitle>
            <CardDescription>
              Real-time anomalies detected by the Isolation Forest model on GPS tracking data.
              Each row represents a transit event that deviated from normal patterns.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {anomalies.length === 0 ? (
              <div className="flex h-32 items-center justify-center rounded-md border-2 border-dashed bg-muted/40 text-sm text-muted-foreground">
                {loading ? "Loading anomaly events…" : "No anomalies detected — all clear ✓"}
              </div>
            ) : (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 border-b bg-background">
                    <tr className="text-xs text-muted-foreground">
                      <th className="py-2 text-left">Type</th>
                      <th className="py-2 text-left">Score</th>
                      <th className="py-2 text-left">Confidence</th>
                      <th className="py-2 text-left">Location</th>
                      <th className="py-2 text-left">Volunteer</th>
                      <th className="py-2 text-left">Action</th>
                      <th className="py-2 text-left">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {anomalies.map((a) => (
                      <tr key={a.id} className="transition-colors hover:bg-muted/50">
                        <td className="py-2">
                          <span
                            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                            style={{
                              backgroundColor: `${anomalyTypeColors[a.anomaly_type] ?? "#6b7280"}20`,
                              color: anomalyTypeColors[a.anomaly_type] ?? "#6b7280",
                            }}
                          >
                            {a.anomaly_type}
                          </span>
                        </td>
                        <td className="py-2 font-mono text-xs">
                          {(a.score * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 font-mono text-xs">
                          {(a.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {a.lat.toFixed(4)}, {a.lng.toFixed(4)}
                        </td>
                        <td className="py-2 text-xs">
                          {a.volunteer_id?.slice(0, 8) ?? "—"}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {a.recommended_action.replace(/_/g, " ")}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {a.detected_at
                            ? new Date(a.detected_at).toLocaleTimeString()
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Model Info ─────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-purple-500" />
              ML Pipeline Status
            </CardTitle>
            <CardDescription>
              Model versions, training metadata, and graph routing statistics
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!modelStatus ? (
              <p className="text-sm text-muted-foreground">Loading model status…</p>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                {/* Anomaly Detector */}
                <div className="rounded-lg border bg-gradient-to-br from-violet-50 to-purple-50 p-4 dark:from-violet-950/20 dark:to-purple-950/20">
                  <h4 className="text-sm font-semibold text-violet-700 dark:text-violet-300">
                    Anomaly Detector
                  </h4>
                  <div className="mt-2 space-y-1 text-xs">
                    <p>
                      <span className="text-muted-foreground">Algorithm:</span>{" "}
                      {modelStatus.anomaly_detector.algorithm}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Estimators:</span>{" "}
                      {modelStatus.anomaly_detector.n_estimators}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Training samples:</span>{" "}
                      {modelStatus.anomaly_detector.n_training_samples}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Version:</span>{" "}
                      {modelStatus.anomaly_detector.version}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Status:</span>{" "}
                      <span
                        className={
                          modelStatus.anomaly_detector.fitted
                            ? "text-emerald-600"
                            : "text-rose-600"
                        }
                      >
                        {modelStatus.anomaly_detector.fitted ? "● Active" : "○ Offline"}
                      </span>
                    </p>
                    <p className="text-muted-foreground">
                      Features: {modelStatus.anomaly_detector.features.join(", ")}
                    </p>
                  </div>
                </div>

                {/* Graph Router */}
                <div className="rounded-lg border bg-gradient-to-br from-blue-50 to-cyan-50 p-4 dark:from-blue-950/20 dark:to-cyan-950/20">
                  <h4 className="text-sm font-semibold text-blue-700 dark:text-blue-300">
                    Graph Router (Dijkstra + A*)
                  </h4>
                  <div className="mt-2 space-y-1 text-xs">
                    <p>
                      <span className="text-muted-foreground">Algorithm:</span>{" "}
                      {modelStatus.graph_router.algorithm}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Nodes:</span>{" "}
                      {modelStatus.graph_router.graph_stats.nodes}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Edges:</span>{" "}
                      {modelStatus.graph_router.graph_stats.edges}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Blocked:</span>{" "}
                      <span className={modelStatus.graph_router.graph_stats.blocked_edges > 0 ? "text-rose-600" : ""}>
                        {modelStatus.graph_router.graph_stats.blocked_edges}
                      </span>
                    </p>
                    <p>
                      <span className="text-muted-foreground">Disrupted:</span>{" "}
                      <span className={modelStatus.graph_router.graph_stats.disrupted_edges > 0 ? "text-amber-600" : ""}>
                        {modelStatus.graph_router.graph_stats.disrupted_edges}
                      </span>
                    </p>
                  </div>
                </div>

                {/* Disruption Predictor */}
                <div className="rounded-lg border bg-gradient-to-br from-amber-50 to-orange-50 p-4 dark:from-amber-950/20 dark:to-orange-950/20">
                  <h4 className="text-sm font-semibold text-amber-700 dark:text-amber-300">
                    Disruption Predictor
                  </h4>
                  <div className="mt-2 space-y-1 text-xs">
                    <p>
                      <span className="text-muted-foreground">Model:</span>{" "}
                      {modelStatus.disruption_predictor.model}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Corridors:</span>{" "}
                      {modelStatus.disruption_predictor.corridors_monitored}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Prediction source:</span> Gemini 2.5
                      Flash + heuristic fallback
                    </p>
                    <p>
                      <span className="text-muted-foreground">Risk threshold:</span> 0.7
                      (auto-reroute)
                    </p>
                    <p>
                      <span className="text-muted-foreground">Update cadence:</span> 15s
                      real-time
                    </p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

/* ── Components ─────────────────────────────────────────────────────────── */

function KpiCard({
  icon,
  title,
  value,
  sublabel,
  accent,
}: {
  icon: React.ReactNode;
  title: string;
  value: number | string;
  sublabel: string;
  accent: string;
}) {
  return (
    <Card className="relative overflow-hidden">
      <div
        className="absolute inset-0 opacity-5"
        style={{
          background: `linear-gradient(135deg, var(--${accent}-500, #8b5cf6), transparent)`,
        }}
      />
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        <p className="mt-1 text-xs text-muted-foreground">{sublabel}</p>
      </CardContent>
    </Card>
  );
}
