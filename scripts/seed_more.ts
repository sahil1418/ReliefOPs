/**
 * Additive seed for the demo — adds 4 more disasters across South Asia plus
 * 35+ shipments in various states (12 delivered today so KPIs aren't zero),
 * tracking events for live map, and alerts. Run AFTER `seed.ts`.
 *
 *   pnpm tsx scripts/seed_more.ts                 # emulator
 *   pnpm tsx scripts/seed_more.ts --prod --sa ./serviceAccount.json
 */
import { cert, getApps, initializeApp } from "firebase-admin/app";
import { FieldValue, getFirestore, GeoPoint, Timestamp } from "firebase-admin/firestore";
import { getDatabase } from "firebase-admin/database";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─── Target selection ────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const IS_PROD = argv.includes("--prod") || process.env.SEED_TARGET === "production";
const saArgIdx = argv.indexOf("--sa");
const SA_PATH = saArgIdx >= 0 ? argv[saArgIdx + 1] : process.env.GOOGLE_APPLICATION_CREDENTIALS;

if (IS_PROD) {
  if (!SA_PATH) {
    console.error("✗ --prod requires --sa <serviceAccount.json>.");
    process.exit(1);
  }
  for (const k of [
    "FIRESTORE_EMULATOR_HOST",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "FIREBASE_DATABASE_EMULATOR_HOST",
    "FIREBASE_STORAGE_EMULATOR_HOST",
  ]) {
    delete process.env[k];
  }
} else {
  process.env.FIRESTORE_EMULATOR_HOST ??= "127.0.0.1:8080";
  process.env.FIREBASE_AUTH_EMULATOR_HOST ??= "127.0.0.1:9099";
  process.env.FIREBASE_DATABASE_EMULATOR_HOST ??= "127.0.0.1:9000";
}

const PROJECT_ID = IS_PROD
  ? (() => {
      const sa = JSON.parse(readFileSync(resolve(SA_PATH!), "utf8"));
      return sa.project_id as string;
    })()
  : (process.env.GCLOUD_PROJECT ?? "relief-logistics");

process.env.GCLOUD_PROJECT = PROJECT_ID;

if (!getApps().length) {
  if (IS_PROD) {
    const sa = JSON.parse(readFileSync(resolve(SA_PATH!), "utf8"));
    initializeApp({
      projectId: PROJECT_ID,
      credential: cert(sa),
      databaseURL: `https://${PROJECT_ID}-default-rtdb.firebaseio.com`,
    });
  } else {
    initializeApp({ projectId: PROJECT_ID });
  }
}

const db = getFirestore();
const rtdb = getDatabase();
db.settings({ ignoreUndefinedProperties: true });

// ─── Disaster fixtures ───────────────────────────────────────────────────────
type DisasterType = "flood" | "earthquake" | "cyclone" | "heatwave" | "drought" | "other";

function ringFromBbox(b: { west: number; south: number; east: number; north: number }) {
  return [
    { lng: b.west, lat: b.south },
    { lng: b.east, lat: b.south },
    { lng: b.east, lat: b.north },
    { lng: b.west, lat: b.north },
    { lng: b.west, lat: b.south },
  ];
}

const DISASTERS: Array<{
  id: string;
  name: string;
  type: DisasterType;
  severityScale: 1 | 2 | 3 | 4 | 5;
  affectedPopulationEstimate: number;
  status: "active" | "contained" | "closed";
  centerLat: number;
  centerLng: number;
  bbox: { west: number; south: number; east: number; north: number };
}> = [
  {
    id: "dis-flood-kerala-2026",
    name: "Kerala Flood — Wayanad District",
    type: "flood",
    severityScale: 5,
    affectedPopulationEstimate: 420_000,
    status: "active",
    centerLat: 11.605,
    centerLng: 76.083,
    bbox: { west: 75.85, south: 11.45, east: 76.30, north: 11.78 },
  },
  {
    id: "dis-heatwave-delhi-2026",
    name: "Delhi NCR Heatwave",
    type: "heatwave",
    severityScale: 4,
    affectedPopulationEstimate: 2_100_000,
    status: "active",
    centerLat: 28.61,
    centerLng: 77.21,
    bbox: { west: 76.95, south: 28.40, east: 77.45, north: 28.80 },
  },
  {
    id: "dis-earthquake-sikkim-2026",
    name: "Sikkim Earthquake — Gangtok",
    type: "earthquake",
    severityScale: 5,
    affectedPopulationEstimate: 180_000,
    status: "active",
    centerLat: 27.33,
    centerLng: 88.61,
    bbox: { west: 88.45, south: 27.20, east: 88.80, north: 27.50 },
  },
  {
    id: "dis-cyclone-sundarbans-2026",
    name: "Cyclone Bulbul — Sundarbans",
    type: "cyclone",
    severityScale: 3,
    affectedPopulationEstimate: 95_000,
    status: "contained",
    centerLat: 21.95,
    centerLng: 88.80,
    bbox: { west: 88.55, south: 21.75, east: 89.10, north: 22.15 },
  },
];

// Demand-request templates — random raw text strings per category.
const REQUEST_TEMPLATES: Record<string, string[]> = {
  flood: [
    "100kg rice + 50 ORS packets urgently — village stranded for 2 days",
    "Water purification tablets needed for 300 displaced families",
    "Family tents + blankets — 40 children at relief camp",
    "Insulin running out — 18 diabetic patients at clinic, cold-chain critical",
    "Bandages and paracetamol for 12 injured at Wayanad camp",
    "Need bottled water and biscuits for elderly group on rooftop",
  ],
  heatwave: [
    "ORS sachets + bottled water for outdoor workers — 500 needed",
    "Cooling shelter supplies — fans + tarpaulins at slum cluster",
    "Heatstroke first-aid kits for 80 elderly at retirement home",
    "Bulk drinking water 20L containers — 30 units for community kitchen",
    "Salt + electrolyte packs for construction site (200 workers)",
  ],
  earthquake: [
    "Tents for 80 displaced families — entire village without shelter",
    "Search & rescue gear — ropes, life jackets, torches at landslide site",
    "First-aid kits + bandages for 25 injured at hospital triage",
    "Drinking water + food kits for school converted to evacuation center",
    "Cold-chain insulin for 8 diabetic patients (clinic destroyed)",
    "Blankets and warm clothing — temperature dropping at altitude",
  ],
  cyclone: [
    "Family tents + tarpaulins at coastal village",
    "ORS + paracetamol — diarrhea outbreak post-flood",
    "Life jackets + rope for fishermen rescue operation",
    "Food kits for 150 people at storm shelter",
    "Water purification + filters — wells contaminated by saltwater",
  ],
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
function randomLocationNear(lat: number, lng: number, jitter = 0.08): GeoPoint {
  const j = jitter / 2;
  return new GeoPoint(
    Number((lat + (Math.random() - 0.5) * j).toFixed(5)),
    Number((lng + (Math.random() - 0.5) * j).toFixed(5)),
  );
}

function randItems(disasterType: DisasterType): Array<{ sku: string; qty: number; unit: string }> {
  const categoryMap: Record<DisasterType, Array<[string, string]>> = {
    flood: [["RICE-25KG", "pcs"], ["ORS-PKT", "packets"], ["WATER-20L", "L"], ["TARP-12X12", "pcs"]],
    heatwave: [["ORS-PKT", "packets"], ["WATER-20L", "L"], ["WATER-PURIF", "packets"]],
    earthquake: [["TENT-FAMILY", "pcs"], ["BLANKET", "pcs"], ["FIRSTAID-KIT", "pcs"], ["TORCH-LED", "pcs"]],
    cyclone: [["TARP-12X12", "pcs"], ["RICE-25KG", "pcs"], ["ORS-PKT", "packets"], ["LIFEJACKET", "pcs"]],
    drought: [["WATER-20L", "L"], ["WATER-PURIF", "packets"]],
    other: [["BLANKET", "pcs"], ["FIRSTAID-KIT", "pcs"]],
  };
  const pool = categoryMap[disasterType];
  const n = 1 + Math.floor(Math.random() * 2);
  return pool.slice(0, n).map(([sku, unit]) => ({
    sku,
    qty: 10 + Math.floor(Math.random() * 80),
    unit,
  }));
}

function pickStatus(): "created" | "assigned" | "in_transit" | "delivered" | "failed" {
  const r = Math.random();
  if (r < 0.30) return "delivered";   // 30% delivered
  if (r < 0.55) return "in_transit";  // 25% in transit
  if (r < 0.75) return "assigned";    // 20% assigned
  if (r < 0.95) return "created";     // 20% created
  return "failed";                     // 5% failed
}

function todayUtcTimestamp(hourOffset = 0): Timestamp {
  const d = new Date();
  d.setUTCHours(8 + hourOffset, 0, 0, 0);
  return Timestamp.fromDate(d);
}

// ─── Main seeding work ───────────────────────────────────────────────────────
async function seedDisasters(): Promise<void> {
  console.log("→ Seeding 4 additional disasters across South Asia");
  const batch = db.batch();
  for (const d of DISASTERS) {
    const ring = ringFromBbox(d.bbox);
    batch.set(db.collection("disasters").doc(d.id), {
      name: d.name,
      type: d.type,
      severityScale: d.severityScale,
      affectedPopulationEstimate: d.affectedPopulationEstimate,
      status: d.status,
      orgId: "org-relief-bd",
      sdgTags: ["SDG2", "SDG3", "SDG11", "SDG13"],
      declaredAt: FieldValue.serverTimestamp(),
      declaredBy: "seed-more",
      centerLocation: new GeoPoint(d.centerLat, d.centerLng),
      geo: { type: "Polygon", rings: [{ points: ring }] },
      bbox: d.bbox,
      geoJson: JSON.stringify({
        type: "Polygon",
        coordinates: [ring.map((p) => [p.lng, p.lat])],
      }),
    });
  }
  await batch.commit();
}

async function seedManyDemandRequests(): Promise<void> {
  console.log("→ Seeding ~50 demand requests across all disasters");
  const batch = db.batch();
  let id = 100;
  for (const d of DISASTERS) {
    const templates = REQUEST_TEMPLATES[d.type] ?? REQUEST_TEMPLATES.flood;
    for (let i = 0; i < templates.length + 2; i++) {
      const raw = templates[i % templates.length];
      const urgency = (1 + Math.floor(Math.random() * 5)) as 1 | 2 | 3 | 4 | 5;
      const severity =
        urgency >= 5 ? "critical" :
        urgency >= 4 ? "high" :
        urgency >= 3 ? "medium" : "low";
      batch.set(db.collection("demand_requests").doc(`req-extra-${id++}`), {
        disasterId: d.id,
        source: ["sms", "app", "web"][i % 3],
        items: randItems(d.type),
        location: randomLocationNear(d.centerLat, d.centerLng),
        urgency,
        severity,
        category: ["food", "medicine", "water", "shelter", "rescue"][i % 5],
        raw,
        photos: [],
        createdAt: FieldValue.serverTimestamp(),
        status: "pending",
        classifiedBy: "gemini",
        confidence: 0.88 + Math.random() * 0.1,
        orgId: "org-relief-bd",
      });
    }
  }
  await batch.commit();
}

async function seedManyShipments(): Promise<{ id: string; status: string; volunteerId: string | null; lat: number; lng: number; disasterId: string }[]> {
  console.log("→ Seeding ~40 shipments distributed across all disasters + statuses");
  const created: Array<{ id: string; status: string; volunteerId: string | null; lat: number; lng: number; disasterId: string }> = [];
  const batch = db.batch();
  // Volunteer IDs from base seed (phantom-vol-2..4 + the real volunteer user)
  const volunteerPool = ["phantom-vol-2", "phantom-vol-3", "phantom-vol-4"];
  const vehiclePool = ["veh-van-01", "veh-truck-01", "veh-cool-01", "veh-bike-01"];

  let count = 0;
  for (const d of DISASTERS) {
    const shipmentsForThis = 8 + Math.floor(Math.random() * 4);
    for (let i = 0; i < shipmentsForThis; i++) {
      const status = pickStatus();
      const id = `ship-extra-${d.id.slice(-12)}-${i}`;
      const items = randItems(d.type);
      const totalKg = items.reduce((s, it) => s + it.qty * (1 + Math.random() * 5), 0);
      const dropLat = d.centerLat + (Math.random() - 0.5) * 0.1;
      const dropLng = d.centerLng + (Math.random() - 0.5) * 0.1;
      const assignedVol = ["delivered", "in_transit", "assigned"].includes(status)
        ? volunteerPool[i % volunteerPool.length]
        : null;
      const vehicle = assignedVol ? vehiclePool[i % vehiclePool.length] : null;

      const doc: Record<string, unknown> = {
        disasterId: d.id,
        requestIds: [],
        items: items.map((it) => ({ ...it, warehouseId: i % 2 === 0 ? "wh-coxs-bazar" : "wh-chittagong", unitWeight_kg: 2.5 })),
        totalKg: Math.round(totalKg * 10) / 10,
        originWarehouseId: i % 2 === 0 ? "wh-coxs-bazar" : "wh-chittagong",
        dropoffLocation: new GeoPoint(dropLat, dropLng),
        dropoffAddress: `${d.name.split(" — ")[0]} relief area #${i + 1}`,
        priority: ["critical", "high", "normal"][i % 3],
        status,
        assignedVolunteerId: assignedVol,
        vehicleId: vehicle,
        etaInitial: status !== "created" ? FieldValue.serverTimestamp() : null,
        etaCurrent: status !== "created" ? FieldValue.serverTimestamp() : null,
        createdAt: FieldValue.serverTimestamp(),
        deliveredAt: status === "delivered" ? todayUtcTimestamp(-Math.floor(Math.random() * 6)) : null,
        orgId: "org-relief-bd",
        requiredSkills: ["driving"],
      };
      batch.set(db.collection("shipments").doc(id), doc);
      created.push({ id, status, volunteerId: assignedVol, lat: dropLat, lng: dropLng, disasterId: d.id });
      count++;
    }
  }
  await batch.commit();
  console.log(`  ${count} shipments seeded`);
  return created;
}

async function seedTrackingEvents(
  shipments: Array<{ id: string; volunteerId: string | null; lat: number; lng: number; status: string; disasterId: string }>,
) {
  console.log("→ Seeding tracking_events for in_transit shipments + RTDB live pins");
  const inTransit = shipments.filter((s) => s.status === "in_transit" && s.volunteerId);
  const batch = db.batch();
  let n = 0;
  for (const s of inTransit) {
    // 3-5 historical tracking points along the route to the dropoff
    const ptCount = 3 + Math.floor(Math.random() * 3);
    for (let i = 0; i < ptCount; i++) {
      const t = (i + 1) / (ptCount + 1);
      const lat = s.lat - 0.04 + t * 0.04;
      const lng = s.lng - 0.04 + t * 0.04;
      batch.set(db.collection("tracking_events").doc(), {
        shipmentId: s.id,
        volunteerId: s.volunteerId!,
        location: new GeoPoint(lat, lng),
        ts: Timestamp.fromMillis(Date.now() - (ptCount - i) * 60_000),
        speedKmh: 25 + Math.random() * 15,
        accuracy: 5,
      });
      n++;
    }
    // Push the most-recent location into RTDB so the live fleet map shows the pin.
    try {
      await rtdb.ref(`locations/${s.volunteerId}`).set({
        lat: s.lat,
        lng: s.lng,
        ts: new Date().toISOString(),
        speedKmh: 30,
        accuracy: 5,
        heading: 90,
        shipmentId: s.id,
        volunteerId: s.volunteerId,
      });
    } catch (e) {
      console.warn(`  RTDB write skipped for ${s.volunteerId}: ${(e as Error).message}`);
    }
  }
  await batch.commit();
  console.log(`  ${n} tracking_events written, ${inTransit.length} live RTDB pins`);
}

async function seedAlerts(): Promise<void> {
  console.log("→ Seeding 8 alerts (mix of disruption, weather, expiry)");
  const batch = db.batch();
  const alertSpecs: Array<{
    type: string;
    subtype: string;
    severity: number;
    headline: string;
    disasterId: string;
    lat: number;
    lng: number;
    rerouteRecommended: boolean;
  }> = [
    { type: "flood", subtype: "damage_assessment", severity: 5, headline: "NH-66 fully submerged near Wayanad — vehicles cannot pass", disasterId: "dis-flood-kerala-2026", lat: 11.62, lng: 76.10, rerouteRecommended: true },
    { type: "weather", subtype: "openweather", severity: 4, headline: "Heavy rain expected in next 6h across Kerala", disasterId: "dis-flood-kerala-2026", lat: 11.61, lng: 76.08, rerouteRecommended: false },
    { type: "other", subtype: "inventory_expiry", severity: 3, headline: "12 inventory items at Cox's Bazar expire within 7 days", disasterId: "dis-cyclone-remal-2026", lat: 21.43, lng: 92.00, rerouteRecommended: false },
    { type: "fire", subtype: "damage_assessment", severity: 4, headline: "Power line down on relief road near Gangtok", disasterId: "dis-earthquake-sikkim-2026", lat: 27.34, lng: 88.62, rerouteRecommended: true },
    { type: "other", subtype: "curfew", severity: 3, headline: "Night-curfew imposed in Delhi heatwave zone (8pm-6am)", disasterId: "dis-heatwave-delhi-2026", lat: 28.61, lng: 77.21, rerouteRecommended: false },
    { type: "collapsed_road", subtype: "damage_assessment", severity: 5, headline: "Bridge collapsed on coastal road near Sundarbans", disasterId: "dis-cyclone-sundarbans-2026", lat: 21.95, lng: 88.80, rerouteRecommended: true },
    { type: "weather", subtype: "openweather", severity: 2, headline: "Wind speeds dropping in Sundarbans — operations resuming", disasterId: "dis-cyclone-sundarbans-2026", lat: 21.92, lng: 88.78, rerouteRecommended: false },
    { type: "other", subtype: "stock_low", severity: 3, headline: "Insulin stock at Chittagong below 30% — restock recommended", disasterId: "dis-cyclone-remal-2026", lat: 22.36, lng: 91.78, rerouteRecommended: false },
  ];
  for (const a of alertSpecs) {
    batch.set(db.collection("alerts").doc(), {
      type: a.type,
      subtype: a.subtype,
      severity: a.severity,
      headline: a.headline,
      source: a.subtype === "openweather" ? "openweather" : a.subtype === "damage_assessment" ? "damage_assessment" : "ops",
      classifiedBy: a.subtype === "damage_assessment" ? "gemini" : "human",
      disasterId: a.disasterId,
      location: new GeoPoint(a.lat, a.lng),
      detectedAt: FieldValue.serverTimestamp(),
      resolved: false,
      rerouteRecommended: a.rerouteRecommended,
      confidenceScore: 0.85 + Math.random() * 0.1,
      orgId: "org-relief-bd",
    });
  }
  await batch.commit();
}

async function main(): Promise<void> {
  console.log(`Seed-more: ${IS_PROD ? "PRODUCTION" : "EMULATOR"} target — project=${PROJECT_ID}\n`);

  await seedDisasters();
  await seedManyDemandRequests();
  const ships = await seedManyShipments();
  await seedTrackingEvents(ships);
  await seedAlerts();

  console.log("\n✔ Additional seed complete.");
  console.log(`  - 4 new disasters (Kerala flood, Delhi heatwave, Sikkim earthquake, Sundarbans cyclone)`);
  console.log(`  - ~50 new demand requests`);
  console.log(`  - ~40 shipments across statuses (~12 delivered today for KPIs)`);
  console.log(`  - ~30 tracking_events for live map`);
  console.log(`  - 8 alerts in 'alerts' collection`);
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
