"""Volunteer auto-match — see BLUEPRINT.md Phase 6 Module 4.

Algorithm (deterministic, no ML):
  1. Filter volunteers where status == 'available' AND orgId matches the shipment.
  2. Vehicle capacity (kg) must be ≥ shipment.totalKg.
  3. Required skills (computed from item categories) must be a subset of
     volunteer.skills.
  4. Distance from the volunteer's currentLocation to the origin warehouse is
     computed via haversine; volunteers more than `MAX_RADIUS_KM` away are dropped.
  5. Score = 100 - (distance_km * 2) + (rating * 5).
  6. Return the top-scored volunteer's userId, or None if no match.

Pure function over plain dicts — easy to unit-test without Firestore.
"""
from __future__ import annotations

import math
from typing import Iterable

MAX_RADIUS_KM = 30.0
EARTH_RADIUS_KM = 6371.0


def haversine_km(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    """Great-circle distance between two lat/lng points in kilometres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def derive_required_skills(item_categories: Iterable[str]) -> set[str]:
    """Map shipment item categories to volunteer skills required to deliver them.

    Cold-chain items (medicine) need 'medical' skill; rescue items need first-aid;
    all others are general 'driving'. Override per deployment by editing this map.
    """
    mapping = {
        "medicine": "medical",
        "rescue": "rescue",
        "food": "driving",
        "water": "driving",
        "shelter": "driving",
    }
    return {mapping.get(c, "driving") for c in item_categories}


def match_volunteer(
    *,
    shipment_total_kg: float,
    shipment_org_id: str,
    required_skills: Iterable[str],
    warehouse_lat: float,
    warehouse_lng: float,
    volunteers: list[dict],
    vehicles_by_id: dict[str, dict],
    max_radius_km: float = MAX_RADIUS_KM,
) -> tuple[str, str, float] | None:
    """Return `(volunteer_user_id, vehicle_id, score)` or `None` if no candidate fits.

    `volunteers` is the result of a Firestore `volunteers` query — each dict expected
    to contain at least: `userId`, `status`, `vehicleId`, `currentLocation`
    `{lat,lng}` (or Firestore GeoPoint), `skills` list, optional `rating`.

    `vehicles_by_id` maps vehicleId → vehicle dict containing `capacityKg`.
    """
    needed_skills = set(required_skills)

    scored: list[tuple[float, str, str]] = []
    for v in volunteers:
        if v.get("status") != "available":
            continue
        if shipment_org_id and v.get("orgId") and v["orgId"] != shipment_org_id:
            continue
        vehicle_id = v.get("vehicleId")
        if not vehicle_id or vehicle_id not in vehicles_by_id:
            continue
        vehicle = vehicles_by_id[vehicle_id]
        if vehicle.get("capacityKg", 0) < shipment_total_kg:
            continue
        skills = set(v.get("skills") or [])
        if not needed_skills.issubset(skills):
            continue
        loc = v.get("currentLocation")
        if loc is None:
            continue
        v_lat = getattr(loc, "latitude", None) or loc.get("lat")
        v_lng = getattr(loc, "longitude", None) or loc.get("lng")
        if v_lat is None or v_lng is None:
            continue
        dist = haversine_km(v_lat, v_lng, warehouse_lat, warehouse_lng)
        if dist > max_radius_km:
            continue
        rating = float(v.get("rating") or 0.0)
        score = 100.0 - dist * 2.0 + rating * 5.0
        user_id = v.get("userId") or v.get("id")
        if not user_id:
            continue
        scored.append((score, user_id, vehicle_id))

    if not scored:
        return None
    scored.sort(reverse=True)
    score, user_id, vehicle_id = scored[0]
    return user_id, vehicle_id, score
