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
  Database,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip,
  XAxis, YAxis, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

/* ── Types ──────────────────────────────────────────────────────────── */

type AnomalyEvent = {
  id: string; anomaly_type: string; score: number; confidence: number;
  recommended_action: string; lat: number; lng: number;
  volunteer_id: string | null; shipment_id: string | null;
  detected_at: string | null; features: Record<string, number>;
};

type CorridorRisk = {
  corridor_id: string; corridor_name: string; center_lat: number; center_lng: number;
  risk_score: number; risk_level: string; factors: string[];
  recommended_action: string; affected_shipment_ids: string[];
  predicted_delay_min: number; confidence: number;
};

type DisruptionPrediction = {
  timestamp: string; corridors: CorridorRisk[]; model_version: string;
  total_at_risk_shipments: number; auto_reroutes_triggered: number;
};

type ModelStatus = {
  anomaly_detector: { version: string; fitted: boolean; trained_at: string | null; n_training_samples: number; algorithm: string; n_estimators: number; features: string[] };
  graph_router: { algorithm: string; graph_stats: { nodes: number; edges: number; blocked_edges: number; disrupted_edges: number }; demo_nodes: string[] };
  disruption_predictor: { model: string; corridors_monitored: number };
};

/* ── Constants ──────────────────────────────────────────────────────── */

const RISK_FALLBACK = { color: "#16a34a", bg: "rgba(22,163,74,0.07)", border: "rgba(22,163,74,0.2)", glow: "0 0 20px rgba(22,163,74,0.08)" };
const RISK: Record<string, typeof RISK_FALLBACK> = {
  critical: { color: "#dc2626", bg: "rgba(220,38,38,0.07)", border: "rgba(220,38,38,0.22)", glow: "0 0 24px rgba(220,38,38,0.10)" },
  high:     { color: "#ea580c", bg: "rgba(234,88,12,0.07)", border: "rgba(234,88,12,0.22)", glow: "0 0 20px rgba(234,88,12,0.08)" },
  medium:   { color: "#ca8a04", bg: "rgba(202,138,4,0.07)", border: "rgba(202,138,4,0.20)", glow: "0 0 20px rgba(202,138,4,0.08)" },
  low:      RISK_FALLBACK,
};

const ANOM_CLR: Record<string, string> = {
  stuck: "#dc2626", drift: "#ea580c", slowdown: "#ca8a04",
  congestion: "#7c3aed", spoofing: "#db2777", unknown: "#6b7280",
};

/* ── Page ───────────────────────────────────────────────────────────── */

export default function DisruptionsPage() {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [pred, setPred] = useState<DisruptionPrediction | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"predict" | "seed" | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, r, m] = await Promise.all([
        api.get<AnomalyEvent[]>("/api/ml/anomalies?hours=4&limit=50"),
        api.get<DisruptionPrediction>("/api/ml/risk-corridors"),
        api.get<ModelStatus>("/api/ml/model-status"),
      ]);
      setAnomalies(a); setPred(r); setModel(m); setError(null);
    } catch (e) { setError(e instanceof ApiCallError ? e.message : "Load failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); const t = setInterval(load, 15_000); return () => clearInterval(t); }, [load]);

  const predict = async () => {
    setBusy("predict");
    try { setPred(await api.post<DisruptionPrediction>("/api/ml/predict-disruptions")); }
    catch (e) { setError(e instanceof ApiCallError ? e.message : "Prediction failed"); }
    finally { setBusy(null); }
  };

  const seed = async () => {
    setBusy("seed"); setToast(null);
    try {
      const r = await api.post<{ anomalies_created: number; tracking_events_created: number }>("/api/ml/seed-demo");
      setToast(`Seeded ${r.anomalies_created} anomalies + ${r.tracking_events_created} tracking events`);
      await load();
    } catch (e) { setError(e instanceof ApiCallError ? e.message : "Seed failed"); }
    finally { setBusy(null); }
  };

  /* derived */
  const barData = Object.entries(anomalies.reduce((a, e) => { const t = e.anomaly_type || "unknown"; a[t] = (a[t] || 0) + 1; return a; }, {} as Record<string, number>)).map(([t, c]) => ({ type: t.charAt(0).toUpperCase() + t.slice(1), count: c }));
  const radarData = pred?.corridors.map(c => ({ name: c.corridor_name.split(/[\s\u2013-]/)[0], risk: Math.round(c.risk_score * 100) })) ?? [];

  return (
    <>
      <AdminTopbar title="Supply Chain Intelligence" />
      <main className="flex-1 space-y-6 p-6">

        {/* ── Hero header ──────────────────────────────────────────── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-700 shadow-lg shadow-violet-500/20">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Disruption Detection</h1>
              <p className="text-[13px] text-muted-foreground">Isolation Forest &middot; Gemini Risk Scoring &middot; Dijkstra Routing</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={seed} disabled={busy === "seed"} className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 bg-card px-3.5 py-2 text-xs font-medium text-muted-foreground shadow-sm transition hover:border-border hover:text-foreground disabled:opacity-40">
              {busy === "seed" ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />} Seed Data
            </button>
            <button onClick={predict} disabled={busy === "predict"} className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-violet-500/25 transition hover:shadow-lg hover:shadow-violet-500/30 disabled:opacity-40">
              {busy === "predict" ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />} Run Prediction
            </button>
          </div>
        </div>

        {toast && <p className="rounded-lg border border-emerald-200 bg-emerald-50/80 px-4 py-2 text-xs font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400">{toast}</p>}
        {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div>}

        {/* ── KPI cards ────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Kpi icon={<ShieldAlert className="h-5 w-5 text-violet-500" />} label="Anomalies Detected" value={anomalies.length} sub="last 4 hours" />
          <Kpi icon={<Route className="h-5 w-5 text-sky-500" />} label="Corridors Monitored" value={pred?.corridors.length ?? 0} sub="real-time scoring" />
          <Kpi icon={<AlertTriangle className="h-5 w-5 text-rose-500" />} label="At-Risk Shipments" value={pred?.total_at_risk_shipments ?? 0} sub="across corridors" />
          <Kpi icon={<Activity className="h-5 w-5 text-emerald-500" />} label="Model Status" value={model?.anomaly_detector.fitted ? "Online" : "Offline"} sub={model?.anomaly_detector.algorithm ?? "\u2014"} highlight={model?.anomaly_detector.fitted ? "emerald" : "rose"} />
        </div>

        {/* ── Corridor risk ────────────────────────────────────────── */}
        <Card className="border-0 shadow-md shadow-black/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-violet-500" /> Corridor Risk Assessment
            </CardTitle>
            <CardDescription>Predictive risk scores updated every 15 s. Risk &gt; 70 % triggers pre-emptive reroute.</CardDescription>
          </CardHeader>
          <CardContent>
            {!pred ? <p className="py-8 text-center text-sm text-muted-foreground">Loading&hellip;</p> : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {pred.corridors.map(c => {
                  const s = RISK[c.risk_level] ?? RISK_FALLBACK;
                  return (
                    <div key={c.corridor_id} className="rounded-xl border p-4 transition-shadow duration-200 hover:shadow-md" style={{ borderColor: s.border, background: s.bg, boxShadow: s.glow }}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold">{c.corridor_name}</p>
                          <p className="text-[11px] text-muted-foreground">{c.center_lat.toFixed(2)}&deg;N, {c.center_lng.toFixed(2)}&deg;E</p>
                        </div>
                        <span className="rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest" style={{ color: s.color }}>{c.risk_level}</span>
                      </div>
                      <div className="mt-3">
                        <div className="flex justify-between text-[11px]"><span className="text-muted-foreground">Risk Score</span><span className="font-mono text-base font-bold tabular-nums" style={{ color: s.color }}>{(c.risk_score * 100).toFixed(1)}<span className="text-[10px] font-normal">%</span></span></div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-border/50"><div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(c.risk_score * 100, 2)}%`, backgroundColor: s.color }} /></div>
                      </div>
                      <div className="mt-2.5 flex gap-4 text-[11px]">
                        <span><span className="text-muted-foreground">Delay </span><strong>{c.predicted_delay_min} min</strong></span>
                        <span><span className="text-muted-foreground">Conf </span><strong>{(c.confidence * 100).toFixed(0)}%</strong></span>
                        {c.affected_shipment_ids.length > 0 && <span className="font-medium text-rose-600">{c.affected_shipment_ids.length} affected</span>}
                      </div>
                      {c.factors.length > 0 && <p className="mt-2 truncate text-[11px] text-muted-foreground">{c.factors[0]}</p>}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Charts ───────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="border-0 shadow-md shadow-black/[0.04]">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Anomaly Distribution</CardTitle><CardDescription className="text-xs">By category &middot; last 4 h</CardDescription></CardHeader>
            <CardContent>
              {barData.length === 0 ? <div className="flex h-44 items-center justify-center text-xs text-muted-foreground">No anomalies in window</div> : (
                <div className="h-44"><ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="type" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid hsl(var(--border))", boxShadow: "0 4px 12px rgba(0,0,0,.08)" }} />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]} barSize={28}>{barData.map(e => <Cell key={e.type} fill={ANOM_CLR[e.type.toLowerCase()] ?? "#94a3b8"} fillOpacity={0.85} />)}</Bar>
                  </BarChart>
                </ResponsiveContainer></div>
              )}
            </CardContent>
          </Card>

          <Card className="border-0 shadow-md shadow-black/[0.04]">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Corridor Risk Radar</CardTitle><CardDescription className="text-xs">Comparative risk levels</CardDescription></CardHeader>
            <CardContent>
              {radarData.length === 0 ? <div className="flex h-44 items-center justify-center text-xs text-muted-foreground">Loading&hellip;</div> : (
                <div className="h-44"><ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData} cx="50%" cy="50%">
                    <PolarGrid stroke="hsl(var(--border))" />
                    <PolarAngleAxis dataKey="name" tick={{ fontSize: 9 }} />
                    <PolarRadiusAxis tick={{ fontSize: 8 }} domain={[0, 100]} axisLine={false} />
                    <Radar dataKey="risk" stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.15} strokeWidth={1.5} />
                  </RadarChart>
                </ResponsiveContainer></div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Anomaly feed ─────────────────────────────────────────── */}
        <Card className="border-0 shadow-md shadow-black/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Eye className="h-4 w-4 text-amber-500" /> Live Anomaly Feed</CardTitle>
            <CardDescription>Real-time anomalies detected by the Isolation Forest model &middot; {anomalies.length} events</CardDescription>
          </CardHeader>
          <CardContent>
            {anomalies.length === 0 ? (
              <div className="flex h-24 items-center justify-center rounded-lg border border-dashed text-xs text-muted-foreground">{loading ? "Loading\u2026" : "No anomalies detected"}</div>
            ) : (
              <div className="max-h-72 overflow-y-auto rounded-lg border">
                <table className="w-full text-[12px]">
                  <thead><tr className="border-b bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2.5 text-left font-medium">Type</th>
                    <th className="px-4 py-2.5 text-left font-medium">Score</th>
                    <th className="hidden px-4 py-2.5 text-left font-medium sm:table-cell">Confidence</th>
                    <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">Location</th>
                    <th className="px-4 py-2.5 text-left font-medium">Action</th>
                    <th className="px-4 py-2.5 text-left font-medium">Time</th>
                  </tr></thead>
                  <tbody>{anomalies.map((a, i) => (
                    <tr key={a.id} className={`border-b border-border/40 transition-colors hover:bg-muted/40 ${i % 2 ? "bg-muted/20" : ""}`}>
                      <td className="px-4 py-2"><span className="rounded-md px-2 py-0.5 text-[10px] font-semibold" style={{ color: ANOM_CLR[a.anomaly_type] ?? "#6b7280", background: `${ANOM_CLR[a.anomaly_type] ?? "#6b7280"}14` }}>{a.anomaly_type}</span></td>
                      <td className="px-4 py-2 font-mono tabular-nums">{(a.score * 100).toFixed(1)}%</td>
                      <td className="hidden px-4 py-2 font-mono tabular-nums sm:table-cell">{(a.confidence * 100).toFixed(0)}%</td>
                      <td className="hidden px-4 py-2 text-muted-foreground md:table-cell">{a.lat.toFixed(3)}, {a.lng.toFixed(3)}</td>
                      <td className="px-4 py-2 text-muted-foreground">{a.recommended_action.replaceAll("_", " ")}</td>
                      <td className="px-4 py-2 tabular-nums text-muted-foreground">{a.detected_at ? new Date(a.detected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "\u2014"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Pipeline status ──────────────────────────────────────── */}
        <Card className="border-0 shadow-md shadow-black/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Brain className="h-4 w-4 text-violet-500" /> ML Pipeline</CardTitle>
            <CardDescription>Model versions, training metadata, and routing graph</CardDescription>
          </CardHeader>
          <CardContent>
            {!model ? <p className="py-6 text-center text-sm text-muted-foreground">Loading&hellip;</p> : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <PipeCard accent="from-violet-500/10 to-purple-500/10" dot="#7c3aed" title="Anomaly Detector" items={[["Algorithm", model.anomaly_detector.algorithm], ["Estimators", String(model.anomaly_detector.n_estimators)], ["Samples", String(model.anomaly_detector.n_training_samples)], ["Version", model.anomaly_detector.version], ["Status", model.anomaly_detector.fitted ? "Active" : "Offline"]]} />
                <PipeCard accent="from-sky-500/10 to-cyan-500/10" dot="#0284c7" title="Graph Router (Dijkstra + A*)" items={[["Algorithm", model.graph_router.algorithm], ["Nodes", String(model.graph_router.graph_stats.nodes)], ["Edges", String(model.graph_router.graph_stats.edges)], ["Blocked", String(model.graph_router.graph_stats.blocked_edges)], ["Disrupted", String(model.graph_router.graph_stats.disrupted_edges)]]} />
                <PipeCard accent="from-amber-500/10 to-orange-500/10" dot="#ea580c" title="Disruption Predictor" items={[["Model", "Gemini 2.5 Flash + heuristic"], ["Corridors", String(model.disruption_predictor.corridors_monitored)], ["Threshold", "0.7 (auto-reroute)"], ["Cadence", "15 s real-time"]]} />
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

/* ── Sub-components ─────────────────────────────────────────────────── */

function Kpi({ icon, label, value, sub, highlight }: { icon: React.ReactNode; label: string; value: number | string; sub: string; highlight?: string }) {
  return (
    <Card className="border-0 shadow-md shadow-black/[0.04]">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>{icon}
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold tracking-tight ${highlight === "emerald" ? "text-emerald-600" : highlight === "rose" ? "text-rose-500" : ""}`}>{value}</div>
        <p className="mt-1 text-[11px] text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function PipeCard({ accent, dot, title, items }: { accent: string; dot: string; title: string; items: [string, string][] }) {
  return (
    <div className={`rounded-xl border bg-gradient-to-br ${accent} p-4`}>
      <div className="flex items-center gap-2"><div className="h-2 w-2 rounded-full" style={{ backgroundColor: dot }} /><h4 className="text-xs font-semibold">{title}</h4></div>
      <dl className="mt-3 space-y-1.5">{items.map(([k, v]) => (
        <div key={k} className="flex justify-between text-[11px]"><dt className="text-muted-foreground">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>
      ))}</dl>
    </div>
  );
}
