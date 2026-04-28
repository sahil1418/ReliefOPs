"""Pure-function tests for the volunteer matcher."""
from src.modules.shipments.matcher import (
    derive_required_skills,
    haversine_km,
    match_volunteer,
)


def test_haversine_known_distance() -> None:
    # Cox's Bazar to Chittagong is roughly 110 km as the crow flies.
    d = haversine_km(21.4272, 92.0058, 22.3569, 91.7832)
    assert 100 < d < 130


def test_derive_required_skills_medicine_implies_medical() -> None:
    skills = derive_required_skills(["medicine", "food"])
    assert "medical" in skills
    assert "driving" in skills


def test_match_picks_best_score() -> None:
    volunteers = [
        # Far away, big vehicle, high rating — distance penalty drops it.
        {
            "userId": "v-far",
            "status": "available",
            "orgId": "org-1",
            "vehicleId": "veh-truck",
            "skills": ["driving"],
            "rating": 5,
            "currentLocation": {"lat": 22.30, "lng": 91.78},  # ~80 km from warehouse
        },
        # Closer, has skills, decent rating — should win.
        {
            "userId": "v-close",
            "status": "available",
            "orgId": "org-1",
            "vehicleId": "veh-van",
            "skills": ["driving", "medical"],
            "rating": 4,
            "currentLocation": {"lat": 21.43, "lng": 92.00},
        },
        # Available but not in same org — should be filtered out.
        {
            "userId": "v-other-org",
            "status": "available",
            "orgId": "org-2",
            "vehicleId": "veh-van",
            "skills": ["driving"],
            "rating": 5,
            "currentLocation": {"lat": 21.43, "lng": 92.01},
        },
        # On_route — must skip.
        {
            "userId": "v-busy",
            "status": "on_route",
            "orgId": "org-1",
            "vehicleId": "veh-van",
            "skills": ["driving"],
            "rating": 5,
            "currentLocation": {"lat": 21.43, "lng": 92.00},
        },
    ]
    vehicles = {
        "veh-truck": {"capacityKg": 5000},
        "veh-van": {"capacityKg": 1000},
    }

    match = match_volunteer(
        shipment_total_kg=200,
        shipment_org_id="org-1",
        required_skills=["driving"],
        warehouse_lat=21.4272,
        warehouse_lng=92.0058,
        volunteers=volunteers,
        vehicles_by_id=vehicles,
    )
    assert match is not None
    user_id, vehicle_id, _score = match
    assert user_id == "v-close"
    assert vehicle_id == "veh-van"


def test_match_returns_none_when_capacity_too_small() -> None:
    volunteers = [
        {
            "userId": "v1",
            "status": "available",
            "orgId": "org-1",
            "vehicleId": "veh-bike",
            "skills": ["driving"],
            "rating": 5,
            "currentLocation": {"lat": 21.43, "lng": 92.00},
        }
    ]
    vehicles = {"veh-bike": {"capacityKg": 50}}
    match = match_volunteer(
        shipment_total_kg=200,
        shipment_org_id="org-1",
        required_skills=["driving"],
        warehouse_lat=21.43,
        warehouse_lng=92.00,
        volunteers=volunteers,
        vehicles_by_id=vehicles,
    )
    assert match is None


def test_match_filters_by_required_skill() -> None:
    volunteers = [
        {
            "userId": "v1",
            "status": "available",
            "orgId": "org-1",
            "vehicleId": "veh-van",
            "skills": ["driving"],  # missing 'medical'
            "rating": 5,
            "currentLocation": {"lat": 21.43, "lng": 92.00},
        }
    ]
    vehicles = {"veh-van": {"capacityKg": 1000}}
    match = match_volunteer(
        shipment_total_kg=100,
        shipment_org_id="org-1",
        required_skills=["driving", "medical"],
        warehouse_lat=21.43,
        warehouse_lng=92.00,
        volunteers=volunteers,
        vehicles_by_id=vehicles,
    )
    assert match is None
