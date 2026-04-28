"use client";

import { useEffect, useState } from "react";
import { doc, onSnapshot, type DocumentData } from "firebase/firestore";
import { format } from "date-fns";

import { firebaseDb } from "@/lib/firebase";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PriorityBadge, StatusBadge } from "@/components/shipments/StatusBadge";
import { RouteStopsCard } from "@/components/shipments/RouteStopsCard";
import { ShipmentLiveMap } from "@/components/shipments/ShipmentLiveMap";

export function ShipmentDetail({ shipmentId }: { shipmentId: string }) {
  const [data, setData] = useState<DocumentData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ref = doc(firebaseDb(), "shipments", shipmentId);
    const unsub = onSnapshot(
      ref,
      (snap) => {
        setData(snap.exists() ? { id: snap.id, ...snap.data() } : null);
        setLoading(false);
      },
      (err) => {
        setError(err.message);
        setLoading(false);
      },
    );
    return unsub;
  }, [shipmentId]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!data) return <p className="text-sm text-muted-foreground">Shipment not found.</p>;

  const items = (data.items ?? []) as Array<{ sku: string; qty: number; unit: string; unitWeight_kg?: number }>;
  const dropoff = data.dropoffLocation as { latitude?: number; longitude?: number; lat?: number; lng?: number } | undefined;
  const lat = dropoff?.latitude ?? dropoff?.lat;
  const lng = dropoff?.longitude ?? dropoff?.lng;

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="font-mono text-base">{shipmentId}</CardTitle>
              <CardDescription>
                Disaster <span className="font-mono">{data.disasterId ?? "—"}</span> ·{" "}
                {(data.totalKg ?? 0).toFixed(1)} kg · {items.length} item{items.length === 1 ? "" : "s"}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <PriorityBadge priority={data.priority ?? "normal"} />
              <StatusBadge status={data.status ?? "created"} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <section>
            <h3 className="mb-2 text-sm font-semibold">Items</h3>
            <ul className="divide-y rounded-md border">
              {items.map((it, i) => (
                <li key={`${it.sku}-${i}`} className="flex items-center justify-between px-4 py-2 text-sm">
                  <span className="font-mono text-xs">{it.sku}</span>
                  <span>{it.qty} {it.unit}</span>
                  <span className="text-xs text-muted-foreground">
                    {(it.unitWeight_kg ?? 0).toFixed(2)} kg/unit
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Dropoff</h3>
            <p className="text-sm">{data.dropoffAddress ?? "—"}</p>
            {lat !== undefined && lng !== undefined && (
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {lat.toFixed(5)}, {lng.toFixed(5)}
              </p>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Live map</h3>
              <span className="text-xs text-muted-foreground">
                Updates from Realtime DB · OpenStreetMap tiles
              </span>
            </div>
            <ShipmentLiveMap
              shipmentId={shipmentId}
              volunteerId={(data.assignedVolunteerId as string | undefined) ?? null}
              routeId={(data.routeId as string | undefined) ?? null}
              fallbackLat={lat ?? 21.4272}
              fallbackLng={lng ?? 92.0058}
            />
          </section>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Assigned volunteer</CardTitle>
          </CardHeader>
          <CardContent>
            {data.assignedVolunteerId ? (
              <>
                <p className="font-mono text-xs">{data.assignedVolunteerId}</p>
                {data.vehicleId && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Vehicle: <span className="font-mono">{data.vehicleId}</span>
                  </p>
                )}
                {typeof data.matchScore === "number" && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Auto-match score: {data.matchScore}
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Unassigned</p>
            )}
          </CardContent>
        </Card>

        <RouteStopsCard routeId={data.routeId ?? null} shipmentId={shipmentId} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Timeline</CardTitle>
            <CardDescription>Status transitions read from audit_logs in COMMIT 4.5+.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="relative space-y-4 border-l border-muted pl-4 text-sm">
              <TimelineEvent label="Created" at={data.createdAt} active />
              <TimelineEvent label="Assigned" at={data.status !== "created" ? data.createdAt : null} active={data.status !== "created"} />
              <TimelineEvent
                label="In transit"
                at={data.status === "in_transit" || data.status === "delivered" ? data.createdAt : null}
                active={data.status === "in_transit" || data.status === "delivered"}
              />
              <TimelineEvent label="Delivered" at={data.deliveredAt} active={data.status === "delivered"} />
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TimelineEvent({
  label,
  at,
  active,
}: {
  label: string;
  at: unknown;
  active: boolean;
}) {
  let formatted: string | null = null;
  if (at && typeof at === "object" && "toDate" in at && typeof (at as { toDate: unknown }).toDate === "function") {
    try {
      formatted = format((at as { toDate: () => Date }).toDate(), "MMM d, HH:mm:ss");
    } catch {
      formatted = null;
    }
  }
  return (
    <li className="ml-2">
      <span
        className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${
          active ? "bg-primary" : "bg-muted-foreground/30"
        }`}
      />
      <div className={active ? "font-medium" : "text-muted-foreground"}>{label}</div>
      {formatted && <div className="text-xs text-muted-foreground">{formatted}</div>}
    </li>
  );
}
