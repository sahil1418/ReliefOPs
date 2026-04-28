"use client";

/**
 * LiveShipmentMap — admin-side live tracker for one shipment.
 *
 * Architecture (BLUEPRINT Phase 6 Module 6):
 *   Volunteer → Firestore RTDB `/locations/{volunteerId}` (every 15s)
 *   This component subscribes to that path via the Firebase web SDK
 *   `onValue` listener and re-renders the volunteer pin smoothly each ping.
 *
 * Tile provider: OpenStreetMap (free, no API key). When Maps Platform billing
 * is enabled, swap the TileLayer URL to Google Maps tiles or migrate to
 * `@vis.gl/react-google-maps` per the production deck. The shipment data and
 * RTDB wiring stay identical.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import { onValue, ref } from "firebase/database";

import { firebaseRtdb } from "@/lib/firebase";

import "leaflet/dist/leaflet.css";

type LatLng = { lat: number; lng: number };

type RouteShape = {
  stops: Array<{
    location: { lat?: number; lng?: number; latitude?: number; longitude?: number };
    address?: string;
    shipmentId?: string;
    etaArrive?: string;
  }>;
  polyline?: string;
} | null;

const VOLUNTEER_ICON = L.divIcon({
  html: `
    <div style="
      background: #ef4444; color: white; border-radius: 9999px;
      width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
      box-shadow: 0 0 0 4px rgba(239,68,68,.25);
      font-size: 16px; transition: transform 200ms ease;
    ">🚚</div>`,
  className: "relief-volunteer-icon",
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

const STOP_ICON = L.divIcon({
  html: `
    <div style="
      background: #0ea5e9; color: white; border-radius: 9999px;
      width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
      font-size: 10px; font-weight: 600; border: 2px solid white;
      box-shadow: 0 1px 4px rgba(0,0,0,.2);
    ">●</div>`,
  className: "relief-stop-icon",
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const DEPOT_ICON = L.divIcon({
  html: `
    <div style="
      background: #0f172a; color: white; border-radius: 6px;
      width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
      font-size: 12px; border: 2px solid white;
      box-shadow: 0 1px 4px rgba(0,0,0,.25);
    ">🏭</div>`,
  className: "relief-depot-icon",
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function parsePolyline(polyline?: string): LatLng[] {
  if (!polyline) return [];
  try {
    const arr = JSON.parse(polyline) as Array<[number, number]>;
    return arr.map(([lat, lng]) => ({ lat, lng }));
  } catch {
    return [];
  }
}

function normalizeStop(loc: unknown): LatLng | null {
  if (!loc || typeof loc !== "object") return null;
  const o = loc as Record<string, unknown>;
  if (typeof o.lat === "number" && typeof o.lng === "number") {
    return { lat: o.lat, lng: o.lng };
  }
  if (typeof o.latitude === "number" && typeof o.longitude === "number") {
    return { lat: o.latitude, lng: o.longitude };
  }
  return null;
}

function FollowVolunteer({ pos, enabled }: { pos: LatLng | null; enabled: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!enabled || !pos) return;
    map.panTo([pos.lat, pos.lng], { animate: true, duration: 0.6 });
  }, [pos, enabled, map]);
  return null;
}

export function LiveShipmentMap({
  volunteerId,
  route,
  fallbackCenter,
}: {
  volunteerId: string | null;
  route: RouteShape;
  fallbackCenter: LatLng;
}) {
  const [pos, setPos] = useState<LatLng | null>(null);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const lastPosRef = useRef<LatLng | null>(null);

  useEffect(() => {
    if (!volunteerId) {
      setPos(null);
      return;
    }
    const r = ref(firebaseRtdb(), `locations/${volunteerId}`);
    const unsub = onValue(r, (snap) => {
      const v = snap.val();
      if (!v || typeof v.lat !== "number" || typeof v.lng !== "number") return;
      const next = { lat: v.lat, lng: v.lng };
      lastPosRef.current = next;
      setPos(next);
      setLastTs(typeof v.ts === "string" ? v.ts : new Date().toISOString());
    });
    return () => unsub();
  }, [volunteerId]);

  const stops = useMemo(() => {
    if (!route) return [];
    type StopOut = {
      loc: LatLng;
      address: string;
      shipmentId: string | undefined;
      etaArrive: string | undefined;
    };
    const out: StopOut[] = [];
    for (const s of route.stops) {
      const loc = normalizeStop(s.location);
      if (!loc) continue;
      out.push({
        loc,
        address: s.address ?? "",
        shipmentId: s.shipmentId,
        etaArrive: s.etaArrive,
      });
    }
    return out;
  }, [route]);

  const polylinePoints = useMemo(() => parsePolyline(route?.polyline), [route?.polyline]);

  const center = pos ?? stops[0]?.loc ?? fallbackCenter;
  const depot = polylinePoints[0] ?? null;

  const stale = lastTs && Date.now() - new Date(lastTs).getTime() > 30_000;

  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-md border">
      <MapContainer
        center={[center.lat, center.lng]}
        zoom={12}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {polylinePoints.length >= 2 && (
          <Polyline positions={polylinePoints.map((p) => [p.lat, p.lng])} pathOptions={{ color: "#0ea5e9", weight: 4, opacity: 0.7 }} />
        )}

        {depot && (
          <Marker position={[depot.lat, depot.lng]} icon={DEPOT_ICON}>
            <Popup>Origin warehouse</Popup>
          </Marker>
        )}

        {stops.map((s, i) => (
          <Marker
            key={`${s.shipmentId ?? "stop"}-${i}`}
            position={[s.loc.lat, s.loc.lng]}
            icon={STOP_ICON}
          >
            <Popup>
              <div className="text-xs">
                <div className="font-semibold">Stop {i + 1}</div>
                {s.address && <div>{s.address}</div>}
                {s.etaArrive && <div className="text-muted-foreground">ETA {new Date(s.etaArrive).toLocaleTimeString()}</div>}
                {s.shipmentId && <div className="font-mono">{s.shipmentId.slice(0, 10)}…</div>}
              </div>
            </Popup>
          </Marker>
        ))}

        {pos && (
          <>
            <Marker position={[pos.lat, pos.lng]} icon={VOLUNTEER_ICON}>
              <Popup>
                <div className="text-xs">
                  <div className="font-semibold">Volunteer</div>
                  <div>Last ping: {lastTs ? new Date(lastTs).toLocaleTimeString() : "—"}</div>
                </div>
              </Popup>
            </Marker>
            <CircleMarker
              center={[pos.lat, pos.lng]}
              radius={20}
              pathOptions={{ color: "#ef4444", fillOpacity: 0.1, weight: 1 }}
            />
          </>
        )}

        <FollowVolunteer pos={pos} enabled={follow} />
      </MapContainer>

      {/* HUD overlay */}
      <div className="pointer-events-none absolute left-3 top-3 flex flex-col gap-2">
        <div className="pointer-events-auto rounded-md bg-white/90 px-3 py-1.5 text-xs shadow backdrop-blur">
          {!volunteerId && <span className="text-muted-foreground">No volunteer assigned yet</span>}
          {volunteerId && !pos && <span className="text-muted-foreground">Waiting for first ping…</span>}
          {volunteerId && pos && (
            <span>
              <span className={`mr-2 inline-block h-2 w-2 rounded-full ${stale ? "bg-amber-500" : "bg-emerald-500"} ${stale ? "" : "animate-pulse"}`} />
              {stale ? "Stale" : "Live"} ·{" "}
              <span className="font-mono">{pos.lat.toFixed(4)}, {pos.lng.toFixed(4)}</span>
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setFollow((f) => !f)}
          className="pointer-events-auto self-start rounded-md bg-white/90 px-3 py-1.5 text-xs font-medium shadow backdrop-blur"
        >
          {follow ? "✓ Following" : "Follow volunteer"}
        </button>
      </div>
    </div>
  );
}

export default LiveShipmentMap;
