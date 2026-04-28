"use client";

import { useRef, useState } from "react";
import { Camera, AlertTriangle, CheckCircle2 } from "lucide-react";

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
import { firebaseStorage } from "@/lib/firebase";
import { ref as storageRef, uploadBytes, getDownloadURL } from "firebase/storage";

type DamageResult = {
  blocked: boolean;
  blockageType: string;
  severity: number;
  description: string;
  rerouteRecommended: boolean;
  confidenceScore: number;
  alertId: string | null;
};

export function PhotoAssess() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DamageResult | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [lat, setLat] = useState("21.4530");
  const [lng, setLng] = useState("92.0187");
  const [disasterId, setDisasterId] = useState("dis-cyclone-remal-2026");

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setResult(null);

    const file = fileInput.current?.files?.[0];
    if (!file) {
      setError("Choose a photo first.");
      return;
    }
    setBusy(true);
    setProgress("Uploading photo…");

    try {
      const path = `damage/${disasterId}/${Date.now()}-${file.name}`;
      const sref = storageRef(firebaseStorage(), path);
      await uploadBytes(sref, file);
      const photoURL = await getDownloadURL(sref);

      setProgress("Asking Gemini for assessment…");
      const data = await api.post<DamageResult>("/api/predict/damage-assess", {
        photoURL,
        location: { lat: Number(lat), lng: Number(lng) },
        disasterId,
      });
      setResult(data);
      setPreview(URL.createObjectURL(file));
      setProgress(null);
    } catch (err) {
      setError(err instanceof ApiCallError ? `${err.code}: ${err.message}` : String(err));
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Camera className="h-4 w-4" />
          Damage assessment
        </CardTitle>
        <CardDescription>
          Upload a photo from a volunteer in the field. Gemini multimodal returns
          blockage type, severity (1–5), and a reroute recommendation. If a
          reroute is recommended, an <code>alerts</code> doc is written and{" "}
          <code>disruption.detected</code> fires on Pub/Sub.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label htmlFor="photo">Photo</Label>
            <Input id="photo" type="file" accept="image/*" ref={fileInput} disabled={busy} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label htmlFor="lat" className="text-xs">Lat</Label>
              <Input id="lat" type="number" step="0.0001" value={lat} onChange={(e) => setLat(e.target.value)} disabled={busy} />
            </div>
            <div>
              <Label htmlFor="lng" className="text-xs">Lng</Label>
              <Input id="lng" type="number" step="0.0001" value={lng} onChange={(e) => setLng(e.target.value)} disabled={busy} />
            </div>
            <div>
              <Label htmlFor="dis" className="text-xs">Disaster id</Label>
              <Input id="dis" value={disasterId} onChange={(e) => setDisasterId(e.target.value)} disabled={busy} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Working…" : "Assess damage"}
            </Button>
            {progress && <span className="text-xs text-muted-foreground">{progress}</span>}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>

        {result && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {preview && (
              <img src={preview} alt="Uploaded" className="max-h-64 w-full rounded-md object-cover" />
            )}
            <div className="rounded-md border bg-card p-4">
              <div className="mb-2 flex items-center gap-2">
                {result.blocked ? (
                  <AlertTriangle className="h-5 w-5 text-amber-500" />
                ) : (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                )}
                <span className="text-sm font-semibold capitalize">
                  {result.blockageType.replace("_", " ")}
                </span>
                <span className={`ml-auto rounded-full px-2 py-0.5 text-xs ${
                  result.severity >= 4
                    ? "bg-red-100 text-red-700"
                    : result.severity >= 3
                    ? "bg-amber-100 text-amber-700"
                    : "bg-emerald-100 text-emerald-700"
                }`}>
                  severity {result.severity}/5
                </span>
              </div>
              <p className="text-sm">{result.description}</p>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Reroute</dt>
                  <dd className="font-medium">
                    {result.rerouteRecommended ? "yes — alert fired" : "not needed"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Confidence</dt>
                  <dd className="font-medium">{(result.confidenceScore * 100).toFixed(0)}%</dd>
                </div>
                {result.alertId && (
                  <div className="col-span-2">
                    <dt className="text-muted-foreground">Alert id</dt>
                    <dd className="font-mono text-xs">{result.alertId}</dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
