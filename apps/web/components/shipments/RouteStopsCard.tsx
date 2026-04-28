"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type Stop = {
  shipmentId: string;
  address: string;
  etaArrive: string | null;
  etaDepart: string | null;
  stopType: string;
  location: { lat: number; lng: number } | { latitude: number; longitude: number };
};

type RouteDoc = {
  id: string;
  vehicleId: string;
  volunteerId: string | null;
  stops: Stop[];
  totalKm: number;
  totalMin: number;
  computedBy: "gmpro" | "ortools";
  blockedAreasApplied: boolean;
};

function fmt(ts: string | null): string {
  if (!ts) return "—";
  try {
    return format(new Date(ts), "HH:mm");
  } catch {
    return "—";
  }
}

function locStr(loc: Stop["location"]): string {
  if ("lat" in loc) return `${loc.lat.toFixed(4)}, ${loc.lng.toFixed(4)}`;
  return `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`;
}

export function RouteStopsCard({
  routeId,
  shipmentId,
}: {
  routeId: string | null | undefined;
  shipmentId: string;
}) {
  const [route, setRoute] = useState<RouteDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!routeId) {
      setRoute(null);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<RouteDoc>(`/api/routes/${routeId}`);
        if (!cancelled) setRoute(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load route");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [routeId]);

  if (!routeId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Route</CardTitle>
          <CardDescription>
            No route computed yet. Run <code>POST /api/routes/optimize</code> with this shipment&apos;s ID,
            or click <em>Optimize routes</em> on the shipments page (COMMIT 7).
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Route</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!route) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Route</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading route…</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">Route stops</CardTitle>
            <CardDescription>
              {route.stops.length} stop{route.stops.length === 1 ? "" : "s"} ·{" "}
              {route.totalKm.toFixed(1)} km · {route.totalMin} min
            </CardDescription>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-mono">
              {route.computedBy === "gmpro" ? "Google Route Opt" : "OR-Tools VRPTW"}
            </span>
            {route.blockedAreasApplied && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                blocked-area aware
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ol className="relative space-y-4 border-l border-muted pl-5 text-sm">
          {route.stops.map((s, i) => {
            const isMine = s.shipmentId === shipmentId;
            return (
              <li key={`${s.shipmentId}-${i}`} className="ml-2">
                <span
                  className={`absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full ${
                    isMine ? "bg-primary" : "bg-muted-foreground/30"
                  }`}
                />
                <div className="flex items-baseline justify-between">
                  <div>
                    <div className={isMine ? "font-medium" : "text-muted-foreground"}>
                      Stop {i + 1} ·{" "}
                      <span className="font-mono text-xs">{s.shipmentId.slice(0, 8)}…</span>
                      {isMine && (
                        <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase text-primary">
                          this
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">{s.address || locStr(s.location)}</div>
                  </div>
                  <div className="text-right text-xs">
                    <div>arrive {fmt(s.etaArrive)}</div>
                    <div className="text-muted-foreground">depart {fmt(s.etaDepart)}</div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
