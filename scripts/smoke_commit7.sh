#!/usr/bin/env bash
# COMMIT 7 acceptance: atomic inventory reservation + 409 on overflow + expiry alerts.
set -euo pipefail

TOKEN=$(curl -s -X POST "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake" \
  -H 'Content-Type: application/json' \
  -d '{"email":"super@reliefops.dev","password":"DevPass123!","returnSecureToken":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['idToken'])")

H_AUTH="Authorization: Bearer $TOKEN"
H_JSON='Content-Type: application/json'

echo "── 1. /api/warehouses/stock — per-warehouse rollup ──"
curl -s -H "$H_AUTH" http://127.0.0.1:8000/api/warehouses/stock | python -c "
import json,sys
d = json.load(sys.stdin)['data']
print(f'  warehouses: {len(d)}')
for w in d:
    print(f'    {w[\"name\"]:38s} skus={w[\"distinctSkus\"]:2d}  qty={int(w[\"totalQty\"]):>5d}  reserved={int(w[\"totalReservedQty\"]):>4d}  kg={w[\"totalKgInStock\"]:>8.1f}  expiringSoon={w[\"expiringSoon\"]}')
"

echo
echo "── 2. Inspect RICE-25KG starting state at wh-coxs-bazar ──"
INV=$(curl -s -H "$H_AUTH" "http://127.0.0.1:8000/api/warehouses/wh-coxs-bazar/inventory?sku=RICE-25KG")
echo "$INV" | python -c "
import json,sys
d = json.load(sys.stdin)['data']
if d:
    it = d[0]
    print(f'  qty={it[\"qty\"]}  reservedQty={it[\"reservedQty\"]}')
"

echo
echo "── 3. Reserve 50 units of RICE-25KG ──"
curl -s -H "$H_AUTH" -H "$H_JSON" -X POST http://127.0.0.1:8000/api/inventory/reserve \
  -d '{"warehouseId":"wh-coxs-bazar","sku":"RICE-25KG","qty":50,"shipmentId":"test-ship-1"}' | python -m json.tool

echo
echo "── 4. RICE-25KG state after reservation ──"
curl -s -H "$H_AUTH" "http://127.0.0.1:8000/api/warehouses/wh-coxs-bazar/inventory?sku=RICE-25KG" | python -c "
import json,sys
d = json.load(sys.stdin)['data'][0]
print(f'  qty={d[\"qty\"]}  reservedQty={d[\"reservedQty\"]}  (qty + reservedQty = {d[\"qty\"] + d[\"reservedQty\"]})')
"

echo
echo "── 5. Try to reserve 999999 units → expect 409 INSUFFICIENT_STOCK ──"
curl -s -o /tmp/r.json -w "HTTP %{http_code}\n" \
  -H "$H_AUTH" -H "$H_JSON" -X POST http://127.0.0.1:8000/api/inventory/reserve \
  -d '{"warehouseId":"wh-coxs-bazar","sku":"RICE-25KG","qty":999999,"shipmentId":"test-ship-2"}'
cat /tmp/r.json | python -m json.tool

echo
echo "── 6. Expiry endpoint returns items expiring within 30 days ──"
curl -s -H "$H_AUTH" "http://127.0.0.1:8000/api/inventory/expiring?days=30" | python -c "
import json,sys
d = json.load(sys.stdin)['data']
print(f'  expiring within 30d: {len(d)}')
for e in d[:5]:
    it = e['item']
    print(f'    sev={e[\"severity\"]}  daysToExpiry={e[\"daysToExpiry\"]:>3d}  {it[\"sku\"]:20s} qty={int(it[\"qty\"]):>4d}  ({it[\"name\"]})')
"

echo
echo "── 7. Trigger the expiry-alert writer (cron path) → expect alerts doc ──"
curl -s -H "$H_AUTH" -X POST "http://127.0.0.1:8000/api/inventory/expiring/alert?days=30" | python -m json.tool

echo
echo "── 8. Verify alert was written to Firestore ──"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=relief-logistics \
  /d/Projects/google_soln_challenge/relief-logistics/apps/api/.venv/Scripts/python.exe -c "
from google.cloud import firestore
db = firestore.Client(project='relief-logistics')
docs = list(db.collection('alerts').stream())
print(f'  total alerts: {len(docs)}')
for d in docs[:3]:
    data = d.to_dict()
    print(f'    [{data.get(\"type\")}/{data.get(\"subtype\",\"\")}] sev={data.get(\"severity\")} {data.get(\"headline\")}')
"

echo
echo "── 9. Create a shipment with RICE-25KG=10 — confirm reservation ran ──"
S_ID=$(curl -s -H "$H_AUTH" -H "$H_JSON" -X POST http://127.0.0.1:8000/api/shipments \
  -d '{
    "disasterId":"dis-cyclone-remal-2026",
    "items":[{"sku":"RICE-25KG","qty":10,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
    "originWarehouseId":"wh-coxs-bazar",
    "dropoffLocation":{"lat":21.46,"lng":92.02},
    "dropoffAddress":"test reservation",
    "priority":"normal"
  }' | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
echo "  shipment_id=$S_ID"
curl -s -H "$H_AUTH" "http://127.0.0.1:8000/api/warehouses/wh-coxs-bazar/inventory?sku=RICE-25KG" | python -c "
import json,sys
d = json.load(sys.stdin)['data'][0]
print(f'  RICE-25KG after second reserve: qty={d[\"qty\"]}  reservedQty={d[\"reservedQty\"]}')
"

echo
echo "── 10. PATCH shipment → delivered → reservedQty drains ──"
curl -s -H "$H_AUTH" -H "$H_JSON" -X PATCH "http://127.0.0.1:8000/api/shipments/$S_ID/status" \
  -d '{"status":"delivered"}' > /dev/null
curl -s -H "$H_AUTH" "http://127.0.0.1:8000/api/warehouses/wh-coxs-bazar/inventory?sku=RICE-25KG" | python -c "
import json,sys
d = json.load(sys.stdin)['data'][0]
print(f'  RICE-25KG after delivered: qty={d[\"qty\"]}  reservedQty={d[\"reservedQty\"]}  (10 units consumed from reserved)')
"
