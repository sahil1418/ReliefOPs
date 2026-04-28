/**
 * Emulator seeder — populates a fresh Firebase emulator suite with the bare-minimum
 * fixture set described in COMMIT 2 of the build plan:
 *
 *   - 2 organizations
 *   - 5 users (one per role) — created in Firebase Auth + mirrored in Firestore /users
 *   - 2 warehouses
 *   - 20 inventory_items
 *   - 1 active disaster
 *   - 10 demand_requests
 *
 * Run:  pnpm tsx scripts/seed.ts
 *
 * Requires the Firebase emulators to be running (firebase emulators:start).
 * The Admin SDK is configured to talk to them via FIRESTORE_EMULATOR_HOST +
 * FIREBASE_AUTH_EMULATOR_HOST env vars set below — no real credentials needed.
 */
import { cert, getApps, initializeApp } from "firebase-admin/app";
import { FieldValue, getFirestore, GeoPoint, Timestamp } from "firebase-admin/firestore";
import { getAuth, type UserRecord } from "firebase-admin/auth";

// ─── Emulator wiring ─────────────────────────────────────────────────────────
const PROJECT_ID = process.env.GCLOUD_PROJECT ?? "relief-logistics";
process.env.FIRESTORE_EMULATOR_HOST ??= "127.0.0.1:8080";
process.env.FIREBASE_AUTH_EMULATOR_HOST ??= "127.0.0.1:9099";
process.env.FIREBASE_DATABASE_EMULATOR_HOST ??= "127.0.0.1:9000";
process.env.FIREBASE_STORAGE_EMULATOR_HOST ??= "127.0.0.1:9199";
process.env.GCLOUD_PROJECT = PROJECT_ID;

if (!getApps().length) {
  initializeApp({ projectId: PROJECT_ID });
}

const db = getFirestore();
const auth = getAuth();

// Avoid SSL on emulator
db.settings({ ignoreUndefinedProperties: true });

// ─── Fixtures ────────────────────────────────────────────────────────────────
type Role =
  | "super_admin"
  | "ngo_admin"
  | "coordinator"
  | "volunteer"
  | "beneficiary";

const ORGS = [
  {
    id: "org-relief-bd",
    name: "Bangladesh Disaster Relief NGO",
    type: "ngo" as const,
    country: "BD",
  },
  {
    id: "org-civic-volunteers",
    name: "Civic Volunteers Network",
    type: "ngo" as const,
    country: "BD",
  },
];

const USERS: Array<{
  email: string;
  password: string;
  displayName: string;
  role: Role;
  orgId: string;
  phone?: string;
  skills?: string[];
}> = [
  {
    email: "super@reliefops.dev",
    password: "DevPass123!",
    displayName: "Sahil Sharma (Super Admin)",
    role: "super_admin",
    orgId: ORGS[0].id,
  },
  {
    email: "admin@reliefops.dev",
    password: "DevPass123!",
    displayName: "Maya Roy (NGO Admin)",
    role: "ngo_admin",
    orgId: ORGS[0].id,
  },
  {
    email: "coordinator@reliefops.dev",
    password: "DevPass123!",
    displayName: "Imran Hossain (Coordinator)",
    role: "coordinator",
    orgId: ORGS[0].id,
    phone: "+8801712345678",
  },
  {
    email: "volunteer@reliefops.dev",
    password: "DevPass123!",
    displayName: "Rahim Uddin (Volunteer)",
    role: "volunteer",
    orgId: ORGS[0].id,
    phone: "+8801812345678",
    skills: ["driving", "heavy_vehicle"],
  },
  {
    email: "beneficiary@reliefops.dev",
    password: "DevPass123!",
    displayName: "Anika Begum (Beneficiary)",
    role: "beneficiary",
    orgId: ORGS[1].id,
  },
];

const WAREHOUSES = [
  {
    id: "wh-coxs-bazar",
    orgId: ORGS[0].id,
    name: "Cox's Bazar Central Warehouse",
    location: new GeoPoint(21.4272, 92.0058),
    address: "Hotel Motel Zone, Cox's Bazar 4700, Bangladesh",
    capacityKg: 50_000,
    coldChainCapable: true,
    contactPhone: "+8803412345678",
  },
  {
    id: "wh-chittagong",
    orgId: ORGS[0].id,
    name: "Chittagong Logistics Hub",
    location: new GeoPoint(22.3569, 91.7832),
    address: "Agrabad C/A, Chittagong 4100, Bangladesh",
    capacityKg: 80_000,
    coldChainCapable: false,
    contactPhone: "+8803112345678",
  },
];

const INVENTORY_TEMPLATES: Array<{
  sku: string;
  name: string;
  category: "food" | "medicine" | "shelter" | "water" | "rescue";
  unitWeight_kg: number;
  coldChainRequired: boolean;
}> = [
  { sku: "RICE-25KG", name: "Rice 25kg sack", category: "food", unitWeight_kg: 25, coldChainRequired: false },
  { sku: "DAL-1KG", name: "Lentil dal 1kg", category: "food", unitWeight_kg: 1, coldChainRequired: false },
  { sku: "OIL-1L", name: "Cooking oil 1L", category: "food", unitWeight_kg: 0.92, coldChainRequired: false },
  { sku: "BISCUIT-PKT", name: "Energy biscuit packet", category: "food", unitWeight_kg: 0.4, coldChainRequired: false },
  { sku: "ORS-PKT", name: "ORS sachet", category: "medicine", unitWeight_kg: 0.025, coldChainRequired: false },
  { sku: "PARACETAMOL-100", name: "Paracetamol 500mg x100", category: "medicine", unitWeight_kg: 0.05, coldChainRequired: false },
  { sku: "INSULIN-VIAL", name: "Insulin vial 10ml", category: "medicine", unitWeight_kg: 0.03, coldChainRequired: true },
  { sku: "BANDAGE-ROLL", name: "Sterile bandage roll", category: "medicine", unitWeight_kg: 0.1, coldChainRequired: false },
  { sku: "TARP-12X12", name: "Tarpaulin 12x12 ft", category: "shelter", unitWeight_kg: 3, coldChainRequired: false },
  { sku: "BLANKET", name: "Wool blanket", category: "shelter", unitWeight_kg: 1.5, coldChainRequired: false },
  { sku: "TENT-FAMILY", name: "Family tent 4-person", category: "shelter", unitWeight_kg: 8, coldChainRequired: false },
  { sku: "MAT-BAMBOO", name: "Bamboo sleeping mat", category: "shelter", unitWeight_kg: 1.2, coldChainRequired: false },
  { sku: "WATER-20L", name: "Water 20L jerry can", category: "water", unitWeight_kg: 20, coldChainRequired: false },
  { sku: "WATER-PURIF", name: "Water purification tablets x10", category: "water", unitWeight_kg: 0.02, coldChainRequired: false },
  { sku: "FILTER-CERAMIC", name: "Ceramic water filter", category: "water", unitWeight_kg: 1.8, coldChainRequired: false },
  { sku: "TORCH-LED", name: "LED torch + battery", category: "rescue", unitWeight_kg: 0.3, coldChainRequired: false },
  { sku: "WHISTLE", name: "Emergency whistle", category: "rescue", unitWeight_kg: 0.02, coldChainRequired: false },
  { sku: "ROPE-30M", name: "Climbing rope 30m", category: "rescue", unitWeight_kg: 2.5, coldChainRequired: false },
  { sku: "LIFEJACKET", name: "Life jacket adult", category: "rescue", unitWeight_kg: 0.6, coldChainRequired: false },
  { sku: "FIRSTAID-KIT", name: "First aid kit family", category: "medicine", unitWeight_kg: 1.2, coldChainRequired: false },
];

// Firestore can't store nested arrays directly, so the polygon ring is held
// as objects {lng, lat}. The full GeoJSON is also stored as a JSON string in
// `geoJson` for round-tripping.
const DISASTER_POLYGON_RING = [
  { lng: 91.95, lat: 21.35 },
  { lng: 92.10, lat: 21.35 },
  { lng: 92.10, lat: 21.55 },
  { lng: 91.95, lat: 21.55 },
  { lng: 91.95, lat: 21.35 },
];

const DISASTER = {
  id: "dis-cyclone-remal-2026",
  name: "Cyclone Remal — Cox's Bazar",
  type: "cyclone" as const,
  declaredAt: Timestamp.now(),
  declaredBy: "", // filled in after super_admin user is created
  status: "active" as const,
  severityScale: 4,
  affectedPopulationEstimate: 250_000,
  sdgTags: ["SDG2", "SDG3", "SDG11", "SDG13"],
  orgId: ORGS[0].id,
  geo: {
    type: "Polygon" as const,
    rings: [{ points: DISASTER_POLYGON_RING }],
  },
  geoJson: JSON.stringify({
    type: "Polygon",
    coordinates: [DISASTER_POLYGON_RING.map((p) => [p.lng, p.lat])],
  }),
  bbox: { west: 91.95, south: 21.35, east: 92.10, north: 21.55 },
};

function randomLocation(): InstanceType<typeof GeoPoint> {
  // Around Cox's Bazar, jittered.
  const lat = 21.42 + (Math.random() - 0.5) * 0.15;
  const lng = 92.00 + (Math.random() - 0.5) * 0.15;
  return new GeoPoint(Number(lat.toFixed(5)), Number(lng.toFixed(5)));
}

function pickItems(): Array<{ sku: string; qty: number; unit: string }> {
  const n = 1 + Math.floor(Math.random() * 3);
  const shuffled = [...INVENTORY_TEMPLATES].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n).map((t) => ({
    sku: t.sku,
    qty: 5 + Math.floor(Math.random() * 100),
    unit: t.category === "water" ? "L" : "pcs",
  }));
}

const RAW_REQUESTS = [
  "Need 100kg rice and 50 ORS packets urgently in flood zone near Inani beach",
  "10 family tents and 30 blankets required at Ukhia camp — children stranded",
  "Insulin running out for 12 diabetic patients at Teknaf clinic, please urgent cold-chain delivery",
  "Water purification tablets needed for 200 people, contaminated wells everywhere",
  "Bandages, paracetamol, first-aid kits — 5 injured villagers at Pekua",
  "Family of 8 displaced, need shelter materials and 20L water immediately",
  "School converted to shelter — needs 100 mats, 50 blankets, food for 80 people",
  "Elderly couple stuck on roof, life jackets and rope needed for rescue",
  "Diarrhea outbreak in Maheshkhali — ORS and water filters critical",
  "Kitchen items lost — need oil, dal, biscuits for 15 families",
];

// ─── Seeding logic ───────────────────────────────────────────────────────────
async function clearAll(): Promise<void> {
  console.log("→ Clearing existing emulator data");
  const collections = [
    "organizations",
    "users",
    "warehouses",
    "inventory_items",
    "disasters",
    "demand_requests",
    "shipments",
    "tracking_events",
    "alerts",
    "ai_conversations",
    "audit_logs",
    "vehicles",
    "volunteers",
  ];
  for (const col of collections) {
    const snap = await db.collection(col).get();
    if (snap.empty) continue;
    const batch = db.batch();
    snap.docs.forEach((doc) => batch.delete(doc.ref));
    await batch.commit();
  }

  // Auth
  const list = await auth.listUsers(1000);
  if (list.users.length) {
    await auth.deleteUsers(list.users.map((u) => u.uid));
  }
}

async function seedOrgs(): Promise<void> {
  console.log("→ Seeding organizations");
  const batch = db.batch();
  ORGS.forEach((o) => {
    batch.set(db.collection("organizations").doc(o.id), {
      ...o,
      createdAt: FieldValue.serverTimestamp(),
    });
  });
  await batch.commit();
}

async function seedUsers(): Promise<Map<Role, UserRecord>> {
  console.log("→ Seeding users (Auth + Firestore)");
  const created = new Map<Role, UserRecord>();
  for (const u of USERS) {
    const record = await auth.createUser({
      email: u.email,
      password: u.password,
      displayName: u.displayName,
      phoneNumber: u.phone,
      emailVerified: true,
    });
    await auth.setCustomUserClaims(record.uid, { role: u.role, orgId: u.orgId });
    await db.collection("users").doc(record.uid).set({
      email: u.email,
      displayName: u.displayName,
      phone: u.phone ?? null,
      role: u.role,
      orgId: u.orgId,
      skills: u.skills ?? [],
      languages: ["en", "bn"],
      createdAt: FieldValue.serverTimestamp(),
    });
    created.set(u.role, record);
    console.log(`   ${u.role.padEnd(13)} ${u.email}  uid=${record.uid}`);
  }
  return created;
}

async function seedWarehouses(): Promise<void> {
  console.log("→ Seeding warehouses");
  const batch = db.batch();
  WAREHOUSES.forEach((w) => {
    batch.set(db.collection("warehouses").doc(w.id), {
      ...w,
      createdAt: FieldValue.serverTimestamp(),
    });
  });
  await batch.commit();
}

async function seedInventory(): Promise<void> {
  console.log("→ Seeding inventory_items (20 items across 2 warehouses)");
  const batch = db.batch();
  let i = 0;
  for (const wh of WAREHOUSES) {
    // 10 items per warehouse → 20 total
    const items = INVENTORY_TEMPLATES.slice(0, 10).map((t, idx) => ({ ...t, idx }));
    for (const t of items) {
      const id = `inv-${wh.id}-${t.sku}`.toLowerCase();
      const expiryDays = t.category === "food" ? 90 : t.category === "medicine" ? 365 : 1825;
      const expiry = Timestamp.fromMillis(Date.now() + expiryDays * 24 * 60 * 60 * 1000);
      batch.set(db.collection("inventory_items").doc(id), {
        warehouseId: wh.id,
        sku: t.sku,
        name: t.name,
        category: t.category,
        qty: 200 + Math.floor(Math.random() * 800),
        reservedQty: 0,
        lot: `LOT-${(2026).toString()}-${String(i + 1).padStart(3, "0")}`,
        expiry,
        coldChainRequired: t.coldChainRequired,
        unitWeight_kg: t.unitWeight_kg,
        updatedAt: FieldValue.serverTimestamp(),
      });
      i++;
    }
  }
  await batch.commit();
}

// 4 vehicles + 4 volunteers (driver pool) so the auto-match has candidates.
const VEHICLES = [
  { id: "veh-van-01",   orgId: ORGS[0].id, plate: "DHA-V-001", type: "van",   capacityKg: 1500, coldChain: false, fuelType: "diesel" },
  { id: "veh-truck-01", orgId: ORGS[0].id, plate: "DHA-T-001", type: "truck", capacityKg: 5000, coldChain: false, fuelType: "diesel" },
  { id: "veh-bike-01",  orgId: ORGS[0].id, plate: "DHA-B-001", type: "bike",  capacityKg: 60,   coldChain: false, fuelType: "petrol" },
  { id: "veh-cool-01",  orgId: ORGS[0].id, plate: "DHA-C-001", type: "van",   capacityKg: 1200, coldChain: true,  fuelType: "diesel" },
];

async function seedVehicles(): Promise<void> {
  console.log("→ Seeding vehicles");
  const batch = db.batch();
  VEHICLES.forEach((v) => {
    batch.set(db.collection("vehicles").doc(v.id), { ...v, createdAt: FieldValue.serverTimestamp() });
  });
  await batch.commit();
}

async function seedVolunteers(volunteerUid: string): Promise<void> {
  console.log("→ Seeding volunteers (4 active drivers, all 'available')");
  const seedVolunteers: Array<{
    id: string; userId: string; orgId: string; vehicleId: string;
    skills: string[]; rating: number; lat: number; lng: number;
  }> = [
    // The seeded volunteer user from COMMIT 2 — closest, decent vehicle, driving+heavy.
    { id: "vol-01", userId: volunteerUid,    orgId: ORGS[0].id, vehicleId: "veh-van-01",   skills: ["driving", "heavy_vehicle"], rating: 4.8, lat: 21.430, lng: 92.005 },
    // Other phantom volunteers (no Auth user; just records for the matcher pool).
    { id: "vol-02", userId: "phantom-vol-2", orgId: ORGS[0].id, vehicleId: "veh-truck-01", skills: ["driving"],                  rating: 4.5, lat: 21.470, lng: 92.040 },
    { id: "vol-03", userId: "phantom-vol-3", orgId: ORGS[0].id, vehicleId: "veh-cool-01",  skills: ["driving", "medical"],       rating: 4.7, lat: 21.440, lng: 92.020 },
    { id: "vol-04", userId: "phantom-vol-4", orgId: ORGS[0].id, vehicleId: "veh-bike-01",  skills: ["driving", "rescue"],        rating: 4.2, lat: 21.420, lng: 91.990 },
  ];

  const batch = db.batch();
  seedVolunteers.forEach((v) => {
    batch.set(db.collection("volunteers").doc(v.id), {
      userId: v.userId,
      orgId: v.orgId,
      status: "available",
      currentLocation: new GeoPoint(v.lat, v.lng),
      vehicleId: v.vehicleId,
      skills: v.skills,
      rating: v.rating,
      lastActiveAt: FieldValue.serverTimestamp(),
    });
  });
  await batch.commit();
}

async function seedDisaster(declaredBy: string): Promise<void> {
  console.log("→ Seeding disaster");
  await db.collection("disasters").doc(DISASTER.id).set({
    ...DISASTER,
    declaredBy,
  });
}

async function seedDemandRequests(beneficiaryUid: string): Promise<void> {
  console.log("→ Seeding 10 demand_requests");
  const batch = db.batch();
  RAW_REQUESTS.forEach((raw, idx) => {
    const id = `req-${idx + 1}`;
    const urgency = (1 + (idx % 5)) as 1 | 2 | 3 | 4 | 5;
    const severity = urgency >= 4 ? "critical" : urgency >= 3 ? "high" : urgency >= 2 ? "medium" : "low";
    batch.set(db.collection("demand_requests").doc(id), {
      disasterId: DISASTER.id,
      source: idx % 3 === 0 ? "sms" : idx % 3 === 1 ? "app" : "web",
      requesterId: beneficiaryUid,
      items: pickItems(),
      location: randomLocation(),
      urgency,
      severity,
      raw,
      photos: [],
      createdAt: FieldValue.serverTimestamp(),
      status: "pending",
      classifiedBy: "human",
      confidence: 0.95,
      orgId: DISASTER.orgId,
    });
  });
  await batch.commit();
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const skipClear = args.includes("--no-clear");

  console.log(`ReliefOps emulator seed — project=${PROJECT_ID}`);
  console.log(`  Firestore @ ${process.env.FIRESTORE_EMULATOR_HOST}`);
  console.log(`  Auth      @ ${process.env.FIREBASE_AUTH_EMULATOR_HOST}`);
  console.log("");

  if (!skipClear) await clearAll();
  await seedOrgs();
  const users = await seedUsers();
  await seedWarehouses();
  await seedInventory();
  await seedVehicles();

  const superAdmin = users.get("super_admin")!;
  const beneficiary = users.get("beneficiary")!;
  const volunteer = users.get("volunteer")!;

  await seedVolunteers(volunteer.uid);
  await seedDisaster(superAdmin.uid);
  await seedDemandRequests(beneficiary.uid);

  console.log("");
  console.log("✔ Seed complete. Visit http://127.0.0.1:4000 to inspect.");
  console.log("  Sign in (web) with any of the *@reliefops.dev / DevPass123!");
}

main().catch((err) => {
  console.error("✗ Seed failed");
  console.error(err);
  process.exit(1);
});
