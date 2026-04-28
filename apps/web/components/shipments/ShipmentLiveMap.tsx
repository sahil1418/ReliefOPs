"use client";

/**
 * Wrapper around <LiveShipmentMap> that fetches the route doc + feeds it down.
 *
 * Kept as its own client component so the parent ShipmentDetail can stay focused
 * on the document subscription — and so dynamic-import / SSR-disable boundaries
 * stay tight to the Leaflet code.
 */
import { useEffect, useState } from "react";

import { LiveShipmentMapDynamic } from "@/components/map/LiveShipmentMapDynamic";
import { api, ApiCallError } from "@/lib/api";

type RouteDoc = {
  id: string;
  vehicleId: string;
  stops: Array<{
    location: { lat?: number; lng?: number; latitude?: number; longitude?: number };
    address?: string;
    shipmentId?: string;
    etaArrive?: string;
  }>;
  polyline?: string;
} | null;

export function ShipmentLiveMap({
  volunteerId,
  routeId,
  fallbackLat,
  fallbackLng,
}: {
  shipmentId: string;
  volunteerId: string | null;
  routeId: string | null;
  fallbackLat: number;
  fallbackLng: number;
}) {
  const [route, setRoute] = useState<RouteDoc>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!routeId) {
      setRoute(null);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<NonNullable<RouteDoc>>(`/api/routes/${routeId}`);
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

  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <LiveShipmentMapDynamic
      volunteerId={volunteerId}
      route={route}
      fallbackCenter={{ lat: fallbackLat, lng: fallbackLng }}
    />
  );
}
