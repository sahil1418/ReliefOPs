"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiCallError } from "@/lib/api";

const formSchema = z.object({
  name: z.string().min(3, "Name must be at least 3 characters"),
  type: z.enum(["flood", "earthquake", "cyclone", "heatwave", "drought", "other"]),
  severityScale: z.number().int().min(1).max(5),
  affectedPopulationEstimate: z.number().int().min(0),
  bbox: z.object({
    west: z.number().min(-180).max(180),
    south: z.number().min(-90).max(90),
    east: z.number().min(-180).max(180),
    north: z.number().min(-90).max(90),
  }),
});

type FormValues = z.infer<typeof formSchema>;

export default function NewDisasterPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<FormValues>({
    name: "",
    type: "flood",
    severityScale: 4,
    affectedPopulationEstimate: 0,
    // Default to a Cox's Bazar-shaped bbox so the demo is one click.
    bbox: { west: 91.95, south: 21.35, east: 92.10, north: 21.55 },
  });

  function update<K extends keyof FormValues>(k: K, v: FormValues[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  function updateBbox(k: keyof FormValues["bbox"], v: number) {
    setForm((f) => ({ ...f, bbox: { ...f.bbox, [k]: v } }));
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const parsed = formSchema.safeParse(form);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input");
      return;
    }
    if (form.bbox.east <= form.bbox.west || form.bbox.north <= form.bbox.south) {
      setError("Bbox is invalid: east must be > west, north must be > south.");
      return;
    }

    setSubmitting(true);
    try {
      const ring = [
        { lat: form.bbox.south, lng: form.bbox.west },
        { lat: form.bbox.south, lng: form.bbox.east },
        { lat: form.bbox.north, lng: form.bbox.east },
        { lat: form.bbox.north, lng: form.bbox.west },
        { lat: form.bbox.south, lng: form.bbox.west },
      ];
      const created = await api.post<{ id: string }>("/api/disasters", {
        name: form.name,
        type: form.type,
        bbox: form.bbox,
        geo: { type: "Polygon", rings: [{ points: ring }] },
        severityScale: form.severityScale,
        affectedPopulationEstimate: form.affectedPopulationEstimate,
        sdgTags: ["SDG2", "SDG3", "SDG11", "SDG13"],
      });
      router.replace(`/disasters/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiCallError ? err.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <AdminTopbar title="Declare disaster" />
      <main className="flex-1 p-6">
        <Card className="mx-auto max-w-2xl">
          <CardHeader>
            <CardTitle>Declare a new disaster zone</CardTitle>
            <CardDescription>
              The bbox defines the affected area as a rectangle. Polygon-draw on a Google Map will
              be added once Maps APIs are enabled on the project (see README).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  placeholder="Cyclone Remal — Cox's Bazar"
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                  disabled={submitting}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="type">Type</Label>
                  <select
                    id="type"
                    value={form.type}
                    onChange={(e) => update("type", e.target.value as FormValues["type"])}
                    disabled={submitting}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {["flood", "earthquake", "cyclone", "heatwave", "drought", "other"].map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="severity">Severity (1-5)</Label>
                  <Input
                    id="severity"
                    type="number"
                    min={1}
                    max={5}
                    value={form.severityScale}
                    onChange={(e) => update("severityScale", Number(e.target.value))}
                    disabled={submitting}
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="population">Estimated affected population</Label>
                <Input
                  id="population"
                  type="number"
                  min={0}
                  value={form.affectedPopulationEstimate}
                  onChange={(e) => update("affectedPopulationEstimate", Number(e.target.value))}
                  disabled={submitting}
                />
              </div>

              <fieldset className="space-y-2 rounded-md border p-4">
                <legend className="px-1 text-sm font-medium">Affected area (bbox)</legend>
                <div className="grid grid-cols-2 gap-4">
                  {(["west", "south", "east", "north"] as const).map((k) => (
                    <div key={k} className="space-y-1">
                      <Label htmlFor={k} className="text-xs uppercase tracking-wider text-muted-foreground">
                        {k}
                      </Label>
                      <Input
                        id={k}
                        type="number"
                        step="0.0001"
                        value={form.bbox[k]}
                        onChange={(e) => updateBbox(k, Number(e.target.value))}
                        disabled={submitting}
                        required
                      />
                    </div>
                  ))}
                </div>
              </fieldset>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="flex gap-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Declaring…" : "Declare disaster"}
                </Button>
                <Button type="button" variant="outline" onClick={() => router.back()} disabled={submitting}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
