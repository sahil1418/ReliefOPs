# ReliefOps

> *An AI dispatcher that turns disaster chaos into coordinated relief in the first 72 hours.*

**Google Solution Challenge 2026** · Targeting SDGs 2, 3, 9, 11, 13.

A production-grade humanitarian disaster logistics platform built end-to-end on the Google ecosystem:
**Gemini 2.5** (Pro · Flash · Embedding) · **Firebase** (Auth · Firestore · Realtime DB · Storage · Hosting) · **FastAPI on Cloud Run** · **OR-Tools VRPTW** · **Google Maps Platform**.

```
70%   of preventable disaster deaths happen in the first 72 hours.
4-6h  is the average dispatch decision time on phones + spreadsheets.
25-40% of donated aid is mismatched, expired, or wrongly routed.
```

ReliefOps closes that gap. One platform: ingest demand → match supply → optimize routes → track delivery → measure SDG impact — all driven by a Gemini copilot that *executes* operations in natural language.

---

## What's in the box

```
┌─────────────────────────────────────────────────────────────────┐
│ Three Gemini surfaces                                            │
│  · Demand classifier (gemini-2.5-flash)                          │
│  · Operational copilot — 5 function-calling tools (gemini-2.5-pro) │
│  · Multimodal damage assessment + auto-reroute (gemini-2.5-flash)│
├─────────────────────────────────────────────────────────────────┤
│ FastAPI modular monolith on Cloud Run                            │
│  12 modules · 50+ REST endpoints · Pydantic v2 · 35/35 tests     │
├─────────────────────────────────────────────────────────────────┤
│ Logistics intelligence                                           │
│  OR-Tools VRPTW (capacity + time-windows + blocked areas)        │
│  Distance matrix cache · live GPS via Realtime DB                │
│  Atomic Firestore inventory reservations                         │
├─────────────────────────────────────────────────────────────────┤
│ Three clients                                                    │
│  Web admin (Next.js 14, TS strict, Leaflet+OSM live map)         │
│  Mobile volunteer (Flutter + Hive offline queue)                 │
│  SMS / beneficiary PWA (Twilio webhook + Next.js)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Live verification — every claim is independently testable

| Claim | How to verify |
|---|---|
| `gemini-2.5-flash` extracts items + severity from text | `pytest -v src/tests/test_classifier.py::test_live_gemini_classifies_rice_and_ors` |
| Vector RAG ranks the cold-chain playbook #1 (cosine 0.754) | `scripts/seed_embeddings.py` then ask the copilot |
| OR-Tools VRPTW respects capacity + time windows | `pytest -v src/tests/test_routing.py` |
| GPS pings throttle to ~1 Firestore doc per minute | `bash scripts/smoke_commit8.sh` |
| Inventory reserve is atomic (409 on overflow) | `bash scripts/smoke_commit7.sh` |
| Damage assess on a flooded-road image triggers auto-reroute | `bash scripts/smoke_commit10.sh` |

---

## Repo layout (Turborepo · pnpm)

```
relief-logistics/
├── apps/
│   ├── web/          Next.js 14 admin dashboard + beneficiary portal
│   ├── api/          FastAPI on Cloud Run (modular monolith)
│   └── mobile/       Flutter volunteer app (offline-first)
├── packages/
│   ├── shared-types/ TS types + Zod schemas mirrored from Pydantic
│   ├── firebase-config/  shared Firebase client config
│   └── ui/           shared shadcn components
├── infra/
│   ├── firebase.json
│   ├── firestore.{rules,indexes.json}
│   ├── storage.rules · database.rules.json
│   ├── functions/    Cloud Functions (location aggregator)
│   └── bootstrap.sh  one-shot gcloud + firebase init
├── scripts/
│   ├── seed.ts                    ← Firestore + Auth seed
│   ├── seed_embeddings.py         ← gemini-embedding-001 → ai_embeddings
│   ├── simulate_volunteer.ts      ← GPS simulator for headless demo
│   └── smoke_commit{4,6,7,9,10}.sh  ← acceptance tests per commit
├── render.yaml             ← Render Blueprint (backend deploy)
├── apps/web/vercel.json    ← Vercel config (frontend deploy)
├── DEPLOYMENT.md           ← Step-by-step walkthrough
└── .github/workflows/      deploy-api · deploy-web · deploy-mobile
```

---

## Tech stack (pinned)

**AI**: gemini-2.5-pro · gemini-2.5-flash · gemini-embedding-001 · `google-genai 0.5` · function calling · multimodal vision · structured JSON · Firestore vector search 768d
**Backend**: FastAPI 0.115 · Pydantic 2.9 · OR-Tools 9.11 VRPTW · firebase-admin 6.5 · Python 3.12
**Web**: Next.js 14.2 (App Router) · React 18.3 · TypeScript 5.6 strict · Tailwind 3.4 · shadcn/ui · TanStack Table 8.20 · react-leaflet 4.2 · recharts 2.13 · react-markdown 9
**Mobile**: Flutter 3.24 · Riverpod 2.5 · go_router 14 · geolocator 13 · hive 2.2 · connectivity_plus
**Data**: Firestore (vector search) · Realtime Database · Cloud Storage · Cloud Pub/Sub · BigQuery + Looker Studio · Firestore→BigQuery extension
**Infra**: Cloud Run · Firebase Hosting · App Distribution · Cloud Scheduler · Secret Manager · Workload Identity Federation · GitHub Actions × 3 · Render free tier · Vercel

---

## Local development

### Prerequisites

| Tool | Version |
|---|---|
| Node.js | ≥ 20 |
| pnpm | 9.x |
| Python | 3.11 or 3.12 |
| Java JDK | 11+ (for Firebase emulators) |
| Firebase CLI | latest (`npm i -g firebase-tools`) |

### Setup

```bash
git clone <your-repo>
cd relief-logistics
pnpm install                                # install web deps
cd apps/api && python -m venv .venv && ./.venv/Scripts/pip install -r requirements-dev.txt
cp .env.example .env                        # at repo root
cp apps/web/.env.local.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env       # fill in GEMINI_API_KEY
```

### Run everything

Three terminals:

```bash
# Terminal 1 — Firebase emulators (Auth, Firestore, RTDB, Storage, Pub/Sub)
firebase emulators:start --config infra/firebase.json --project relief-logistics

# Terminal 2 — FastAPI at http://localhost:8000  (docs at /docs)
cd apps/api && ./.venv/Scripts/python -m uvicorn src.main:app --reload --port 8000

# Terminal 3 — Next.js admin web at http://localhost:3000
NEXT_PUBLIC_USE_EMULATORS=true pnpm --filter @relief/web dev
```

Then seed:

```bash
pnpm tsx scripts/seed.ts                                      # Firestore + Auth fixtures
cd apps/api && ./.venv/Scripts/python ../../scripts/seed_embeddings.py  # ai_embeddings via Gemini
```

Sign in to <http://localhost:3000> with `super@reliefops.dev` / `DevPass123!`.

---

## Production deploy

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full step-by-step guide.

```
GitHub  ──push──→ ┬─→ Render (FastAPI · render.yaml in repo root)
                  └─→ Vercel (Next.js · apps/web/vercel.json)
                       ↑
                  Firebase project (Firestore + RTDB + Auth + Storage)
```

Total time end-to-end: ~25 minutes. Free-tier deployable; `$0/mo` at demo scale.

---

## Build status

| Commit | What shipped |
|---|---|
| 01 | Monorepo bootstrap (Turborepo, Next.js shell, FastAPI health) |
| 02 | Firebase emulators + auth foundation (Admin SDK, RBAC, seed) |
| 03 | Auth flows (web: email + Google + phone OTP; mobile scaffold; session cookie middleware) |
| 04 | Admin dashboard + shipments CRUD (TanStack Table + Firestore live updates, volunteer auto-match, audit logs) |
| 05 | Disaster intake + Gemini 2.5 Flash demand classifier (live AI), SMS webhook with TwiML |
| 06 | Route optimization (OR-Tools VRPTW + Google Route Optimization stub; ComputeRouteMatrix → haversine fallback; cache 1h) |
| 07 | Inventory + warehouses (atomic reserve, 409 on overflow, expiry monitor) |
| 08 | Live GPS tracking (Realtime DB pings, 50s aggregation throttle, Cloud Function aggregator, Leaflet+OSM live map) |
| 09 | Gemini AI copilot (5 function-calling tools, SSE streaming) + multimodal damage assessment + Firestore vector search |
| 10 | Notifications (FCM + SMS), disruption monitor, analytics timeseries + Looker embed, GitHub Actions × 3 |

---

## License

MIT. Built for humanitarian use; please attribute and contribute back.

---

*Built for Google Solution Challenge 2026. SDG 02 · 03 · 09 · 11 · 13.*
