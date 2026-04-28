"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Truck, Users, Package } from "lucide-react";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { AIActivityFeed } from "@/components/ai/AIActivityFeed";
import { AIInsightsCard } from "@/components/ai/AIInsightsCard";
import { OpsMapDynamic } from "@/components/map/OpsMapDynamic";
import { DisruptionRadar } from "@/components/ml/DisruptionRadar";
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

export default function DashboardPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<Kpis>("/api/analytics/kpis");
        if (!cancelled) setKpis(data);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiCallError ? err.message : "Failed to load KPIs");
      }
    }
    void load();
    const id = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <>
      <AdminTopbar title="Dashboard" />
      <main className="flex-1 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            title="Active disasters"
            value={kpis?.activeDisasters}
            icon={<AlertTriangle className="h-5 w-5 text-amber-500" />}
            sublabel="declared, status = active"
          />
          <KpiCard
            title="Shipments in transit"
            value={kpis?.shipmentsInTransit}
            icon={<Truck className="h-5 w-5 text-blue-500" />}
            sublabel="status = in_transit"
          />
          <KpiCard
            title="Volunteers on route"
            value={kpis?.volunteersOnRoute}
            icon={<Users className="h-5 w-5 text-emerald-500" />}
            sublabel="distinct assignees in transit"
          />
          <KpiCard
            title="Kg delivered today"
            value={kpis?.kgDeliveredToday}
            icon={<Package className="h-5 w-5 text-violet-500" />}
            sublabel="status = delivered (UTC day)"
            decimals={1}
          />
        </div>

        {error && (
          <p className="mt-4 text-sm text-destructive">
            {error} — is FastAPI running on <code>{process.env.NEXT_PUBLIC_API_BASE_URL}</code>?
          </p>
        )}

        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <AIInsightsCard />
          </div>
          <AIActivityFeed />
        </div>

        <div className="mt-6">
          <DisruptionRadar />
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Operations map</CardTitle>
            <CardDescription>
              Live disaster zones across South Asia plus every active volunteer&apos;s GPS ping
              (15&thinsp;s cadence via Firebase Realtime DB). Severity-coloured pulses, filter by
              status, toggle the heatmap view.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <OpsMapDynamic defaultCenter={{ lat: 22.5, lng: 82 }} />
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Operational KPIs</CardTitle>
            <CardDescription>
              Real-time shipments table on <a className="underline" href="/shipments">/shipments</a>{" "}
              uses Firestore <code>onSnapshot</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Stat label="Lives reached (est.)" value={kpis?.livesReached ?? "—"} />
            <Stat label="On-time %" value={kpis ? `${kpis.onTimePct}%` : "—"} />
            <Stat label="Avg ETA error" value={kpis ? `${kpis.avgEtaErrorMin} min` : "—"} />
            <Stat label="CO₂ saved (kg)" value={kpis?.co2SavedKg ?? "—"} />
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function KpiCard({
  title,
  value,
  icon,
  sublabel,
  decimals = 0,
}: {
  title: string;
  value: number | undefined;
  icon: React.ReactNode;
  sublabel: string;
  decimals?: number;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">
          {value === undefined ? "—" : value.toFixed(decimals)}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{sublabel}</p>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between rounded-md border bg-background p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-lg font-semibold">{value}</span>
    </div>
  );
}
