"use client";

/**
 * Disruption Radar — surfaces the ML disruption-prediction pipeline.
 *
 * Pulls /api/ml/risk-corridors (corridor-level risk scores from IsolationForest
 * anomaly density + Gemini reasoning) and /api/ml/anomalies (recent flagged
 * GPS pings). Auto-refreshes every 60s.
 */
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, GitBranch, Radar } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type CorridorRisk = {
  corridor_id: string;
  corridor_name: string;
  center_lat: number;
  center_lng: number;
  risk_score: number;
  risk_level: "low" | "medium" | "high" | "critical";
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

const LEVEL_TINT: Record<CorridorRisk["risk_level"], string> = {
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-700",
  high: "border-orange-200 bg-orange-50 text-orange-700",
  critical: "border-red-300 bg-red-50 text-red-700",
};

const LEVEL_BAR: Record<CorridorRisk["risk_level"], string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-orange-500",
  critical: "bg-red-500",
};

const ACTION_LABEL: Record<string, string> = {
  pre_emptive_reroute: "Pre-emptive reroute",
  alert_coordinators: "Alert coordinators",
  continue_monitoring: "Monitor",
  monitor: "Monitor",
};

export function DisruptionRadar() {
  const [pred, setPred] = useState<DisruptionPrediction | null>(null);
  const [anoms, setAnoms] = useState<AnomalyEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [p, a] = await Promise.all([
          api.get<DisruptionPrediction>("/api/ml/risk-corridors"),
          api.get<AnomalyEvent[]>("/api/ml/anomalies?hours=4&limit=8"),
        ]);
        if (!cancelled) {
          setPred(p);
          setAnoms(a);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load");
      }
    }
    void load();
    const id = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const corridors = pred?.corridors ?? [];
  const sorted = [...corridors].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <Card className="border-orange-200 bg-gradient-to-br from-orange-50/40 to-white">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-orange-100">
              <Radar className="h-4 w-4 text-orange-600" />
            </div>
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                Disruption Radar
                <span className="inline-flex items-center gap-1 rounded-full border border-orange-200 bg-orange-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-orange-700">
                  IsolationForest + Gemini
                </span>
              </CardTitle>
              <CardDescription className="text-xs">
                Continuous transit-data analysis · pre-emptive reroute when corridor risk &gt; 0.7
              </CardDescription>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-xs text-muted-foreground">
              {pred ? `${pred.total_at_risk_shipments} at-risk` : "—"}
            </div>
            <div className="font-mono text-[10px] text-muted-foreground/70">
              {pred?.model_version}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-xs text-destructive">
            {error}
          </div>
        )}

        {/* Corridor risk grid */}
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <GitBranch className="h-3 w-3" />
            <span>Corridors monitored ({corridors.length})</span>
          </div>

          {!pred && !error && (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-muted" />
              ))}
            </div>
          )}

          {pred && (
            <ul className="space-y-1.5">
              {sorted.map((c) => (
                <li
                  key={c.corridor_id}
                  className="rounded-md border bg-white/70 p-2.5 transition hover:shadow-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">{c.corridor_name}</span>
                        <span
                          className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${LEVEL_TINT[c.risk_level]}`}
                        >
                          {c.risk_level}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={`h-full ${LEVEL_BAR[c.risk_level]} transition-[width] duration-700`}
                            style={{ width: `${(c.risk_score * 100).toFixed(0)}%` }}
                          />
                        </div>
                        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                          {(c.risk_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-xs font-medium text-orange-700">
                        {ACTION_LABEL[c.recommended_action] ?? c.recommended_action.replace("_", " ")}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {c.affected_shipment_ids.length} ship · +{c.predicted_delay_min}m
                      </div>
                    </div>
                  </div>
                  {c.factors.length > 0 && (
                    <details className="mt-1.5">
                      <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-muted-foreground hover:text-foreground">
                        {c.factors.length} risk factor{c.factors.length === 1 ? "" : "s"}
                      </summary>
                      <ul className="mt-1 space-y-0.5 pl-3 text-[11px] text-muted-foreground">
                        {c.factors.map((f, i) => (
                          <li key={i} className="list-disc">{f}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Anomaly stream */}
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Activity className="h-3 w-3" />
            <span>
              Recent anomalies ({anoms?.length ?? 0})
              <span className="ml-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-orange-500" />
            </span>
          </div>

          {!anoms && !error && (
            <div className="space-y-1.5">
              {[0, 1].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded bg-muted" />
              ))}
            </div>
          )}

          {anoms && anoms.length === 0 && (
            <p className="rounded-md border border-dashed py-3 text-center text-xs text-muted-foreground">
              No anomalies detected in the last 4 hours. The IsolationForest is monitoring live pings.
            </p>
          )}

          {anoms && anoms.length > 0 && (
            <ul className="-mx-1 max-h-[180px] divide-y overflow-y-auto">
              {anoms.map((a) => (
                <li key={a.id} className="flex items-start gap-2 px-1 py-2">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-xs font-medium capitalize">
                        {a.anomaly_type.replace("_", " ")}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                        score {(a.score * 100).toFixed(0)}% · conf {(a.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                      {a.recommended_action.replace(/_/g, " ")}
                      {a.detected_at && ` · ${formatAge(a.detected_at)}`}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function formatAge(iso: string): string {
  const sec = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}
