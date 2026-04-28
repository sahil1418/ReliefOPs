/**
 * RTDB → Firestore aggregator.
 *
 * Triggered on every write to `/locations/{volunteerId}`. Reads the most-recent
 * Firestore tracking_events doc for the same shipment; writes a new one only if
 * MIN_AGGREGATION_SECONDS (50s) have passed. Also publishes Pub/Sub
 * `location.updated` for analytics streaming.
 *
 * Deployed in COMMIT 10; until then the API has the same logic inline so the
 * demo runs without Functions.
 */
import * as admin from "firebase-admin";
import { onValueWritten } from "firebase-functions/v2/database";
import { PubSub } from "@google-cloud/pubsub";

if (!admin.apps.length) {
  admin.initializeApp();
}

const MIN_AGGREGATION_SECONDS = 50;
const TOPIC = "location.updated";

const pubsub = new PubSub();

export const locationAggregator = onValueWritten(
  {
    ref: "/locations/{volunteerId}",
    region: "us-central1",
  },
  async (event) => {
    const after = event.data.after.val() as
      | {
          lat?: number;
          lng?: number;
          ts?: string;
          speedKmh?: number;
          accuracy?: number;
          heading?: number;
          shipmentId?: string;
          volunteerId?: string;
        }
      | null;

    if (!after || typeof after.lat !== "number" || typeof after.lng !== "number") {
      return;
    }

    const volunteerId = after.volunteerId ?? event.params.volunteerId;
    const shipmentId = after.shipmentId ?? null;
    const db = admin.firestore();

    let recentTs: Date | null = null;
    let q = db.collection("tracking_events").orderBy("ts", "desc").limit(1) as FirebaseFirestore.Query;
    if (shipmentId) {
      q = db
        .collection("tracking_events")
        .where("shipmentId", "==", shipmentId)
        .orderBy("ts", "desc")
        .limit(1);
    } else {
      q = db
        .collection("tracking_events")
        .where("volunteerId", "==", volunteerId)
        .orderBy("ts", "desc")
        .limit(1);
    }
    const snap = await q.get();
    if (!snap.empty) {
      const ts = snap.docs[0].get("ts");
      if (ts && typeof ts.toDate === "function") recentTs = ts.toDate();
    }

    const now = new Date();
    const due =
      !recentTs || (now.getTime() - recentTs.getTime()) / 1000 >= MIN_AGGREGATION_SECONDS;
    if (!due) return;

    await db.collection("tracking_events").add({
      shipmentId,
      volunteerId,
      location: new admin.firestore.GeoPoint(after.lat, after.lng),
      ts: admin.firestore.FieldValue.serverTimestamp(),
      speedKmh: after.speedKmh ?? 0,
      accuracy: after.accuracy ?? 0,
      heading: after.heading ?? null,
    });

    try {
      await pubsub.topic(TOPIC).publishMessage({
        json: { volunteerId, shipmentId, lat: after.lat, lng: after.lng },
      });
    } catch (err) {
      console.warn("[locationAggregator] pubsub publish failed", err);
    }
  },
);
