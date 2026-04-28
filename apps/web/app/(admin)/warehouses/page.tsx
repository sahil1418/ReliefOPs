"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Snowflake, Warehouse, AlertCircle } from "lucide-react";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { StockBars, type StockByCategory } from "@/components/inventory/StockBars";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type Summary = {
  warehouseId: string;
  name: string;
  address: string;
  location: { lat: number; lng: number };
  coldChainCapable: boolean;
  capacityKg: number;
  totalQty: number;
  totalReservedQty: number;
  totalKgInStock: number;
  itemsByCategory: StockByCategory;
  distinctSkus: number;
  expiringSoon: number;
};

export default function WarehousesPage() {
  const [rows, setRows] = useState<Summary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<Summary[]>("/api/warehouses/stock");
        if (!cancelled) setRows(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load");
      }
    }
    void load();
    const id = window.setInterval(load, 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <>
      <AdminTopbar title="Warehouses" />
      <main className="flex-1 space-y-6 p-6">
        <p className="text-sm text-muted-foreground">
          Per-warehouse stock summary, refreshed every 20s. Click a warehouse to inspect inventory,
          search by SKU/category, and see expiry warnings.
        </p>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!rows && !error && <p className="text-sm text-muted-foreground">Loading…</p>}

        {rows && rows.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">No warehouses configured</CardTitle>
              <CardDescription>
                Use <code>POST /api/warehouses</code> to register your first warehouse.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {rows && rows.length > 0 && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {rows.map((w) => {
              const utilization = Math.min(
                100,
                Math.round((w.totalKgInStock / Math.max(1, w.capacityKg)) * 100),
              );
              return (
                <Link key={w.warehouseId} href={`/warehouses/${w.warehouseId}`}>
                  <Card className="h-full transition-shadow hover:shadow-md">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                            <Warehouse className="h-3.5 w-3.5" />
                            <span className="font-mono">{w.warehouseId}</span>
                          </div>
                          <CardTitle className="mt-1 text-base">{w.name}</CardTitle>
                          <CardDescription className="mt-0.5">{w.address}</CardDescription>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          {w.coldChainCapable && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700">
                              <Snowflake className="h-3 w-3" /> cold chain
                            </span>
                          )}
                          {w.expiringSoon > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                              <AlertCircle className="h-3 w-3" />
                              {w.expiringSoon} expiring
                            </span>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="rounded-md border bg-background p-2">
                          <div className="text-lg font-semibold">{w.distinctSkus}</div>
                          <div className="text-xs text-muted-foreground">SKUs</div>
                        </div>
                        <div className="rounded-md border bg-background p-2">
                          <div className="text-lg font-semibold">{Math.round(w.totalQty).toLocaleString()}</div>
                          <div className="text-xs text-muted-foreground">units avail</div>
                        </div>
                        <div className="rounded-md border bg-background p-2">
                          <div className="text-lg font-semibold">{Math.round(w.totalReservedQty).toLocaleString()}</div>
                          <div className="text-xs text-muted-foreground">reserved</div>
                        </div>
                      </div>

                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Capacity</span>
                          <span className="font-medium">{utilization}% used</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${utilization}%` }}
                          />
                        </div>
                        <div className="mt-1 text-right text-xs text-muted-foreground">
                          {w.totalKgInStock.toLocaleString()} / {w.capacityKg.toLocaleString()} kg
                        </div>
                      </div>

                      <div>
                        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                          Stock by category
                        </p>
                        <StockBars totals={w.itemsByCategory} />
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
