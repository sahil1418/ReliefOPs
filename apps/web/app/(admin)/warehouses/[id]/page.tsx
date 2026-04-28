"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { format } from "date-fns";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { ExpiryBadge } from "@/components/inventory/ExpiryBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiCallError } from "@/lib/api";

type Warehouse = {
  id: string;
  name: string;
  address: string;
  location: { lat: number; lng: number };
  capacityKg: number;
  coldChainCapable: boolean;
  contactPhone: string | null;
};

type Item = {
  id: string;
  warehouseId: string;
  sku: string;
  name: string;
  category: string;
  qty: number;
  reservedQty: number;
  lot: string | null;
  expiry: string;
  coldChainRequired: boolean;
  unitWeight_kg: number;
  updatedAt: string | null;
};

const CATEGORIES = ["all", "food", "medicine", "shelter", "water", "rescue", "other"];

export default function WarehouseDetailPage({ params }: { params: { id: string } }) {
  const [warehouse, setWarehouse] = useState<Warehouse | null>(null);
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("all");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [wh, list] = await Promise.all([
          api.get<Warehouse>(`/api/warehouses/${params.id}`),
          api.get<Item[]>(`/api/warehouses/${params.id}/inventory?limit=2000`),
        ]);
        if (!cancelled) {
          setWarehouse(wh);
          setItems(list);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load");
      }
    }
    void load();
    const id = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [params.id]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toLowerCase();
    return items.filter((it) => {
      if (category !== "all" && it.category !== category) return false;
      if (!q) return true;
      return it.sku.toLowerCase().includes(q) || it.name.toLowerCase().includes(q);
    });
  }, [items, search, category]);

  return (
    <>
      <AdminTopbar title="Warehouse" />
      <main className="flex-1 space-y-6 p-6">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {warehouse && (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-2xl">{warehouse.name}</CardTitle>
                  <CardDescription className="mt-1">{warehouse.address}</CardDescription>
                </div>
                <div className="flex flex-col items-end gap-1 text-xs">
                  <span className="font-mono">{warehouse.id}</span>
                  {warehouse.coldChainCapable && (
                    <span className="rounded-full bg-sky-100 px-2 py-0.5 text-sky-700">cold chain</span>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <div className="text-muted-foreground">Capacity</div>
                <div className="font-medium">{warehouse.capacityKg.toLocaleString()} kg</div>
              </div>
              <div>
                <div className="text-muted-foreground">SKUs in stock</div>
                <div className="font-medium">{items?.length ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Location</div>
                <div className="font-mono text-xs">
                  {warehouse.location.lat.toFixed(4)}, {warehouse.location.lng.toFixed(4)}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Contact</div>
                <div className="text-xs">{warehouse.contactPhone ?? "—"}</div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-lg">Inventory</CardTitle>
                <CardDescription>
                  Search by SKU or name; filter by category. Reserved units are atomically held by
                  active shipments.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="search"
                    placeholder="Search SKU or name…"
                    className="h-9 w-56 pl-8"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {items === null ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {search || category !== "all" ? "No items match the filter." : "No inventory yet."}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-2 py-2">SKU</th>
                      <th className="px-2 py-2">Name</th>
                      <th className="px-2 py-2">Category</th>
                      <th className="px-2 py-2 text-right">Available</th>
                      <th className="px-2 py-2 text-right">Reserved</th>
                      <th className="px-2 py-2 text-right">Unit kg</th>
                      <th className="px-2 py-2">Lot</th>
                      <th className="px-2 py-2">Expiry</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {filtered.map((it) => {
                      const days = Math.ceil(
                        (new Date(it.expiry).getTime() - Date.now()) / 86_400_000,
                      );
                      return (
                        <tr key={it.id} className="hover:bg-muted/40">
                          <td className="px-2 py-2 font-mono text-xs">{it.sku}</td>
                          <td className="px-2 py-2">{it.name}</td>
                          <td className="px-2 py-2 text-xs capitalize">{it.category}</td>
                          <td className="px-2 py-2 text-right tabular-nums">
                            {Math.round(it.qty).toLocaleString()}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
                            {Math.round(it.reservedQty).toLocaleString()}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums">
                            {it.unitWeight_kg.toFixed(2)}
                          </td>
                          <td className="px-2 py-2 text-xs">{it.lot ?? "—"}</td>
                          <td className="px-2 py-2">
                            <div className="flex items-center gap-2">
                              <ExpiryBadge daysToExpiry={days} />
                              <span className="text-xs text-muted-foreground">
                                {format(new Date(it.expiry), "MMM d, yyyy")}
                              </span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
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
