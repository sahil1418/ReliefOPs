"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { format } from "date-fns";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { DisasterStatusBadge } from "@/components/disasters/SeverityBadge";
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
};

export default function DisastersPage() {
  const [rows, setRows] = useState<Disaster[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<Disaster[]>("/api/disasters");
        if (!cancelled) setRows(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load");
      }
    }
    void load();
    const id = window.setInterval(load, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <>
      <AdminTopbar title="Disasters" />
      <main className="flex-1 space-y-6 p-6">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Active disasters declared by your organization. Polls the API every 15s.
          </p>
          <Button asChild>
            <Link href="/disasters/new">
              <Plus className="mr-2 h-4 w-4" />
              Declare disaster
            </Link>
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!rows && !error && <p className="text-sm text-muted-foreground">Loading…</p>}

        {rows && rows.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">No disasters yet</CardTitle>
              <CardDescription>
                Click <em>Declare disaster</em> to declare one. Demand requests can then be filed against it,
                and Gemini will auto-classify their severity.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {rows && rows.length > 0 && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {rows.map((d) => (
              <Link key={d.id} href={`/disasters/${d.id}`}>
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <span className="text-xs uppercase tracking-wider text-muted-foreground">
                        {d.type}
                      </span>
                      <DisasterStatusBadge status={d.status} />
                    </div>
                    <CardTitle className="mt-2 text-base">{d.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Severity</span>
                      <span className="font-medium">{d.severityScale} / 5</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Population affected</span>
                      <span className="font-medium">{d.affectedPopulationEstimate.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Declared</span>
                      <span className="text-xs">
                        {d.declaredAt ? format(new Date(d.declaredAt), "MMM d, HH:mm") : "—"}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1 pt-1">
                      {d.sdgTags.map((tag) => (
                        <span key={tag} className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
