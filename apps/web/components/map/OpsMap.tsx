"use client";

/**
 * OpsMap — operational disaster + fleet view (replaces FleetMap on /dashboard).
 *
 * Visual style: dark CARTO tiles, neon overlays, pulsing severity-coloured
 * markers, heatmap mode, filter chips.
 *
 * Data sources:
 *   - Firestore `disasters` (one pulse per active disaster, severity-coloured)
 *   - RTDB `/locations/*` (one pin per live volunteer)
 *
 * Polylines + per-shipment routing live in LiveShipmentMap; this is the
 * city-scale ops view.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import { onValue, ref } from "firebase/database";
import { collection, onSnapshot } from "firebase/firestore";

import { firebaseDb, firebaseRtdb } from "@/lib/firebase";

import "leaflet/dist/leaflet.css";

// Inject CSS keyframes once on the client (Leaflet markers are HTML divs).
if (typeof window !== "undefined" && !document.getElementById("ops-map-styles")) {
  const style = document.createElement("style");
  style.id = "ops-map-styles";
  style.textContent = `
    @keyframes ops-pulse {
      0%   { transform: scale(1);   opacity: 1;   }
      70%  { transform: scale(2.4); opacity: 0;   }
      100% { transform: scale(2.4); opacity: 0;   }
    }
    .ops-pulse-ring {
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      width: 100%; height: 100%;
      border-radius: 9999px;
      animation: ops-pulse 1.6s ease-out infinite;
    }
    .ops-marker-core {
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      border-radius: 9999px;
      box-shadow: 0 0 12px currentColor;
    }
    .leaflet-container { background: #0f172a !important; }
    .leaflet-popup-content-wrapper {
      background: #0f172a;
      color: #f1f5f9;
      border: 1px solid #334155;
      box-shadow: 0 6px 24px rgba(0,0,0,.6);
    }
    .leaflet-popup-tip { background: #0f172a; }
    .leaflet-control-zoom a {
      background: #1e293b !important;
      color: #f1f5f9 !important;
      border-color: #334155 !important;
    }
  `;
  document.head.appendChild(style);
}

type LatLng = { lat: number; lng: number };

type DisasterMarker = {
  id: string;
  name: string;
  type: string;
  status: string;
  severity: number;
  lat: number;
  lng: number;
  affected: number;
};

type Ping = {
  lat: number;
  lng: number;
  ts?: string;
  speedKmh?: number;
  shipmentId?: string;
  volunteerId?: string;
};

function severityColor(s: number): string {
  // red -> orange -> yellow -> cyan -> emerald, in descending severity.
  if (s >= 5) return "#ef4444";
  if (s === 4) return "#f97316";
  if (s === 3) return "#eab308";
  if (s === 2) return "#22d3ee";
  return "#10b981";
}
const SEVERITY_COLOR = { 5: "#ef4444", 4: "#f97316", 3: "#eab308", 2: "#22d3ee", 1: "#10b981" } as const;

const VOLUNTEER_COLOR = "#60a5fa"; // light blue

function pulseDivIcon(color: string, size = 14): L.DivIcon {
  return L.divIcon({
    html: `
      <div style="position:relative;width:${size}px;height:${size}px;color:${color};">
        <div class="ops-pulse-ring" style="background:${color};opacity:.4;"></div>
        <div class="ops-marker-core" style="width:${size}px;height:${size}px;background:${color};border:2px solid white;"></div>
      </div>`,
    className: "ops-pulse-icon",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function volunteerDivIcon(): L.DivIcon {
  const c = VOLUNTEER_COLOR;
  return L.divIcon({
    html: `
      <div style="position:relative;width:18px;height:18px;color:${c};">
        <div class="ops-pulse-ring" style="background:${c};opacity:.5;"></div>
        <div class="ops-marker-core" style="width:18px;height:18px;background:${c};border:2px solid white;"></div>
      </div>`,
    className: "ops-volunteer-icon",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

// ─── Heatmap layer (uses leaflet.heat) ──────────────────────────────────────
type HeatLayer = L.Layer & { setLatLngs: (pts: Array<[number, number, number?]>) => void };

function HeatmapLayer({ points, enabled }: { points: Array<[number, number, number?]>; enabled: boolean }) {
  const map = useMap();
  const layerRef = useRef<HeatLayer | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    void (async () => {
      // Dynamic import — leaflet.heat attaches to global `L` so it isn't ESM-friendly.
      await import("leaflet.heat");
      if (cancelled) return;
      // @ts-expect-error - L.heatLayer is added by the leaflet.heat plugin
      const layer = L.heatLayer(points, {
        radius: 30,
        blur: 22,
        maxZoom: 17,
        max: 1.0,
        gradient: {
          0.2: "#22d3ee",
          0.4: "#10b981",
          0.6: "#eab308",
          0.8: "#f97316",
          1.0: "#ef4444",
        },
      }) as HeatLayer;
      layerRef.current = layer;
      if (enabled) layer.addTo(map);
    })();
    return () => {
      cancelled = true;
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Toggle visibility + update points when changed.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    if (enabled && !map.hasLayer(layer)) layer.addTo(map);
    if (!enabled && map.hasLayer(layer)) map.removeLayer(layer);
    layer.setLatLngs(points);
  }, [enabled, points, map]);

  return null;
}

// ─── Main component ─────────────────────────────────────────────────────────
type Filter = "all" | "active" | "contained" | "closed";

export function OpsMap({ defaultCenter }: { defaultCenter: LatLng }) {
  const [disasters, setDisasters] = useState<DisasterMarker[]>([]);
  const [pings, setPings] = useState<Record<string, Ping>>({});
  const [filter, setFilter] = useState<Filter>("all");
  const [heatmap, setHeatmap] = useState(false);

  // Subscribe to disasters in Firestore (live updates if new ones get declared).
  useEffect(() => {
    const c = collection(firebaseDb(), "disasters");
    const unsub = onSnapshot(c, (snap) => {
      const out: DisasterMarker[] = [];
      snap.forEach((d) => {
        const data = d.data();
        const center = data.centerLocation as { latitude?: number; longitude?: number } | undefined;
        const bbox = data.bbox as { north: number; south: number; east: number; west: number } | undefined;
        const lat = center?.latitude ?? (bbox ? (bbox.north + bbox.south) / 2 : null);
        const lng = center?.longitude ?? (bbox ? (bbox.east + bbox.west) / 2 : null);
        if (lat == null || lng == null) return;
        out.push({
          id: d.id,
          name: data.name ?? d.id,
          type: data.type ?? "other",
          status: data.status ?? "active",
          severity: typeof data.severityScale === "number" ? data.severityScale : 3,
          lat,
          lng,
          affected: typeof data.affectedPopulationEstimate === "number" ? data.affectedPopulationEstimate : 0,
        });
      });
      setDisasters(out);
    });
    return () => unsub();
  }, []);

  // Subscribe to RTDB live pings.
  useEffect(() => {
    const r = ref(firebaseRtdb(), "locations");
    const unsub = onValue(r, (snap) => {
      const v = (snap.val() ?? {}) as Record<string, Ping>;
      const cleaned: Record<string, Ping> = {};
      for (const [uid, p] of Object.entries(v)) {
        if (p && typeof p.lat === "number" && typeof p.lng === "number") cleaned[uid] = p;
      }
      setPings(cleaned);
    });
    return () => unsub();
  }, []);

  const filtered = useMemo(
    () => (filter === "all" ? disasters : disasters.filter((d) => d.status === filter)),
    [disasters, filter],
  );

  const live = useMemo(() => Object.entries(pings), [pings]);

  // Heatmap inputs: weight disasters by severity, volunteers by 0.5.
  const heatPoints = useMemo<Array<[number, number, number?]>>(() => {
    const pts: Array<[number, number, number?]> = [];
    for (const d of filtered) pts.push([d.lat, d.lng, d.severity / 5]);
    for (const [, p] of live) pts.push([p.lat, p.lng, 0.5]);
    return pts;
  }, [filtered, live]);

  const counts = useMemo(() => {
    const out = { all: disasters.length, active: 0, contained: 0, closed: 0 };
    for (const d of disasters) {
      if (d.status === "active") out.active++;
      else if (d.status === "contained") out.contained++;
      else if (d.status === "closed") out.closed++;
    }
    return out;
  }, [disasters]);

  return (
    <div className="relative h-[480px] w-full overflow-hidden rounded-xl border border-slate-800">
      {/* Top toolbar — CivicLoop-style filter chips + heatmap toggle */}
      <div className="pointer-events-none absolute inset-x-3 top-3 z-[400] flex items-center gap-2">
        <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/85 px-2 py-1 text-xs backdrop-blur">
          <span className="mr-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate-300">ReliefOps Live</span>
        </div>

        <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/85 px-1 py-1 text-xs backdrop-blur">
          {(["all", "active", "contained", "closed"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 transition-colors ${
                filter === f
                  ? "bg-slate-700 text-white"
                  : "text-slate-300 hover:bg-slate-800"
              }`}
            >
              <span className="capitalize">{f}</span>
              <span className="rounded-md bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                {counts[f]}
              </span>
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setHeatmap((h) => !h)}
            className={`pointer-events-auto flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-wider backdrop-blur transition ${
              heatmap
                ? "border-orange-500 bg-orange-500/30 text-orange-200"
                : "border-slate-700 bg-slate-900/85 text-slate-300 hover:bg-slate-800"
            }`}
          >
            <FlameIcon className="h-3.5 w-3.5" />
            Heatmap
          </button>
        </div>
      </div>

      {/* Bottom-left legend */}
      <div className="pointer-events-none absolute bottom-3 left-3 z-[400] rounded-lg border border-slate-700 bg-slate-900/85 px-3 py-2 text-xs text-slate-300 backdrop-blur">
        <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-slate-500">Severity</div>
        <div className="flex items-center gap-3">
          {[5, 4, 3, 2, 1].map((s) => {
            const c = severityColor(s);
            return (
              <div key={s} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: c, boxShadow: `0 0 6px ${c}` }}
                />
                <span className="font-mono text-[10px]">{s}</span>
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: VOLUNTEER_COLOR, boxShadow: `0 0 6px ${VOLUNTEER_COLOR}` }}
          />
          <span className="font-mono text-[10px]">{live.length} volunteer{live.length === 1 ? "" : "s"} live</span>
        </div>
      </div>

      <MapContainer
        center={[defaultCenter.lat, defaultCenter.lng]}
        zoom={5}
        scrollWheelZoom
        zoomControl
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; OpenStreetMap'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        <HeatmapLayer points={heatPoints} enabled={heatmap} />

        {!heatmap &&
          filtered.map((d) => {
            const c = severityColor(d.severity);
            const size = 12 + d.severity * 2;
            return (
              <Marker key={d.id} position={[d.lat, d.lng]} icon={pulseDivIcon(c, size)}>
                <Popup>
                  <div className="text-xs">
                    <div className="font-semibold" style={{ color: c }}>{d.name}</div>
                    <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-slate-400">
                      {d.type} · severity {d.severity}/5 · {d.status}
                    </div>
                    <div className="mt-1.5 text-slate-300">
                      {d.affected.toLocaleString()} affected
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}

        {!heatmap &&
          live.map(([uid, p]) => (
            <Marker key={uid} position={[p.lat, p.lng]} icon={volunteerDivIcon()}>
              <Popup>
                <div className="text-xs">
                  <div className="font-semibold" style={{ color: VOLUNTEER_COLOR }}>Volunteer</div>
                  <div className="mt-1 font-mono text-[10px]">{uid.slice(0, 12)}…</div>
                  {p.shipmentId && (
                    <div className="mt-1 font-mono text-[10px]">ship {p.shipmentId.slice(0, 10)}…</div>
                  )}
                  {typeof p.speedKmh === "number" && (
                    <div className="mt-1">{p.speedKmh.toFixed(0)} km/h</div>
                  )}
                  {p.ts && <div className="mt-0.5 text-slate-400">{new Date(p.ts).toLocaleTimeString()}</div>}
                </div>
              </Popup>
            </Marker>
          ))}

        {!heatmap &&
          live.map(([uid, p]) => (
            <CircleMarker
              key={`pulse-${uid}`}
              center={[p.lat, p.lng]}
              radius={20}
              pathOptions={{ color: VOLUNTEER_COLOR, fillOpacity: 0.05, weight: 1 }}
            />
          ))}
      </MapContainer>
    </div>
  );
}

function FlameIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
    </svg>
  );
}

export default OpsMap;
