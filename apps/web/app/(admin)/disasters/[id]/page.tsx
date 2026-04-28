"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { format } from "date-fns";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import {
  DisasterStatusBadge,
  SeverityBadge,
  UrgencyDot,
} from "@/components/disasters/SeverityBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type Disaster = {
  id: string;
  name: string;
  type: string;
  status: string;
  severityScale: number;
  affectedPopulationEstimate: number;
  declaredAt: string;
  sdgTags: string[];
  bbox?: { west: number; south: number; east: number; north: number };
};

type DemandRequest = {
  id: string;
  source: string;
  items: Array<{ sku: string; qty: number; unit: string }>;
  urgency: number;
  severity: string;
  category: string | null;
  raw: string;
  status: string;
  classifiedBy: string;
  confidence: number;
  createdAt: string;
};

export default function DisasterDetailPage({ params }: { params: { id: string } }) {
  const [disaster, setDisaster] = useState<Disaster | null>(null);
  const [requests, setRequests] = useState<DemandRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function loadAll() {
    try {
      const [d, reqs] = await Promise.all([
        api.get<Disaster>(`/api/disasters/${params.id}`),
        api.get<DemandRequest[]>(`/api/requests?disasterId=${params.id}&limit=100`),
      ]);
      setDisaster(d);
      setRequests(reqs);
    } catch (err) {
      setError(err instanceof ApiCallError ? err.message : "Failed to load");
    }
  }

  useEffect(() => {
    void loadAll();
    const id = window.setInterval(loadAll, 10_000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function createShipment(req: DemandRequest) {
    if (!disaster) return;
    setCreating(true);
    try {
      // Simple "create shipment" path: drop items at the bbox center.
      const center = disaster.bbox
        ? {
            lat: (disaster.bbox.north + disaster.bbox.south) / 2,
            lng: (disaster.bbox.east + disaster.bbox.west) / 2,
          }
        : { lat: 21.45, lng: 92.0 };
      await api.post("/api/shipments", {
        disasterId: disaster.id,
        requestIds: [req.id],
        items: req.items.map((it) => ({
          sku: it.sku,
          qty: Math.ceil(it.qty),
          unit: it.unit,
          warehouseId: "wh-coxs-bazar",
        })),
        originWarehouseId: "wh-coxs-bazar",
        dropoffLocation: center,
        dropoffAddress: `Drop near ${disaster.name}`,
        priority: req.severity === "critical" ? "critical" : req.severity === "high" ? "high" : "normal",
      });
      void loadAll();
    } catch (err) {
      setError(err instanceof ApiCallError ? err.message : "Create shipment failed");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <AdminTopbar title="Disaster" />
      <main className="flex-1 space-y-6 p-6">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {disaster && (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">{disaster.type}</p>
                  <CardTitle className="mt-1 text-2xl">{disaster.name}</CardTitle>
                  <CardDescription>
                    Declared{" "}
                    {disaster.declaredAt
                      ? format(new Date(disaster.declaredAt), "MMM d, yyyy HH:mm")
                      : "—"}{" "}
                    · Severity {disaster.severityScale} / 5
                  </CardDescription>
                </div>
                <DisasterStatusBadge status={disaster.status} />
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <div className="text-muted-foreground">Population</div>
                <div className="font-medium">
                  {disaster.affectedPopulationEstimate.toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Demand requests</div>
                <div className="font-medium">{requests?.length ?? "—"}</div>
              </div>
              <div className="sm:col-span-2">
                <div className="text-muted-foreground">SDGs</div>
                <div className="flex flex-wrap gap-1 pt-1">
                  {disaster.sdgTags.map((tag) => (
                    <span key={tag} className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Demand requests</CardTitle>
            <CardDescription>
              Sorted by urgency (highest first). Severity, urgency, and category come from Gemini 2.5 Flash;
              click <em>Create shipment</em> to dispatch.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {requests === null && <p className="text-sm text-muted-foreground">Loading…</p>}
            {requests && requests.length === 0 && (
              <p className="text-sm text-muted-foreground">No demand requests filed yet for this disaster.</p>
            )}
            {requests && requests.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-2 py-2">Urgency</th>
                      <th className="px-2 py-2">Severity</th>
                      <th className="px-2 py-2">Category</th>
                      <th className="px-2 py-2">Items</th>
                      <th className="px-2 py-2">Source</th>
                      <th className="px-2 py-2">Status</th>
                      <th className="px-2 py-2">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {requests.map((req) => (
                      <tr key={req.id} className="hover:bg-muted/40">
                        <td className="px-2 py-3">
                          <UrgencyDot urgency={req.urgency} />
                        </td>
                        <td className="px-2 py-3">
                          <SeverityBadge severity={req.severity} />
                        </td>
                        <td className="px-2 py-3 text-xs capitalize">{req.category ?? "—"}</td>
                        <td className="px-2 py-3">
                          <details className="cursor-pointer">
                            <summary className="text-xs">
                              {req.items.length} item{req.items.length === 1 ? "" : "s"}
                            </summary>
                            <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">
                              {req.items.map((it, i) => (
                                <li key={`${it.sku}-${i}`}>
                                  <span className="font-mono">{it.sku}</span> · {it.qty} {it.unit}
                                </li>
                              ))}
                            </ul>
                            <p className="mt-1 max-w-md text-xs italic text-muted-foreground">{req.raw}</p>
                          </details>
                        </td>
                        <td className="px-2 py-3 text-xs uppercase">{req.source}</td>
                        <td className="px-2 py-3 text-xs capitalize">{req.status}</td>
                        <td className="px-2 py-3">
                          {req.status === "pending" && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={creating}
                              onClick={() => createShipment(req)}
                            >
                              Create shipment
                            </Button>
                          )}
                          {req.status !== "pending" && (
                            <Link
                              href="/shipments"
                              className="text-xs text-primary underline-offset-4 hover:underline"
                            >
                              View shipments
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
