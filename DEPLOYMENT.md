# Deployment guide — ReliefOps

Three external systems, one repo. Total time end-to-end: **~25 minutes** for a fresh setup.

```
GitHub  ──push──→ ┬─→ Render (backend, Cloud Run alternative)
                  └─→ Vercel (frontend, Next.js)
                       ↑
                  Firebase project (Firestore + RTDB + Auth + Storage)
```

---

## Step 1 — Create Firebase project (~5 minutes)

The platform needs **real** Firestore, Realtime Database, Authentication, and Storage. Free Spark plan is enough.

### 1a. Create or attach a project

1. Go to <https://console.firebase.google.com/>
2. Click **Add project**.
3. **Project name**: `reliefops` (or attach to your existing GCP project `sol`).
4. Disable Google Analytics for this project (skip the optional step).
5. Wait for "Your new project is ready" → **Continue**.

### 1b. Enable services

In the left nav, enable each one (one click each):

| Service | Path | Settings |
|---|---|---|
| **Authentication** | Build → Authentication → Get started → Sign-in method | Enable **Email/Password** and **Google**. Enable **Phone** if you have a real phone number to test (Spark = 10/day). |
| **Firestore Database** | Build → Firestore Database → Create database | Mode: **Production**. Location: **nam5 (multi-region)**. Then Rules → paste the contents of `infra/firestore.rules` from the repo. |
| **Realtime Database** | Build → Realtime Database → Create database | Location: **United States (us-central1)**. Mode: **Production**. Rules: paste `infra/database.rules.json`. |
| **Storage** | Build → Storage → Get started | Default bucket. Rules: paste `infra/storage.rules`. |

### 1c. Register a Web app

1. Project Settings (gear icon) → **General** → scroll to *Your apps* → click `</>` (Web).
2. App nickname: `reliefops-web`.
3. **Don't** enable Firebase Hosting (we use Vercel).
4. Copy the `firebaseConfig` object — you'll need 7 values:
   ```
   apiKey, authDomain, projectId, storageBucket,
   messagingSenderId, appId, databaseURL
   ```
   The `databaseURL` is on the Realtime Database page if not in the snippet.

### 1d. Generate a service account JSON for the backend

1. Project Settings → **Service accounts** → **Generate new private key** → **Generate key** → save the JSON file.
2. **Don't commit this file.** Open it, copy the whole contents — you'll paste it as a single env var string into Render.

### 1e. Send me back

Drop these in chat:

- **The 7 NEXT_PUBLIC_FIREBASE_* values** (apiKey, authDomain, projectId, storageBucket, messagingSenderId, appId, databaseURL)
- **The service account JSON** (entire `{...}` blob — I'll redact it from any output)

---

## Step 2 — Push to GitHub (~3 minutes)

### 2a. Create the repo

Go to <https://github.com/new>:
- Repository name: `reliefops` (or anything)
- Description: `AI-powered humanitarian disaster logistics — Google Solution Challenge 2026`
- **Public** (required for free Render + Vercel auto-deploy)
- Don't tick "Add a README" / .gitignore / license — we have those already
- **Create repository**

Copy the URL shown (e.g. `https://github.com/yourname/reliefops.git`) and send it back to me.

### 2b. I'll push

I'll then run from `relief-logistics/`:

```bash
git init
git add .
git commit -m "ReliefOps — Google Solution Challenge 2026 submission"
git branch -M main
git remote add origin <your-url>
git push -u origin main
```

You'll get prompted for GitHub auth in the terminal (use a Personal Access Token as password — go to <https://github.com/settings/tokens> → Generate new token (classic) → tick `repo` scope).

---

## Step 3 — Deploy backend to Render (~5 minutes)

### 3a. Connect repo

1. <https://dashboard.render.com/select-repo>
2. **Connect** your GitHub account if not already.
3. Pick the `reliefops` repo.
4. Render reads `render.yaml` from the repo root and offers to create the `reliefops-api` service.
5. **Apply** → service starts building. First build is ~5 min (Python + OR-Tools).

### 3b. Set env vars

While it builds, click the service → **Environment** → add:

| Key | Value |
|---|---|
| `GCP_PROJECT_ID` | your Firebase project ID |
| `CORS_ORIGINS` | `https://<vercel-app-name>.vercel.app` (set after Vercel deploy; can update later) |
| `GEMINI_API_KEY` | your Gemini key |
| `FIREBASE_ADMIN_SA_JSON` | the entire JSON contents (paste as one line) |
| `GOOGLE_MAPS_API_KEY` | your Maps key (or leave empty) |

`GEMINI_MODEL_PRO` and `GEMINI_MODEL_FLASH` are pre-set to `gemini-2.5-flash` in `render.yaml` (free-tier safe). Override later if you upgrade billing.

### 3c. Verify

After build finishes, the service URL is shown (e.g. `https://reliefops-api.onrender.com`). Test:

```bash
curl https://reliefops-api.onrender.com/health
# → {"data":{"status":"ok","env":"production",...},"error":null}
```

Render free tier sleeps after 15 min idle — first request after that takes ~30 seconds.

---

## Step 4 — Deploy frontend to Vercel (~3 minutes)

### 4a. Connect repo

1. <https://vercel.com/new>
2. **Import** the GitHub repo.
3. **Framework preset**: Next.js (auto-detected).
4. **Root Directory**: `apps/web` ← **important**.
5. **Install Command**: leave default (Vercel reads `vercel.json`).
6. **Build Command**: leave default.

### 4b. Set env vars

In **Environment Variables**, add for **All Environments**:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_USE_EMULATORS` | `false` |
| `NEXT_PUBLIC_API_BASE_URL` | `https://reliefops-api.onrender.com` (your Render URL) |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | from step 1c |
| `NEXT_PUBLIC_FIREBASE_DATABASE_URL` | from step 1c |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | optional |

7. **Deploy** → ~2 min build → live at `https://<your-app>.vercel.app`

### 4c. Cross-link CORS

Go back to Render → service → Environment → set `CORS_ORIGINS=https://<your-app>.vercel.app` → Save (auto-redeploys).

---

## Step 5 — End-to-end test (~3 minutes)

### 5a. Seed Firestore with demo data

The seed script writes to your real Firestore. From your local machine (with the Firebase service account JSON saved as `serviceAccount.json` next to the repo root):

```bash
cd relief-logistics
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccount.json \
  GCLOUD_PROJECT=<your-firebase-project-id> \
  pnpm tsx scripts/seed.ts
```

This creates 2 orgs, 5 users, 2 warehouses, 20 inventory items, 1 disaster, 10 demand requests, 4 vehicles, 4 volunteers — all in your real Firebase project.

### 5b. Smoke test the live stack

1. Visit `https://<your-app>.vercel.app` → click **Sign in**.
2. Sign in with `super@reliefops.dev` / `DevPass123!` (one of the seeded users).
3. Check `/dashboard` → KPI cards should populate from your real Firestore.
4. Check `/shipments` → 0 rows initially; create one via `POST /api/shipments` (Postman/cURL with bearer token from auth emulator pattern, but production-bound).
5. Check `/copilot` → ask "Show all critical shipments" → Gemini fires `query_shipments` tool → real data flows back.
6. Open the network tab — all `/api/*` calls hit `reliefops-api.onrender.com`, all Firestore subscriptions hit `firestore.googleapis.com`.

---

## Functionality matrix — what works in production

| Feature | Works on Vercel + Render + Firebase Spark? | Notes |
|---|---|---|
| Email + Google sign-in | ✓ | Phone OTP capped at 10/day on Spark |
| Firestore CRUD + onSnapshot | ✓ | Real `firestore.googleapis.com` |
| Realtime DB GPS pings | ✓ | Web subscribes via `firebase/database` SDK |
| Cloud Storage uploads (PoD, damage assess) | ✓ | Direct from browser to Storage with security rules |
| Gemini classifier + copilot + damage assess | ✓ | Live API |
| Vector search over `ai_embeddings` | ✓ | Run `pnpm tsx scripts/seed_embeddings.py` once |
| OR-Tools VRPTW route optimization | ✓ | Pure Python, runs in Render container |
| Live OpenStreetMap tiles | ✓ | No API key needed |
| Pub/Sub event publishing | Optional | Soft-fails if `roles/pubsub.publisher` not granted to the SA |
| FCM push notifications | ✓ | Needs volunteer device + token; admin SDK is wired |
| Twilio SMS intake/notifications | Optional | Graceful no-op if Twilio creds absent |
| BigQuery analytics + Looker embed | Optional | Needs Firestore→BigQuery extension; until then `/api/analytics/timeseries` falls back to Firestore |
| Cloud Function aggregator | Skipped | Inline throttle in `tracking/service.py` does the same thing |

---

## Troubleshooting

**Render build fails on `pip install ortools`** → the free tier sometimes runs out of memory mid-build. Bump to **Starter plan** ($7/mo) for the build, then drop back to Free for runtime — Render lets you swap plans freely.

**CORS errors in browser** → make sure `CORS_ORIGINS` on Render exactly matches your Vercel URL including `https://` and no trailing slash.

**Render service sleeps and the first request takes 30s** → expected on Free tier. Solution: external uptime ping every 14 minutes (UptimeRobot free) or upgrade to Starter for always-on.

**Firestore "permission denied" in production** → make sure `infra/firestore.rules` is published to your real Firebase project (Console → Firestore → Rules → paste → Publish).

**`/copilot` returns 503 GEMINI_NOT_CONFIGURED** → `GEMINI_API_KEY` not set on Render. Set it under Environment, then "Manual Deploy → Deploy latest commit".
