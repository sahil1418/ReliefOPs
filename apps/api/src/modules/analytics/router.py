"""Analytics — KPI rollups + timeseries + Looker Studio embed.

COMMIT 4: live KPIs computed from Firestore (cheap on demo-sized data).
COMMIT 10: + deliveries timeseries + Looker iframe URL stub.

Production target swaps the implementation for BigQuery view-backed reads
(`relief.kpis_daily` per BLUEPRINT Phase 6 Module 10), same response shapes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Query
from google.cloud import firestore as gc_firestore
from pydantic import BaseModel

from src.core.config import get_settings

from src.core.auth import CurrentUser
from src.core.errors import ApiResponse
from src.core.firebase import get_firestore

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class KpiSnapshot(BaseModel):
    activeDisasters: int
    shipmentsInTransit: int
    volunteersOnRoute: int
    kgDeliveredToday: float
    livesReached: int = 0
    onTimePct: float = 0.0
    avgEtaErrorMin: float = 0.0
    co2SavedKg: float = 0.0


class KpiPayload(ApiResponse[KpiSnapshot]):
    pass


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


@router.get("/kpis", response_model=KpiPayload)
async def kpis(
    _user: CurrentUser,
    org_id: str | None = Query(default=None, alias="orgId"),
) -> KpiPayload:
    db = get_firestore()
    ff = gc_firestore.FieldFilter

    disasters_q = db.collection("disasters").where(filter=ff("status", "==", "active"))
    if org_id:
        disasters_q = disasters_q.where(filter=ff("orgId", "==", org_id))
    active_disasters = sum(1 for _ in disasters_q.stream())

    shipments = list(db.collection("shipments").stream())
    in_transit = 0
    on_route = set()
    delivered_today_kg = 0.0
    today = _start_of_today_utc()
    for d in shipments:
        data = d.to_dict() or {}
        if org_id and data.get("orgId") != org_id:
            continue
        if data.get("status") == "in_transit":
            in_transit += 1
            v = data.get("assignedVolunteerId")
            if v:
                on_route.add(v)
        if data.get("status") == "delivered":
            delivered_at = data.get("deliveredAt")
            if isinstance(delivered_at, datetime) and delivered_at >= today:
                delivered_today_kg += float(data.get("totalKg") or 0.0)

    snap = KpiSnapshot(
        activeDisasters=active_disasters,
        shipmentsInTransit=in_transit,
        volunteersOnRoute=len(on_route),
        kgDeliveredToday=round(delivered_today_kg, 2),
        # Below are placeholder/derived — full BigQuery rollups land in COMMIT 10.
        livesReached=int(delivered_today_kg * 4),
        onTimePct=92.5 if shipments else 0.0,
        avgEtaErrorMin=12.0 if shipments else 0.0,
        co2SavedKg=round(delivered_today_kg * 0.3, 2),
    )
    return KpiPayload(data=snap)


# ── Timeseries ──────────────────────────────────────────────────────────────


class TimeseriesPoint(BaseModel):
    date: str  # YYYY-MM-DD
    deliveries: int = 0
    kgDelivered: float = 0
    livesReached: int = 0


class TimeseriesPayload(ApiResponse[list[TimeseriesPoint]]):
    pass


@router.get("/timeseries", response_model=TimeseriesPayload)
async def deliveries_timeseries(
    _user: CurrentUser,
    days: int = Query(default=14, ge=1, le=90),
    org_id: str | None = Query(default=None, alias="orgId"),
) -> TimeseriesPayload:
    """Day-by-day delivery counts.

    Production target: a SELECT against the BigQuery view `relief.kpis_daily`.
    For COMMIT 10 we compute over Firestore — fine at demo scale (≤ 10K shipments).
    """
    db = get_firestore()
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)

    bucket: dict[str, dict] = {
        (start + timedelta(days=i)).isoformat(): {"deliveries": 0, "kgDelivered": 0.0}
        for i in range(days)
    }

    docs = list(db.collection("shipments").stream())
    for d in docs:
        data = d.to_dict() or {}
        if data.get("status") != "delivered":
            continue
        if org_id and data.get("orgId") != org_id:
            continue
        delivered_at = data.get("deliveredAt")
        if not isinstance(delivered_at, datetime):
            continue
        key = delivered_at.date().isoformat()
        if key in bucket:
            bucket[key]["deliveries"] += 1
            bucket[key]["kgDelivered"] += float(data.get("totalKg") or 0)

    rows = [
        TimeseriesPoint(
            date=k,
            deliveries=v["deliveries"],
            kgDelivered=round(v["kgDelivered"], 1),
            livesReached=int(v["kgDelivered"] * 4),  # rough conversion
        )
        for k, v in sorted(bucket.items())
    ]
    return TimeseriesPayload(data=rows)


# ── Looker Studio embed ─────────────────────────────────────────────────────


class LookerEmbed(BaseModel):
    embedUrl: str
    reportId: str | None = None
    note: str = ""


class LookerEmbedPayload(ApiResponse[LookerEmbed]):
    pass


@router.get("/looker-embed", response_model=LookerEmbedPayload)
async def looker_embed(_user: CurrentUser) -> LookerEmbedPayload:
    """Returns the Looker Studio embed iframe URL.

    For COMMIT 10 demo, the dashboard is built in Looker Studio against the
    `relief.kpis_daily` BigQuery view (DDL in BLUEPRINT.md Phase 6 Module 10);
    the iframe URL is then pinned via env var `LOOKER_EMBED_URL`. If unset, we
    return an empty URL and the web page falls back to the Tremor area chart.
    """
    import os
    url = os.environ.get("LOOKER_EMBED_URL", "")
    return LookerEmbedPayload(
        data=LookerEmbed(
            embedUrl=url,
            reportId=os.environ.get("LOOKER_REPORT_ID"),
            note=(
                "Set LOOKER_EMBED_URL=<embed url> on the Cloud Run service after "
                "publishing the report from looker.google.com."
            ) if not url else "",
        )
    )
