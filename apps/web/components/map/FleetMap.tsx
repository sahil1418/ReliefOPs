"use client";

/**
 * FleetMap — dashboard-level overview showing every active volunteer pin.
 *
 * Subscribes to RTDB `/locations/*` (one entry per signed-in volunteer pushing
 * pings). Renders a marker for each, refreshing on every push. No route lines.
 */
import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { onValue, ref } from "firebase/database";

import { firebaseRtdb } from "@/lib/firebase";

import "leaflet/dist/leaflet.css";

type Ping = {
  lat: number;
  lng: number;
  ts?: string;
  speedKmh?: number;
  shipmentId?: string;
  volunteerId?: string;
};

const VOLUNTEER_ICON = L.divIcon({
  html: `<div style="
    background:#ef4444;color:white;border-radius:9999px;
    width:28px;height:28px;display:flex;align-items:center;justify-content:center;
    font-size:14px;border:2px solid white;
    box-shadow:0 0 0 3px rgba(239,68,68,.2);
  ">🚚</div>`,
  className: "relief-volunteer-icon",
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

export function FleetMap({ defaultCenter }: { defaultCenter: { lat: number; lng: number } }) {
  const [pings, setPings] = useState<Record<string, Ping>>({});

  useEffect(() => {
    const r = ref(firebaseRtdb(), "locations");
    const unsub = onValue(r, (snap) => {
      const v = (snap.val() ?? {}) as Record<string, Ping>;
      const cleaned: Record<string, Ping> = {};
      for (const [uid, p] of Object.entries(v)) {
        if (p && typeof p.lat === "number" && typeof p.lng === "number") {
          cleaned[uid] = p;
        }
      }
      setPings(cleaned);
    });
    return () => unsub();
  }, []);

  const live = useMemo(() => Object.entries(pings), [pings]);

  return (
    <div className="relative h-[400px] w-full overflow-hidden rounded-md border">
      <MapContainer
        center={[defaultCenter.lat, defaultCenter.lng]}
        zoom={11}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {live.map(([uid, p]) => (
          <Marker key={uid} position={[p.lat, p.lng]} icon={VOLUNTEER_ICON}>
            <Popup>
              <div className="text-xs">
                <div className="font-semibold">Volunteer</div>
                <div className="font-mono">{uid.slice(0, 10)}…</div>
                {p.shipmentId && <div className="font-mono">ship: {p.shipmentId.slice(0, 10)}…</div>}
                {typeof p.speedKmh === "number" && <div>{p.speedKmh.toFixed(0)} km/h</div>}
                {p.ts && <div>{new Date(p.ts).toLocaleTimeString()}</div>}
              </div>
            </Popup>
          </Marker>
        ))}
        {live.map(([uid, p]) => (
          <CircleMarker
            key={`pulse-${uid}`}
            center={[p.lat, p.lng]}
            radius={18}
            pathOptions={{ color: "#ef4444", fillOpacity: 0.05, weight: 1 }}
          />
        ))}
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-white/90 px-3 py-1.5 text-xs font-medium shadow backdrop-blur">
        <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
        {live.length} volunteer{live.length === 1 ? "" : "s"} on route
      </div>
    </div>
  );
}

export default FleetMap;
