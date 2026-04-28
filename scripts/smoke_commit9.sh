#!/usr/bin/env bash
# COMMIT 9 acceptance: Gemini copilot fires the right tool + damage assessment.
set -euo pipefail

TOKEN=$(curl -s -X POST "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake" \
  -H 'Content-Type: application/json' \
  -d '{"email":"super@reliefops.dev","password":"DevPass123!","returnSecureToken":true}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['idToken'])")
H="Authorization: Bearer $TOKEN"

# Create a few critical shipments so query_shipments returns something.
echo "── Setup: 2 critical shipments ──"
for ADDR in "Inani Beach Camp" "Pekua flood zone"; do
  cat > /tmp/ship.json <<EOF
{
  "disasterId":"dis-cyclone-remal-2026",
  "items":[{"sku":"ORS-PKT","qty":40,"unit":"pcs","warehouseId":"wh-coxs-bazar"}],
  "originWarehouseId":"wh-coxs-bazar",
  "dropoffLocation":{"lat":21.46,"lng":92.02},
  "dropoffAddress":"$ADDR",
  "priority":"critical"
}
EOF
  curl -s -H "$H" -H 'Content-Type: application/json' \
    -X POST http://127.0.0.1:8000/api/shipments --data-binary @/tmp/ship.json > /dev/null
done

echo
echo "── 1. /api/copilot/chat — 'Show me all critical shipments' ──"
echo "    (capture SSE stream, look for query_shipments tool call)"
curl -s -N -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/copilot/chat \
  -d '{"message":"Show me all critical shipments. Just list them with their dropoff addresses."}' \
  | python -c "
import json, sys, re
events = []
text_chunks = []
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'): continue
    try:
        ev = json.loads(line[5:].strip())
    except: continue
    events.append(ev)
    if ev['type'] == 'tool_call':
        print(f'  TOOL_CALL  {ev[\"content\"][\"name\"]}({json.dumps(ev[\"content\"][\"args\"])[:60]})')
    elif ev['type'] == 'tool_result':
        r = ev['content']['result']
        summary = (
            f'count={r[\"count\"]}' if isinstance(r.get('count'), int)
            else f'matches={len(r[\"matches\"])}' if isinstance(r.get('matches'), list)
            else f'ok={r.get(\"ok\")}'
        )
        print(f'  TOOL_RESULT {ev[\"content\"][\"name\"]}: {summary}')
    elif ev['type'] == 'text':
        text_chunks.append(ev['content'])
    elif ev['type'] == 'conversation':
        print(f'  CONVERSATION id={ev[\"content\"][\"id\"]}')
    elif ev['type'] == 'done':
        print('  DONE')
print()
final = ''.join(text_chunks)
print(f'  Final assistant text ({len(final)} chars):')
print('  ' + final[:400].replace(chr(10), chr(10)+'  '))

# Acceptance checks
tool_calls = [e for e in events if e['type'] == 'tool_call']
assert any(t['content']['name'] == 'query_shipments' for t in tool_calls), 'expected query_shipments tool call'
print()
print('  ASSERT: query_shipments was called ✓'.replace('✓', '[OK]'))
"

echo
echo "── 2. /api/copilot/chat — 'summarize disaster Cyclone Remal' ──"
curl -s -N -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/copilot/chat \
  -d '{"message":"Summarize the operational status of disaster dis-cyclone-remal-2026."}' \
  | python -c "
import json,sys
tools = []
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'): continue
    try: ev = json.loads(line[5:].strip())
    except: continue
    if ev['type'] == 'tool_call':
        tools.append(ev['content']['name'])
print(f'  Tools called: {tools}')
assert 'summarize_disaster_status' in tools, 'expected summarize_disaster_status'
print('  ASSERT: summarize_disaster_status was called [OK]')
"

echo
echo "── 3. Vector search via copilot — 'find playbooks for cold chain delivery' ──"
curl -s -N -H "$H" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/copilot/chat \
  -d '{"message":"Find similar playbooks about cold chain insulin distribution from past disasters."}' \
  | python -c "
import json,sys
tools = []
matches = None
for line in sys.stdin:
    line = line.strip()
    if not line.startswith('data:'): continue
    try: ev = json.loads(line[5:].strip())
    except: continue
    if ev['type'] == 'tool_call':
        tools.append(ev['content']['name'])
    elif ev['type'] == 'tool_result' and ev['content']['name'] == 'find_similar_past_disasters':
        matches = ev['content']['result'].get('matches', [])
print(f'  Tools called: {tools}')
if matches:
    print(f'  Top {len(matches)} matches:')
    for m in matches[:3]:
        print(f'    - {m[\"id\"]:30s} score={m.get(\"score\"):.3f}')
assert 'find_similar_past_disasters' in tools, 'expected vector search tool'
print('  ASSERT: find_similar_past_disasters was called [OK]')
"
