"use client";

/**
 * Volunteers — roster view sourced from Firestore `volunteers` enriched with
 * `users/{userId}` (for displayName) and RTDB `/locations/{volunteerId}` (live).
 *
 * No API endpoint exists for this; we read Firestore + RTDB directly via the
 * client SDK, the same way OpsMap does.
 */
import { useEffect, useMemo, useState } from "react";
import { onValue, ref } from "firebase/database";
import { collection, doc, getDoc, onSnapshot } from "firebase/firestore";
import { Star, Truck, Users } from "lucide-react";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { firebaseDb, firebaseRtdb } from "@/lib/firebase";

type Volunteer = {
  id: string;
  userId: string;
  orgId: string;
  status: string;
  vehicleId: string | null;
  skills: string[];
  rating: number;
  lat: number | null;
  lng: number | null;
  lastActiveAt: Date | null;
};

type Ping = {
  lat: number;
  lng: number;
  ts?: string;
  speedKmh?: number;
  shipmentId?: string;
};

const STATUS_COLOURS: Record<string, string> = {
  available: "bg-emerald-100 text-emerald-700 border-emerald-200",
  in_transit: "bg-sky-100 text-sky-700 border-sky-200",
  off_duty: "bg-slate-100 text-slate-600 border-slate-200",
  on_break: "bg-amber-100 text-amber-700 border-amber-200",
};

function formatAge(ts: string | undefined): string {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}

export default function VolunteersPage() {
  const [vols, setVols] = useState<Volunteer[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [pings, setPings] = useState<Record<string, Ping>>({});
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Firestore: subscribe to volunteers collection.
  useEffect(() => {
    const unsub = onSnapshot(
      collection(firebaseDb(), "volunteers"),
      (snap) => {
        const out: Volunteer[] = [];
        snap.forEach((d) => {
          const data = d.data();
          const loc = data.currentLocation as { latitude?: number; longitude?: number } | undefined;
          const last = data.lastActiveAt as { toDate?: () => Date } | undefined;
          out.push({
            id: d.id,
            userId: typeof data.userId === "string" ? data.userId : "",
            orgId: typeof data.orgId === "string" ? data.orgId : "",
            status: typeof data.status === "string" ? data.status : "available",
            vehicleId: typeof data.vehicleId === "string" ? data.vehicleId : null,
            skills: Array.isArray(data.skills) ? data.skills.filter((s): s is string => typeof s === "string") : [],
            rating: typeof data.rating === "number" ? data.rating : 0,
            lat: loc?.latitude ?? null,
            lng: loc?.longitude ?? null,
            lastActiveAt: last?.toDate ? last.toDate() : null,
          });
        });
        setVols(out);
        setLoaded(true);
      },
      (err) => setError(err.message),
    );
    return () => unsub();
  }, []);

  // Firestore: lazily fetch users/{uid} for displayName, once per uid.
  useEffect(() => {
    const unknown = vols.filter((v) => v.userId && !v.userId.startsWith("phantom-") && !(v.userId in names));
    if (unknown.length === 0) return;
    let cancelled = false;
    void (async () => {
      const next: Record<string, string> = {};
      for (const v of unknown) {
        try {
          const snap = await getDoc(doc(firebaseDb(), "users", v.userId));
          const display = snap.data()?.displayName as string | undefined;
          if (display) next[v.userId] = display;
        } catch {
          // ignore — the Firestore rules may forbid cross-user reads outside admin
        }
      }
      if (!cancelled && Object.keys(next).length > 0) {
        setNames((prev) => ({ ...prev, ...next }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [vols, names]);

  // RTDB: subscribe to live pings.
  useEffect(() => {
    const unsub = onValue(ref(firebaseRtdb(), "locations"), (snap) => {
      const v = (snap.val() ?? {}) as Record<string, Ping>;
      const cleaned: Record<string, Ping> = {};
      for (const [uid, p] of Object.entries(v)) {
        if (p && typeof p.lat === "number" && typeof p.lng === "number") cleaned[uid] = p;
      }
      setPings(cleaned);
    });
    return () => unsub();
  }, []);

  const stats = useMemo(() => {
    const out = { total: vols.length, available: 0, in_transit: 0, live: Object.keys(pings).length };
    for (const v of vols) {
      if (v.status === "available") out.available++;
      else if (v.status === "in_transit") out.in_transit++;
    }
    return out;
  }, [vols, pings]);

  return (
    <>
      <AdminTopbar title="Volunteers" />
      <main className="flex-1 space-y-6 p-6">
        <p className="text-sm text-muted-foreground">
          Active volunteer roster from Firestore <code>volunteers</code>, enriched with live GPS pings
          from Firebase Realtime DB <code>/locations/*</code>. Pings refresh in real time.
        </p>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Total" value={stats.total} />
          <StatCard label="Available" value={stats.available} accent="text-emerald-600" />
          <StatCard label="In transit" value={stats.in_transit} accent="text-sky-600" />
          <StatCard label="Live GPS pings" value={stats.live} accent="text-amber-600" />
        </div>

        {!loaded && <p className="text-sm text-muted-foreground">Loading volunteers…</p>}

        {loaded && vols.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">No volunteers seeded</CardTitle>
              <CardDescription>
                Run <code>pnpm seed</code> to populate the <code>volunteers</code> collection.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {loaded && vols.length > 0 && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {vols.map((v) => {
              const ping = pings[v.id];
              const name = names[v.userId] ?? prettyId(v.id, v.userId);
              const statusClass = STATUS_COLOURS[v.status] ?? "bg-slate-100 text-slate-600 border-slate-200";
              return (
                <Card key={v.id} className="h-full">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                          <Users className="h-3.5 w-3.5" />
                          <span className="font-mono">{v.id}</span>
                          {ping && (
                            <span className="ml-1 inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                              LIVE
                            </span>
                          )}
                        </div>
                        <CardTitle className="mt-1 text-base">{name}</CardTitle>
                        <CardDescription className="mt-0.5 font-mono text-[11px]">
                          {v.orgId}
                        </CardDescription>
                      </div>
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${statusClass}`}
                      >
                        {v.status.replace("_", " ")}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center gap-3 text-sm">
                      <div className="flex items-center gap-1">
                        <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                        <span className="font-medium">{v.rating.toFixed(1)}</span>
                      </div>
                      {v.vehicleId && (
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Truck className="h-3.5 w-3.5" />
                          <span className="font-mono text-xs">{v.vehicleId}</span>
                        </div>
                      )}
                    </div>

                    {v.skills.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {v.skills.map((s) => (
                          <span
                            key={s}
                            className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {s.replace("_", " ")}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2 border-t pt-3 text-xs">
                      <div>
                        <div className="text-muted-foreground">Last seen</div>
                        <div className="font-medium">
                          {ping ? formatAge(ping.ts) : v.lastActiveAt ? formatAge(v.lastActiveAt.toISOString()) : "—"}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Speed</div>
                        <div className="font-medium">
                          {ping && typeof ping.speedKmh === "number"
                            ? `${ping.speedKmh.toFixed(0)} km/h`
                            : "—"}
                        </div>
                      </div>
                      {(ping || (v.lat != null && v.lng != null)) && (
                        <div className="col-span-2">
                          <div className="text-muted-foreground">Position</div>
                          <div className="font-mono text-[11px]">
                            {ping
                              ? `${ping.lat.toFixed(4)}, ${ping.lng.toFixed(4)}`
                              : `${v.lat?.toFixed(4)}, ${v.lng?.toFixed(4)}`}
                          </div>
                        </div>
                      )}
                      {ping?.shipmentId && (
                        <div className="col-span-2">
                          <div className="text-muted-foreground">Active shipment</div>
                          <div className="font-mono text-[11px]">{ping.shipmentId}</div>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className={`text-2xl font-semibold ${accent ?? ""}`}>{value}</div>
        <div className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

function prettyId(volId: string, userId: string): string {
  if (userId.startsWith("phantom-")) {
    const n = volId.replace(/^vol-0?/, "");
    return `Volunteer ${n}`;
  }
  return volId;
}
