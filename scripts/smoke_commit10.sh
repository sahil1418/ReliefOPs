#!/usr/bin/env bash
# COMMIT 10 acceptance: notifications + disruption monitor + reroute + analytics.
set -euo pipefail

TOKEN=$(curl -s -X POST 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake' \
  -H 'Content-Type: application/json' \
  -d '{"email":"super@reliefops.dev","password":"DevPass123!","returnSecureToken":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['idToken'])")

H="Authorization: Bearer $TOKEN"

echo "── 1. POST /api/notify  (push to topic) ──"
curl -s -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/notify \
  -d '{
    "channel":"push",
    "audience":{"topic":"org-relief-bd-alerts"},
    "template":{"title":"Test alert","body":"Smoke test from CI"}
  }' | python -m json.tool

echo
echo "── 2. Create a near-Inani shipment so the disruption inject affects it ──"
cat > /tmp/ship.json <<'EOF'
{
  "disasterId":"dis-cyclone-remal-2026",
  "items":[{"sku":"TARP-12X12","qty":2,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
  "originWarehouseId":"wh-coxs-bazar",
  "dropoffLocation":{"lat":21.4530,"lng":92.0187},
  "dropoffAddress":"Inani test reroute target",
  "priority":"high"
}
EOF
SHIP_ID=$(curl -s -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/shipments --data-binary @/tmp/ship.json \
  | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
echo "  shipment: $SHIP_ID"

# Move it to in_transit so the disruption monitor sees it as eligible.
curl -s -H "$H" -H 'Content-Type: application/json' \
  -X PATCH "http://127.0.0.1:8000/api/shipments/$SHIP_ID/status" \
  -d '{"status":"in_transit"}' > /dev/null

echo
echo "── 3. Inject a synthetic disruption near Inani (sev 4) ──"
curl -s -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/admin/disruption/inject \
  -d '{
    "headline":"Bridge collapse on coastal road; passable only by bike",
    "severity":4,
    "lat":21.4530,
    "lng":92.0187,
    "orgId":"org-relief-bd"
  }' | python -m json.tool

echo
echo "── 4. /api/analytics/kpis ──"
curl -s -H "$H" "http://127.0.0.1:8000/api/analytics/kpis" | python -c "
import json,sys; d=json.load(sys.stdin)['data']
print(f'  activeDisasters={d[\"activeDisasters\"]}  inTransit={d[\"shipmentsInTransit\"]}  livesReached={d[\"livesReached\"]}  co2SavedKg={d[\"co2SavedKg\"]}')
"

echo
echo "── 5. /api/analytics/timeseries (last 14 days) ──"
curl -s -H "$H" "http://127.0.0.1:8000/api/analytics/timeseries?days=14" | python -c "
import json,sys
d = json.load(sys.stdin)['data']
print(f'  series points: {len(d)}')
total = sum(p['kgDelivered'] for p in d)
print(f'  total kg delivered (14d): {total:.1f}')
"

echo
echo "── 6. /api/analytics/looker-embed ──"
curl -s -H "$H" "http://127.0.0.1:8000/api/analytics/looker-embed" | python -m json.tool

echo
echo "── 7. Verify alert + reroute side-effects in Firestore ──"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=relief-logistics \
  /d/Projects/google_soln_challenge/relief-logistics/apps/api/.venv/Scripts/python.exe -c "
from google.cloud import firestore
db = firestore.Client(project='relief-logistics')
alerts = list(db.collection('alerts').where(filter=firestore.FieldFilter('subtype','==','disruption_monitor')).stream())
routes = list(db.collection('routes').stream())
print(f'  disruption_monitor alerts: {len(alerts)}')
for a in alerts[-3:]:
    data = a.to_dict()
    print(f'    sev={data.get(\"severity\")} reroute={data.get(\"rerouteRecommended\")} {(data.get(\"headline\") or \"\")[:60]}')
print(f'  total routes documented: {len(routes)}')
"

echo
echo "── 8. Run full disruption monitor cron ──"
curl -s -H "$H" -X POST 'http://127.0.0.1:8000/api/admin/disruption/run?country=BGD' \
  | python -m json.tool
