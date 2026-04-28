"""Seed `ai_embeddings` with a small corpus of past-disaster playbooks.

The copilot's `find_similar_past_disasters` tool ranks these by cosine similarity
to the query embedding. Run after the JS seed script:

    cd apps/api
    ./.venv/Scripts/python ../../scripts/seed_embeddings.py

Idempotent — re-running re-writes each doc with the latest embedding.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make the API src importable so we get the same Firebase init + Gemini client
# the runtime uses (with .env loaded).
HERE = Path(__file__).resolve().parent
API_DIR = HERE.parent / "apps" / "api"
sys.path.insert(0, str(API_DIR))

# Ensure emulator hosts are set even if .env didn't load (the seeder runs
# without uvicorn).
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
os.environ.setdefault("FIREBASE_DATABASE_EMULATOR_HOST", "127.0.0.1:9000")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("GCP_PROJECT_ID", "relief-logistics")

from src.core.firebase import get_firestore  # noqa: E402
from src.modules.gemini.client import get_client, is_configured  # noqa: E402

EMBED_MODEL = "gemini-embedding-001"
DIMENSIONS = 768

CORPUS: list[dict[str, str]] = [
    {
        "id": "past-cyclone-fani-2019",
        "sourceType": "disaster_report",
        "sourceId": "fani-2019",
        "text": (
            "Cyclone Fani (Odisha, India, May 2019). Lessons: pre-positioned 1.2M "
            "evacuation supplies. Critical SKUs: tarpaulin, water, ORS, candles, "
            "rice. Cold-chain insulin distribution by motorcycle teams worked "
            "well. SMS/IVR demand intake performed better than the mobile app "
            "in coastal districts where smartphone penetration was low. "
            "Door-to-door volunteer dispatch was preferred over centralized "
            "distribution centers because of crowd-control issues."
        ),
    },
    {
        "id": "past-flood-kerala-2018",
        "sourceType": "disaster_report",
        "sourceId": "kerala-flood-2018",
        "text": (
            "Kerala floods (August 2018). 1.5 million displaced. Critical needs: "
            "boats for rescue, water purification tablets, ORS, antibiotics. "
            "Diarrhea outbreaks in 6 districts within 72 hours. Mosquito-net "
            "distribution prevented a dengue surge. Volunteer rotations every "
            "4 hours kept fatigue low. Cold-chain medicine logistics were "
            "the single biggest bottleneck — refrigerated vans were scarce."
        ),
    },
    {
        "id": "past-earthquake-nepal-2015",
        "sourceType": "disaster_report",
        "sourceId": "nepal-quake-2015",
        "text": (
            "Nepal earthquake (April 2015). Magnitude 7.8. 9000 dead, 22000 "
            "injured. First-72-hour priorities: rescue supplies (rope, "
            "lifejackets, headlamps), tents, blankets, water, first-aid kits. "
            "Air-drop coordination was the highest-impact intervention. "
            "Donor-product matching marketplace mismatched 30% of donations "
            "to actual needs — a tighter SKU catalogue helped subsequent "
            "disasters."
        ),
    },
    {
        "id": "past-cyclone-amphan-2020",
        "sourceType": "disaster_report",
        "sourceId": "amphan-2020",
        "text": (
            "Cyclone Amphan (May 2020) hit West Bengal + Odisha. ~13M affected. "
            "COVID-19 era — distribution required masks, sanitizer alongside "
            "food + water. Lockdown made volunteer mobility hard. SMS-based "
            "intake critical because in-person assessments were limited. "
            "Pre-positioned playbook: ORS + paracetamol + masks every 50km, "
            "tarpaulin + tent every 100km."
        ),
    },
    {
        "id": "playbook-cold-chain",
        "sourceType": "playbook",
        "sourceId": "cold-chain",
        "text": (
            "Cold-chain logistics SOP: insulin, vaccines, blood products. "
            "Maximum transit time without refrigeration: 4 hours for vaccines, "
            "30 minutes for blood. Every cold-chain shipment must be assigned "
            "to a vehicle with `coldChain=true`. Volunteers handling these need "
            "the 'medical' skill. A coordinator must approve hand-off at the "
            "destination clinic with a temperature reading photo."
        ),
    },
    {
        "id": "playbook-evacuation",
        "sourceType": "playbook",
        "sourceId": "evac",
        "text": (
            "Evacuation route SOP: identify floodable bridges 6 hours before "
            "landfall. Volunteers carry life-jackets and rope as standard. "
            "Each route must have a backup that avoids the named flood zone. "
            "If a coordinator marks `rerouteRecommended` based on damage "
            "assessment, the OR-Tools solver re-runs with the affected polygon "
            "in `blockedAreas` and pushes the new route to the volunteer."
        ),
    },
    {
        "id": "playbook-sms-intake",
        "sourceType": "playbook",
        "sourceId": "sms-intake",
        "text": (
            "SMS demand-request format: `<DISTRICT> NEED <QTY> <ITEM> <LAT,LNG>`. "
            "Examples: `Cox's Bazar NEED 50 RICE 21.44,91.98`. "
            "Twilio webhook strips the GPS and Gemini classifies severity, "
            "category, and items from the remaining text. Auto-replies confirm "
            "with severity + reference number within 8 seconds."
        ),
    },
]


def main() -> None:
    if not is_configured():
        print("GEMINI_API_KEY missing in apps/api/.env — aborting.")
        sys.exit(1)

    db = get_firestore()
    client = get_client()
    from google.genai import types as gtypes

    print(f"Seeding {len(CORPUS)} ai_embeddings via {EMBED_MODEL} ({DIMENSIONS}-dim)...")

    for item in CORPUS:
        try:
            resp = client.models.embed_content(
                model=EMBED_MODEL,
                contents=item["text"],
                config=gtypes.EmbedContentConfig(output_dimensionality=DIMENSIONS),
            )
            vec = list(resp.embeddings[0].values)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {item['id']} (embed error: {exc})")
            continue

        db.collection("ai_embeddings").document(item["id"]).set(
            {
                "text": item["text"],
                "embedding": vec,
                "sourceType": item["sourceType"],
                "sourceId": item["sourceId"],
                "createdAt": time.time(),
            }
        )
        print(f"  + {item['id']}  ({len(vec)}-dim)")

    print("done.")


if __name__ == "__main__":
    main()
