#!/usr/bin/env bash
# COMMIT 6 acceptance: 3 shipments + 2 vehicles → 2 routes with stops + ETAs;
# cache-hit on repeat optimize.
set -euo pipefail

TOKEN=$(curl -s -X POST "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake" \
  -H 'Content-Type: application/json' \
  -d '{"email":"super@reliefops.dev","password":"DevPass123!","returnSecureToken":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['idToken'])")

mkpost() {
  local body="$1"
  echo "$body" > /tmp/_body.json
  curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -X POST "$2" --data-binary @/tmp/_body.json
}

echo "── 1. Create 3 shipments at distinct dropoff points ──"

S1=$(mkpost '{
  "disasterId":"dis-cyclone-remal-2026",
  "items":[{"sku":"RICE-25KG","qty":4,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
  "originWarehouseId":"wh-coxs-bazar",
  "dropoffLocation":{"lat":21.450,"lng":92.020},
  "dropoffAddress":"Inani Beach Camp",
  "priority":"high"
}' http://127.0.0.1:8000/api/shipments | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
echo "  S1=$S1"

S2=$(mkpost '{
  "disasterId":"dis-cyclone-remal-2026",
  "items":[{"sku":"BLANKET","qty":40,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
  "originWarehouseId":"wh-coxs-bazar",
  "dropoffLocation":{"lat":21.480,"lng":92.040},
  "dropoffAddress":"Ukhia camp",
  "priority":"normal"
}' http://127.0.0.1:8000/api/shipments | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
echo "  S2=$S2"

S3=$(mkpost '{
  "disasterId":"dis-cyclone-remal-2026",
  "items":[{"sku":"WATER-20L","qty":15,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
  "originWarehouseId":"wh-coxs-bazar",
  "dropoffLocation":{"lat":21.420,"lng":91.990},
  "dropoffAddress":"Pekua flood zone",
  "priority":"critical"
}' http://127.0.0.1:8000/api/shipments | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
echo "  S3=$S3"

echo
echo "── 2. POST /api/routes/optimize  (3 shipments x 2 vehicles, BIKE+VAN forces split) ──"
T1=$(date +%s%3N)
RESP=$(mkpost "{
  \"shipmentIds\":[\"$S1\",\"$S2\",\"$S3\"],
  \"vehicleIds\":[\"veh-bike-01\",\"veh-van-01\"],
  \"timeLimitSeconds\":4
}" http://127.0.0.1:8000/api/routes/optimize)
T2=$(date +%s%3N)
echo "$RESP" | python -c "
import json,sys
d = json.load(sys.stdin)['data']
print(f'  routes returned: {len(d)}')
for r in d:
    print(f'    [{r[\"vehicleId\"]:14s}] stops={len(r[\"stops\"]):2d} totalKm={r[\"totalKm\"]:.1f}  totalMin={r[\"totalMin\"]:3d}  computedBy={r[\"computedBy\"]}')
    for s in r['stops']:
        print(f'        -> {s[\"shipmentId\"][:8]}  arrive={s[\"etaArrive\"][11:16]}  depart={s[\"etaDepart\"][11:16]}  addr={s[\"address\"]}')
"
echo "  elapsed: $((T2-T1)) ms"

echo
echo "── 3. Repeat the same call — expect distance-matrix cache hit ──"
T1=$(date +%s%3N)
mkpost "{
  \"shipmentIds\":[\"$S1\",\"$S2\",\"$S3\"],
  \"vehicleIds\":[\"veh-bike-01\",\"veh-van-01\"],
  \"timeLimitSeconds\":4
}" http://127.0.0.1:8000/api/routes/optimize > /dev/null
T2=$(date +%s%3N)
echo "  elapsed: $((T2-T1)) ms"

echo
echo "── 4. Distance-matrix cache present? ──"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=relief-logistics \
  /d/Projects/google_soln_challenge/relief-logistics/apps/api/.venv/Scripts/python.exe -c "
from google.cloud import firestore
db = firestore.Client(project='relief-logistics')
docs = list(db.collection('route_cache').stream())
print(f'  route_cache entries: {len(docs)}')
for d in docs[:2]:
    data = d.to_dict()
    print(f'    {d.id[:12]}… usedGoogle={data.get(\"usedGoogle\")} expiresAt={data.get(\"expiresAt\")}')
"

echo
echo "── 5. Shipment now has routeId attached (cross-link) ──"
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/shipments/$S1" | python -c "
import json,sys
d = json.load(sys.stdin)['data']
print(f'  S1 routeId={d.get(\"routeId\")}  etaInitial={d.get(\"etaInitial\")}  etaCurrent={d.get(\"etaCurrent\")}')
"

echo
echo "── 6. Reroute test: post a re-optimization — expect a new route ──"
mkpost "{
  \"shipmentIds\":[\"$S1\",\"$S2\"],
  \"vehicleIds\":[\"veh-van-01\"],
  \"blockedAreas\":[
    {\"type\":\"Polygon\",\"rings\":[{\"points\":[
      {\"lat\":21.460,\"lng\":92.030},{\"lat\":21.460,\"lng\":92.050},
      {\"lat\":21.480,\"lng\":92.050},{\"lat\":21.480,\"lng\":92.030}
    ]}]}
  ],
  \"timeLimitSeconds\":4
}" http://127.0.0.1:8000/api/routes/optimize | python -c "
import json,sys
d = json.load(sys.stdin)['data']
for r in d:
    print(f'  [{r[\"vehicleId\"]}] blocked-aware={r[\"blockedAreasApplied\"]} stops={len(r[\"stops\"])} km={r[\"totalKm\"]:.1f}')
"
