"use client";

import { useEffect, useMemo, useState } from "react";
import { Heart, Leaf, Truck, Users } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type Kpis = {
  activeDisasters: number;
  shipmentsInTransit: number;
  volunteersOnRoute: number;
  kgDeliveredToday: number;
  livesReached: number;
  onTimePct: number;
  avgEtaErrorMin: number;
  co2SavedKg: number;
};

type SeriesPoint = {
  date: string;
  deliveries: number;
  kgDelivered: number;
  livesReached: number;
};

type Looker = { embedUrl: string; reportId: string | null; note: string };

export default function AnalyticsPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [series, setSeries] = useState<SeriesPoint[] | null>(null);
  const [looker, setLooker] = useState<Looker | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [k, s, l] = await Promise.all([
          api.get<Kpis>("/api/analytics/kpis"),
          api.get<SeriesPoint[]>("/api/analytics/timeseries?days=14"),
          api.get<Looker>("/api/analytics/looker-embed"),
        ]);
        if (cancelled) return;
        setKpis(k);
        setSeries(s);
        setLooker(l);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load analytics");
      }
    }
    void load();
    const id = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const totals = useMemo(() => {
    if (!series) return { deliveries: 0, kg: 0, lives: 0 };
    return series.reduce(
      (acc, p) => ({
        deliveries: acc.deliveries + p.deliveries,
        kg: acc.kg + p.kgDelivered,
        lives: acc.lives + p.livesReached,
      }),
      { deliveries: 0, kg: 0, lives: 0 },
    );
  }, [series]);

  return (
    <>
      <AdminTopbar title="Analytics" />
      <main className="flex-1 space-y-6 p-6">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <ImpactCard
            icon={<Heart className="h-5 w-5 text-rose-500" />}
            label="Lives reached (14d)"
            value={totals.lives.toLocaleString()}
            sublabel="≈ 4 beneficiaries per kg delivered"
            sdg="SDG 2 / 3"
          />
          <ImpactCard
            icon={<Truck className="h-5 w-5 text-sky-500" />}
            label="Kg delivered (14d)"
            value={totals.kg.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            sublabel={`${totals.deliveries} shipments`}
            sdg="SDG 9 / 11"
          />
          <ImpactCard
            icon={<Users className="h-5 w-5 text-emerald-500" />}
            label="Volunteers on route"
            value={kpis?.volunteersOnRoute ?? "—"}
            sublabel="Distinct assignees in transit"
            sdg="SDG 11"
          />
          <ImpactCard
            icon={<Leaf className="h-5 w-5 text-emerald-600" />}
            label="CO₂ saved today (kg)"
            value={kpis?.co2SavedKg ?? "—"}
            sublabel="vs naive routing baseline"
            sdg="SDG 13"
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Deliveries · last 14 days</CardTitle>
            <CardDescription>
              Live aggregation from Firestore for the demo. Production target: a SELECT against
              the BigQuery view <code>relief.kpis_daily</code>, materialized via the
              Firestore→BigQuery extension (DDL in BLUEPRINT.md Phase 6 Module 10).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!series ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={series} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                    <defs>
                      <linearGradient id="kgGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(d) => format(parseISO(d as string), "MMM d")}
                    />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ fontSize: 12 }}
                      labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
                      formatter={(v: number, k: string) =>
                        k === "kgDelivered" ? [`${v.toFixed(1)} kg`, "Delivered"] : [v, k]
                      }
                    />
                    <Area
                      type="monotone"
                      dataKey="kgDelivered"
                      stroke="#0ea5e9"
                      fill="url(#kgGrad)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Looker Studio (production dashboard)</CardTitle>
            <CardDescription>
              {looker?.embedUrl
                ? "Embedded report — built against the BigQuery view"
                : "Set LOOKER_EMBED_URL on Cloud Run to embed the published Looker Studio dashboard here."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {looker?.embedUrl ? (
              <iframe
                src={looker.embedUrl}
                className="h-[480px] w-full rounded-md border"
                title="Looker Studio"
              />
            ) : (
              <div className="flex h-32 items-center justify-center rounded-md border-2 border-dashed bg-muted/40 text-sm text-muted-foreground">
                {looker?.note || "Looker iframe will appear here when embed URL is configured."}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function ImpactCard({
  icon,
  label,
  value,
  sublabel,
  sdg,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sublabel: string;
  sdg: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        <p className="mt-1 text-xs text-muted-foreground">{sublabel}</p>
        <p className="mt-2 text-xs text-emerald-700">{sdg}</p>
      </CardContent>
    </Card>
  );
}
