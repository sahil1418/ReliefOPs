/**
 * Cloud Functions entry point.
 *
 * COMMIT 8 adds `locationAggregator`: an RTDB onWrite trigger that throttles
 * volunteer GPS pings into 1 Firestore `tracking_events` doc per minute and
 * fans out a Pub/Sub `location.updated` event for downstream analytics.
 *
 * The same throttle behavior is implemented inline in `apps/api/src/modules/
 * tracking/service.py` so the demo runs without deploying Functions. When
 * COMMIT 10 deploys real GCP, this module takes over and the API endpoint
 * becomes redundant — both paths are wire-compatible.
 *
 * COMMIT 10 will add:
 *   - scheduled disruption monitor (Cloud Scheduler)
 *   - Pub/Sub fan-out handlers (FCM, BigQuery streaming inserts)
 */
export { locationAggregator } from "./locationAggregator";
