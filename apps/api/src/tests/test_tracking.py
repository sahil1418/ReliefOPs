"""Tracking service tests — auth gating + throttled aggregation."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import os
import pytest

from src.core.errors import ApiError
from src.modules.disasters.models import GeoPoint
from src.modules.tracking import service as tracking_service
from src.modules.tracking.models import TrackingEventCreate


def _emulator_running() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    try:
        httpx.get(f"http://{host}", timeout=0.5)
        return True
    except Exception:  # noqa: BLE001
        return False


needs_emulator = pytest.mark.skipif(
    not _emulator_running(), reason="Needs Firestore emulator running on 127.0.0.1:8080"
)


def test_record_event_rejects_beneficiary_role() -> None:
    """Beneficiaries can sign in but must not be able to spoof tracking events."""
    with pytest.raises(ApiError) as excinfo:
        tracking_service.record_event(
            TrackingEventCreate(
                shipmentId="ship-1",
                location=GeoPoint(lat=21.43, lng=92.00),
                speedKmh=30,
                accuracy=5,
            ),
            volunteer_uid="u1",
            actor_role="beneficiary",
        )
    assert excinfo.value.code == "FORBIDDEN"
    assert excinfo.value.status_code == 403


@needs_emulator
def test_first_event_aggregates_subsequent_throttled() -> None:
    """First event creates a Firestore tracking_events doc; a second ping
    immediately after should be throttled (RTDB-only).
    """
    from src.core.firebase import get_firestore

    # Use a unique shipment id so prior test runs don't pollute.
    shipment_id = f"ship-test-{int(time.time())}"

    out1 = tracking_service.record_event(
        TrackingEventCreate(
            shipmentId=shipment_id,
            location=GeoPoint(lat=21.43, lng=92.00),
            speedKmh=20,
            accuracy=5,
        ),
        volunteer_uid="u-test",
        actor_role="volunteer",
    )
    assert out1["aggregated"] is True

    out2 = tracking_service.record_event(
        TrackingEventCreate(
            shipmentId=shipment_id,
            location=GeoPoint(lat=21.44, lng=92.01),
            speedKmh=22,
            accuracy=5,
        ),
        volunteer_uid="u-test",
        actor_role="volunteer",
    )
    assert out2["aggregated"] is False

    # Confirm Firestore has exactly one tracking_events doc for this shipment.
    db = get_firestore()
    docs = list(
        db.collection("tracking_events")
        .where(field_path="shipmentId", op_string="==", value=shipment_id)
        .stream()
    )
    assert len(docs) == 1


@needs_emulator
def test_aggregation_window_can_be_bypassed_by_old_timestamp() -> None:
    """If the most recent event is older than MIN_AGGREGATION_SECONDS, the next
    ping should aggregate again. We simulate this by deleting the prior doc.
    """
    from src.core.firebase import get_firestore

    shipment_id = f"ship-test2-{int(time.time())}"

    out1 = tracking_service.record_event(
        TrackingEventCreate(
            shipmentId=shipment_id,
            location=GeoPoint(lat=21.43, lng=92.00),
        ),
        volunteer_uid="u-test2",
        actor_role="coordinator",
    )
    assert out1["aggregated"] is True

    # Manually backdate the doc so the throttle window is exhausted.
    db = get_firestore()
    docs = list(
        db.collection("tracking_events")
        .where(field_path="shipmentId", op_string="==", value=shipment_id)
        .stream()
    )
    assert len(docs) == 1
    docs[0].reference.update(
        {"ts": datetime.now(timezone.utc) - timedelta(minutes=5)}
    )

    out2 = tracking_service.record_event(
        TrackingEventCreate(
            shipmentId=shipment_id,
            location=GeoPoint(lat=21.45, lng=92.01),
        ),
        volunteer_uid="u-test2",
        actor_role="coordinator",
    )
    assert out2["aggregated"] is True
