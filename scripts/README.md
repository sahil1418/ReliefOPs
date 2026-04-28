# scripts/

Operational scripts that run against the **emulator suite** (or, when env vars
point to it, real GCP). All TS scripts use `tsx` from the workspace root:

```bash
pnpm tsx scripts/<name>.ts
```

## seed.ts

Populates a fresh emulator with the COMMIT 2 fixture set:
2 orgs · 5 users (one per role) · 2 warehouses · 20 inventory items ·
1 disaster (Cyclone Remal) · 10 demand requests.

```bash
# Terminal A — start the emulators (Firestore + Auth + RTDB + Storage + Pub/Sub)
firebase emulators:start --project relief-logistics --config infra/firebase.json

# Terminal B — run the seed
pnpm tsx scripts/seed.ts            # clears all data first
pnpm tsx scripts/seed.ts --no-clear # additive
```

After seeding, log in to the web app with any of:

| email | password | role |
|---|---|---|
| super@reliefops.dev | DevPass123! | super_admin |
| admin@reliefops.dev | DevPass123! | ngo_admin |
| coordinator@reliefops.dev | DevPass123! | coordinator |
| volunteer@reliefops.dev | DevPass123! | volunteer |
| beneficiary@reliefops.dev | DevPass123! | beneficiary |
