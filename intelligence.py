"""Impact prediction and resource recommendation engine."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from database import get_db, calculate_impact_score


@dataclass
class EventInput:
    event_cause: str
    event_type: str = "planned"
    zone: str | None = None
    corridor: str | None = None
    junction: str | None = None
    hour_of_day: int = 12
    day_of_week: str = "Monday"
    requires_road_closure: bool = False
    estimated_crowd: int = 0
    description: str = ""


@dataclass
class ImpactPrediction:
    impact_score: float = 0.0
    predicted_duration_hours: float = 0.0
    risk_level: str = "Low"
    affected_corridors: list[str] = field(default_factory=list)
    affected_junctions: list[str] = field(default_factory=list)


@dataclass
class ResourcePlan:
    recommended_personnel: int = 0
    barricade_points: list[str] = field(default_factory=list)
    diversion_routes: list[str] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)


@dataclass
class SimilarEvent:
    id: str = ""
    event_cause: str = ""
    description: str = ""
    zone: str = ""
    corridor: str = ""
    duration_hours: float = 0.0
    impact_score: float = 0.0
    road_closure: bool = False
    start_datetime: str = ""


# ── Diversion routes per corridor ─────────────────────────────────────
CORRIDOR_DIVERSIONS = {
    "Mysore Road": ["Magadi Road → Chord Road → Ring Road", "Kanakapura Road → NICE Road"],
    "Bellary Road 1": ["Sankey Road → Palace Road", "Hebbal Flyover → ORR North"],
    "Bellary Road 2": ["ORR North 1 → Tumkur Road", "Hennur Main Road"],
    "Tumkur Road": ["Magadi Road → Mysore Road", "Chord Road → Rajajinagar"],
    "Hosur Road": ["Bannerghata Road → Kanakapura Road", "Electronics City Flyover"],
    "ORR North 1": ["Bellary Road → Hebbal", "Hennur Main Road"],
    "ORR North 2": ["Tumkur Road → Yeshwanthpur", "Bellary Road 1"],
    "ORR East 1": ["Old Madras Road → KR Puram", "Whitefield Road"],
    "ORR East 2": ["Sarjapur Road → HSR Layout", "Old Airport Road"],
    "Old Madras Road": ["ORR East 1 → KR Puram Bridge", "Indiranagar → HAL Road"],
    "Magadi Road": ["Chord Road → Rajajinagar", "Mysore Road"],
    "Bannerghata Road": ["Hosur Road → Electronics City", "Kanakapura Road"],
    "Hennur Main Road": ["Bellary Road 2 → Hebbal", "ORR North 1"],
    "West of Chord Road": ["Magadi Road → Tumkur Road", "Rajajinagar → Yeshwanthpur"],
    "ORR West 1": ["Mysore Road → NICE Road", "Tumkur Road"],
    "Non-corridor": ["Use parallel local roads", "Check live traffic for alternatives"],
}

# ── Barricade points per junction ─────────────────────────────────────
JUNCTION_BARRICADES = {
    "VeerannapalyaJunction(BEL,HO)": ["BEL Circle approach", "Veerannapalya bus stop", "Sadashivanagar entry"],
    "Nagavara-ORR Junction": ["Nagavara signal", "ORR underpass entry", "Hennur approach"],
    "HebbalFlyoverJunc": ["Hebbal flyover entry", "Bellary Road approach", "ORR exit ramp"],
    "SilkBoardJunc": ["Hosur Road approach", "BTM Layout entry", "HSR Layout approach"],
    "SantheCircle": ["Santhe Circle north arm", "South approach", "Market road entry"],
}


def predict_impact(event: EventInput) -> ImpactPrediction:
    """Predict impact score and details for a new event."""
    score = calculate_impact_score(
        event.event_cause, event.requires_road_closure,
        event.hour_of_day, event.zone, event.corridor,
    )
    # Crowd multiplier — apply ONCE with tiered scaling
    if event.estimated_crowd > 10000:
        score = min(score * 1.4, 10.0)
    elif event.estimated_crowd > 5000:
        score = min(score * 1.3, 10.0)
    elif event.estimated_crowd > 1000:
        score = min(score * 1.15, 10.0)

    # Predict duration from MEDIAN of similar past events (cap outliers)
    conn = get_db()
    rows = conn.execute(
        "SELECT duration_hours FROM events "
        "WHERE event_cause = ? AND duration_hours IS NOT NULL "
        "AND duration_hours > 0 AND duration_hours < 72 "
        "ORDER BY duration_hours",
        (event.event_cause,),
    ).fetchall()
    if rows:
        durations = [r["duration_hours"] for r in rows]
        mid = len(durations) // 2
        avg_dur = durations[mid]  # median
    else:
        avg_dur = 3.0
    conn.close()

    if event.requires_road_closure:
        avg_dur *= 1.2
    # Sensible caps per event type
    duration_caps = {
        "public_event": 8, "procession": 6, "vip_movement": 4,
        "protest": 12, "construction": 48, "congestion": 4,
        "accident": 4, "vehicle_breakdown": 3, "tree_fall": 6,
        "water_logging": 8, "pot_holes": 24, "road_conditions": 12,
    }
    max_dur = duration_caps.get(event.event_cause, 12)
    avg_dur = max(min(avg_dur, max_dur), 1.0)  # floor at 1 hour

    risk = "Low" if score < 4 else "Medium" if score < 7 else "High" if score < 9 else "Critical"

    corridors = [event.corridor] if event.corridor and event.corridor != "Non-corridor" else []
    junctions = [event.junction] if event.junction else []

    return ImpactPrediction(
        impact_score=round(score, 1),
        predicted_duration_hours=round(avg_dur, 1),
        risk_level=risk,
        affected_corridors=corridors,
        affected_junctions=junctions,
    )


def recommend_resources(event: EventInput, impact: ImpactPrediction) -> ResourcePlan:
    """Recommend manpower, barricades, and diversion routes."""
    base = int(impact.impact_score * 3)
    if event.requires_road_closure:
        base = int(base * 1.5)
    if event.estimated_crowd > 5000:
        base = int(base * 2.0)
    elif event.estimated_crowd > 1000:
        base = int(base * 1.5)
    if event.event_cause == "vip_movement":
        base = int(base * 2.0)
    if impact.predicted_duration_hours > 6:
        base = int(base * 1.3)

    minimums = {
        "public_event": 8, "procession": 6, "vip_movement": 15,
        "protest": 10, "construction": 4, "congestion": 4,
    }
    personnel = max(base, minimums.get(event.event_cause, 4))
    # Cap to realistic deployable numbers
    personnel = min(personnel, 60)

    # Barricade points
    barricades = []
    if event.junction and event.junction in JUNCTION_BARRICADES:
        barricades = JUNCTION_BARRICADES[event.junction]
    elif event.requires_road_closure:
        barricades = ["Entry point to event area", "Exit point from event area",
                      "Nearest major intersection"]

    # Diversion routes
    diversions = []
    corridor_key = event.corridor or "Non-corridor"
    if corridor_key in CORRIDOR_DIVERSIONS:
        diversions = CORRIDOR_DIVERSIONS[corridor_key]

    # Equipment
    equipment = ["Traffic cones", "Reflective barriers"]
    if event.requires_road_closure:
        equipment.extend(["Road closure signs", "Detour signs"])
    if impact.risk_level in ("High", "Critical"):
        equipment.extend(["PA system", "Emergency vehicle standby"])
    if event.event_cause == "vip_movement":
        equipment.extend(["Pilot vehicles", "Communication radios"])

    return ResourcePlan(
        recommended_personnel=personnel,
        barricade_points=barricades,
        diversion_routes=diversions,
        equipment=equipment,
    )


def find_similar_events(event: EventInput, limit: int = 10) -> list[SimilarEvent]:
    """Find historically similar events with progressive fallback."""
    conn = get_db()

    # Try strict match first (cause + zone + corridor), then relax
    search_tiers = []
    if event.zone and event.corridor:
        search_tiers.append((["event_cause = ?", "zone = ?", "corridor = ?"],
                             [event.event_cause, event.zone, event.corridor]))
    if event.zone:
        search_tiers.append((["event_cause = ?", "zone = ?"],
                             [event.event_cause, event.zone]))
    if event.corridor:
        search_tiers.append((["event_cause = ?", "corridor = ?"],
                             [event.event_cause, event.corridor]))
    # Always fallback to cause-only
    search_tiers.append((["event_cause = ?"], [event.event_cause]))

    rows = []
    for conditions, params in search_tiers:
        where = " AND ".join(conditions)
        query = f"""
            SELECT id, event_cause, description, zone, corridor,
                   duration_hours, impact_score, requires_road_closure, start_datetime
            FROM events WHERE {where}
            ORDER BY start_datetime DESC LIMIT ?
        """
        rows = conn.execute(query, params + [limit]).fetchall()
        if rows:
            break
    conn.close()

    return [
        SimilarEvent(
            id=r["id"], event_cause=r["event_cause"],
            description=r["description"] or "",
            zone=r["zone"] or "", corridor=r["corridor"] or "",
            duration_hours=r["duration_hours"] or 0,
            impact_score=r["impact_score"] or 0,
            road_closure=bool(r["requires_road_closure"]),
            start_datetime=r["start_datetime"] or "",
        )
        for r in rows
    ]


