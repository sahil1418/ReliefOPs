/**
 * Volunteer GPS simulator — drives Realtime DB writes along a route at
 * 1 ping per `--interval-ms` so the live admin map demo runs without an
 * actual Android device.
 *
 * Usage (with emulators running):
 *   pnpm tsx scripts/simulate_volunteer.ts \
 *     --shipment <SHIPMENT_ID> \
 *     [--volunteer <UID>] \
 *     [--interval-ms 2000] \
 *     [--speed-kmh 35] \
 *     [--also-api]              # also POST /api/tracking/event so Firestore aggregates
 *
 * Defaults:
 *   - Cox's Bazar warehouse (21.4272, 92.0058) → Inani Beach (21.453, 92.018)
 *   - 2-second tick (faster than real life so the demo is snappy)
 *   - Emits to RTDB only by default; --also-api hits FastAPI for Firestore writes
 */
import { getApps, initializeApp } from "firebase-admin/app";
import { getDatabase } from "firebase-admin/database";

// ─── Emulator wiring ─────────────────────────────────────────────────────────
const PROJECT_ID = process.env.GCLOUD_PROJECT ?? "relief-logistics";
process.env.FIRESTORE_EMULATOR_HOST ??= "127.0.0.1:8080";
process.env.FIREBASE_AUTH_EMULATOR_HOST ??= "127.0.0.1:9099";
process.env.FIREBASE_DATABASE_EMULATOR_HOST ??= "127.0.0.1:9000";
process.env.GCLOUD_PROJECT = PROJECT_ID;

if (!getApps().length) {
  initializeApp({
    projectId: PROJECT_ID,
    databaseURL: `http://${process.env.FIREBASE_DATABASE_EMULATOR_HOST}/?ns=${PROJECT_ID}-default-rtdb`,
  });
}

// ─── CLI ─────────────────────────────────────────────────────────────────────
type Args = {
  shipmentId: string | null;
  volunteerId: string;
  intervalMs: number;
  speedKmh: number;
  apiUrl: string;
  alsoApi: boolean;
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  apiToken: string | null;
};

function parseArgs(): Args {
  const argv = process.argv.slice(2);
  const get = (name: string, fallback?: string): string | undefined => {
    const i = argv.indexOf(`--${name}`);
    return i >= 0 ? argv[i + 1] : fallback;
  };
  const flag = (name: string): boolean => argv.includes(`--${name}`);
  return {
    shipmentId: get("shipment") ?? null,
    volunteerId: get("volunteer") ?? "phantom-vol-3",
    intervalMs: Number(get("interval-ms", "2000")),
    speedKmh: Number(get("speed-kmh", "35")),
    apiUrl: get("api-url", "http://127.0.0.1:8000")!,
    alsoApi: flag("also-api"),
    startLat: Number(get("start-lat", "21.4272")),
    startLng: Number(get("start-lng", "92.0058")),
    endLat: Number(get("end-lat", "21.4530")),
    endLng: Number(get("end-lng", "92.0187")),
    apiToken: process.env.API_TOKEN ?? null,
  };
}

// ─── Math helpers ────────────────────────────────────────────────────────────
const R_KM = 6371;
function haversineKm(a: [number, number], b: [number, number]): number {
  const [la1, lo1] = a.map((x) => (x * Math.PI) / 180);
  const [la2, lo2] = b.map((x) => (x * Math.PI) / 180);
  const dLa = la2 - la1;
  const dLo = lo2 - lo1;
  const h =
    Math.sin(dLa / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(h));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

// ─── Main ────────────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const args = parseArgs();
  const start: [number, number] = [args.startLat, args.startLng];
  const end: [number, number] = [args.endLat, args.endLng];
  const totalKm = haversineKm(start, end);
  const totalMin = (totalKm / args.speedKmh) * 60;
  const totalTicks = Math.max(2, Math.ceil((totalMin * 60_000) / args.intervalMs));

  console.log("Volunteer GPS simulator");
  console.log(`  RTDB:      ${process.env.FIREBASE_DATABASE_EMULATOR_HOST}`);
  console.log(`  shipment:  ${args.shipmentId ?? "(none)"}`);
  console.log(`  volunteer: ${args.volunteerId}`);
  console.log(`  start:     ${start[0]}, ${start[1]}`);
  console.log(`  end:       ${end[0]}, ${end[1]}`);
  console.log(`  distance:  ${totalKm.toFixed(2)} km (~${totalMin.toFixed(1)} min @ ${args.speedKmh} km/h)`);
  console.log(`  ticks:     ${totalTicks} every ${args.intervalMs}ms`);
  console.log(`  also-api:  ${args.alsoApi}`);
  console.log("");

  const rtdb = getDatabase();
  const ref = rtdb.ref(`locations/${args.volunteerId}`);
  const shutdown = async () => {
    console.log("\nClearing /locations/" + args.volunteerId);
    await ref.remove().catch(() => undefined);
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  for (let i = 0; i <= totalTicks; i++) {
    const t = i / totalTicks;
    // Mild ease-out curve so the volunteer "decelerates" as they arrive.
    const tt = 1 - (1 - t) ** 1.4;
    const lat = lerp(start[0], end[0], tt);
    const lng = lerp(start[1], end[1], tt);
    const ts = new Date().toISOString();

    const payload = {
      lat,
      lng,
      ts,
      speedKmh: args.speedKmh * (1 - 0.4 * tt),
      accuracy: 5,
      heading: 90,
      shipmentId: args.shipmentId,
      volunteerId: args.volunteerId,
    };
    await ref.set(payload);

    if (args.alsoApi && args.apiToken) {
      try {
        const res = await fetch(`${args.apiUrl}/api/tracking/event`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${args.apiToken}`,
          },
          body: JSON.stringify({
            shipmentId: args.shipmentId,
            location: { lat, lng },
            speedKmh: payload.speedKmh,
            accuracy: 5,
            heading: 90,
          }),
        });
        if (!res.ok) {
          console.warn(`  api ${res.status} ${await res.text().catch(() => "")}`);
        }
      } catch (err) {
        console.warn("  api fetch error", err);
      }
    }

    process.stdout.write(
      `  tick ${String(i).padStart(3)}/${totalTicks}: ${lat.toFixed(5)}, ${lng.toFixed(5)} (${(t * 100).toFixed(1)}%)\r`,
    );
    if (i < totalTicks) await new Promise((r) => setTimeout(r, args.intervalMs));
  }
  console.log("\n✔ Simulation complete. Pin will stay at the destination until you SIGINT.");

  // Keep RTDB pin alive so the demo stays static after arrival.
  await new Promise((r) => setTimeout(r, 60_000));
  await shutdown();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
