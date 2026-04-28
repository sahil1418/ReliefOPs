"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  collection,
  limit as fsLimit,
  onSnapshot,
  orderBy,
  query,
  type DocumentData,
  type QueryDocumentSnapshot,
} from "firebase/firestore";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { format } from "date-fns";

import { firebaseDb } from "@/lib/firebase";
import { PriorityBadge, StatusBadge } from "@/components/shipments/StatusBadge";

export type ShipmentRow = {
  id: string;
  status: string;
  priority: string;
  disasterId: string;
  assignedVolunteerId: string | null;
  totalKg: number;
  etaCurrent: Date | null;
  createdAt: Date | null;
};

function snapshotToRow(snap: QueryDocumentSnapshot<DocumentData>): ShipmentRow {
  const data = snap.data();
  const toDate = (v: unknown): Date | null => {
    if (!v) return null;
    if (v instanceof Date) return v;
    // Firestore Timestamp
    if (typeof v === "object" && v !== null && "toDate" in v && typeof (v as { toDate: unknown }).toDate === "function") {
      return (v as { toDate: () => Date }).toDate();
    }
    return null;
  };
  return {
    id: snap.id,
    status: (data.status as string) ?? "created",
    priority: (data.priority as string) ?? "normal",
    disasterId: (data.disasterId as string) ?? "",
    assignedVolunteerId: (data.assignedVolunteerId as string | null) ?? null,
    totalKg: Number(data.totalKg ?? 0),
    etaCurrent: toDate(data.etaCurrent),
    createdAt: toDate(data.createdAt),
  };
}

export function ShipmentsTable() {
  const [rows, setRows] = useState<ShipmentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const db = firebaseDb();
    const q = query(collection(db, "shipments"), orderBy("createdAt", "desc"), fsLimit(100));
    const unsub = onSnapshot(
      q,
      (snap) => {
        setRows(snap.docs.map(snapshotToRow));
        setLoading(false);
      },
      (err) => {
        setError(err.message);
        setLoading(false);
      },
    );
    return unsub;
  }, []);

  const columns = useMemo<ColumnDef<ShipmentRow>[]>(
    () => [
      {
        header: "ID",
        accessorKey: "id",
        cell: (c) => (
          <Link href={`/shipments/${c.row.original.id}`} className="font-mono text-xs text-primary hover:underline">
            {c.row.original.id.slice(0, 8)}…
          </Link>
        ),
      },
      {
        header: "Status",
        accessorKey: "status",
        cell: (c) => <StatusBadge status={c.row.original.status} />,
      },
      {
        header: "Priority",
        accessorKey: "priority",
        cell: (c) => <PriorityBadge priority={c.row.original.priority} />,
      },
      {
        header: "Disaster",
        accessorKey: "disasterId",
        cell: (c) => <span className="font-mono text-xs">{c.row.original.disasterId || "—"}</span>,
      },
      {
        header: "Volunteer",
        accessorKey: "assignedVolunteerId",
        cell: (c) =>
          c.row.original.assignedVolunteerId ? (
            <span className="font-mono text-xs">
              {c.row.original.assignedVolunteerId.slice(0, 8)}…
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">unassigned</span>
          ),
      },
      {
        header: "Weight",
        accessorKey: "totalKg",
        cell: (c) => <span className="text-sm">{c.row.original.totalKg.toFixed(1)} kg</span>,
      },
      {
        header: "ETA",
        accessorKey: "etaCurrent",
        cell: (c) =>
          c.row.original.etaCurrent ? (
            <span className="text-sm">{format(c.row.original.etaCurrent, "MMM d, HH:mm")}</span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          ),
      },
      {
        header: "Created",
        accessorKey: "createdAt",
        cell: (c) =>
          c.row.original.createdAt ? (
            <span className="text-xs text-muted-foreground">
              {format(c.row.original.createdAt, "MMM d, HH:mm")}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          ),
      },
    ],
    [],
  );

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
        Live listener failed: {error}
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="text-sm">
          <span className="font-medium">{rows.length}</span> shipment{rows.length === 1 ? "" : "s"}
          {loading && <span className="ml-2 text-muted-foreground">loading…</span>}
        </div>
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
          ● live
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} className="px-4 py-3 font-medium">
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y">
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No shipments yet. Create one via{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">POST /api/shipments</code>.
                </td>
              </tr>
            )}
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-muted/40">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
