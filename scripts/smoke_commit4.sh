#!/usr/bin/env bash
# COMMIT 4 acceptance test — drives the full shipments lifecycle through the API.
set -euo pipefail

echo "── 1. Mint super_admin ID token ──"
TOKEN=$(curl -s -X POST "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake" \
  -H 'Content-Type: application/json' \
  -d '{"email":"super@reliefops.dev","password":"DevPass123!","returnSecureToken":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['idToken'])")
echo "  token len=${#TOKEN}"

echo
echo "── 2. /api/analytics/kpis (initial) ──"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/analytics/kpis | python -m json.tool

echo
echo "── 3. POST /api/shipments (critical priority, food + medicine) ──"
SHIPMENT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/shipments \
  -d '{
    "disasterId": "dis-cyclone-remal-2026",
    "items": [
      {"sku": "RICE-25KG", "qty": 4, "unit": "pcs", "warehouseId": "wh-coxs-bazar"},
      {"sku": "ORS-PKT", "qty": 50, "unit": "pcs", "warehouseId": "wh-coxs-bazar"}
    ],
    "originWarehouseId": "wh-coxs-bazar",
    "dropoffLocation": {"lat": 21.4530, "lng": 92.0187},
    "dropoffAddress": "Inani Beach Camp, Cox Bazar",
    "priority": "critical"
  }' | python -c "import json,sys; d=json.load(sys.stdin); print(d['data']['id'])")
echo "  created shipment_id=$SHIPMENT_ID"

echo
echo "── 4. GET shipment back: status + assigned volunteer ──"
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/shipments/$SHIPMENT_ID" \
  | python -c "import json,sys; d=json.load(sys.stdin)['data']; print(f'  status={d[\"status\"]}  volunteer={d.get(\"assignedVolunteerId\")}  vehicle={d.get(\"vehicleId\")}  totalKg={d[\"totalKg\"]}')"

echo
echo "── 5. List shipments → assert at least one ──"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/shipments \
  | python -c "import json,sys; d=json.load(sys.stdin); print(f'  count={len(d[\"data\"])}')"

echo
echo "── 6. PATCH status → in_transit ──"
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -X PATCH "http://127.0.0.1:8000/api/shipments/$SHIPMENT_ID/status" \
  -d '{"status":"in_transit","note":"Departed warehouse"}' \
  | python -c "import json,sys; d=json.load(sys.stdin)['data']; print(f'  status now={d[\"status\"]}')"

echo
echo "── 7. KPIs after status change (shipmentsInTransit should be >= 1) ──"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/analytics/kpis \
  | python -c "import json,sys; d=json.load(sys.stdin)['data']; print(f'  shipmentsInTransit={d[\"shipmentsInTransit\"]}  volunteersOnRoute={d[\"volunteersOnRoute\"]}')"

echo
echo "── 8. PATCH status → delivered ──"
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -X PATCH "http://127.0.0.1:8000/api/shipments/$SHIPMENT_ID/status" \
  -d '{"status":"delivered"}' \
  | python -c "import json,sys; d=json.load(sys.stdin)['data']; print(f'  status now={d[\"status\"]}')"

echo
echo "── 9. Audit log entries written ──"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=relief-logistics \
  /d/Projects/google_soln_challenge/relief-logistics/apps/api/.venv/Scripts/python.exe -c "
from google.cloud import firestore
db = firestore.Client(project='relief-logistics')
docs = list(db.collection('audit_logs').stream())
print(f'  total audit log entries: {len(docs)}')
for d in docs:
    data = d.to_dict()
    rid = (data.get('resourceId') or '')[:10]
    print(f'    {data.get(\"action\"):30s} {data.get(\"resource\")}/{rid}')
"

echo
echo "── 10. /shipments page renders (HTTP 307 expected without cookie; GET /shipments via API ok) ──"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/shipments)
echo "  GET /shipments (no cookie) → $STATUS"
