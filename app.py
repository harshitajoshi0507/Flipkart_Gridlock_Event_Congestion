"""FastAPI application for Event Congestion Intelligence Platform."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import get_db, init_db, ingest_csv
from intelligence import (
    EventInput, predict_impact, recommend_resources, find_similar_events,
)

app = FastAPI(title="Event Congestion Intelligence")
BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.on_event("startup")
def startup():
    init_db()
    ingest_csv()


# ── Pages ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active": "dashboard"})


@app.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return templates.TemplateResponse(request, "map.html", {"active": "map"})


@app.get("/predict", response_class=HTMLResponse)
def predict_page(request: Request):
    return templates.TemplateResponse(request, "predict.html", {"active": "predict"})


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    return templates.TemplateResponse(request, "analytics.html", {"active": "analytics"})


# ── API Endpoints ──────────────────────────────────────────────────────
@app.get("/api/stats")
def api_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    planned = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='planned'").fetchone()["c"]
    unplanned = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='unplanned'").fetchone()["c"]
    closures = conn.execute("SELECT COUNT(*) c FROM events WHERE requires_road_closure=1").fetchone()["c"]
    high_impact = conn.execute("SELECT COUNT(*) c FROM events WHERE impact_score >= 7").fetchone()["c"]
    avg_impact = conn.execute("SELECT ROUND(AVG(impact_score),1) a FROM events").fetchone()["a"]
    conn.close()
    return {
        "total": total, "planned": planned, "unplanned": unplanned,
        "closures": closures, "high_impact": high_impact, "avg_impact": avg_impact,
    }


@app.get("/api/events/map")
def api_events_map(event_cause: str = "", event_type: str = "", zone: str = ""):
    conn = get_db()
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params = []
    if event_cause:
        conditions.append("event_cause = ?")
        params.append(event_cause)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if zone:
        conditions.append("zone = ?")
        params.append(zone)
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT id, event_type, event_cause, latitude, longitude, address, "
        f"impact_score, priority, requires_road_closure, zone, corridor, junction, "
        f"start_datetime, description "
        f"FROM events WHERE {where} LIMIT 5000",
        params,
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "type": r["event_type"], "cause": r["event_cause"],
             "lat": r["latitude"], "lng": r["longitude"], "address": r["address"] or "",
             "impact": r["impact_score"], "priority": r["priority"],
             "closure": bool(r["requires_road_closure"]), "zone": r["zone"] or "",
             "corridor": r["corridor"] or "", "junction": r["junction"] or "",
             "date": r["start_datetime"] or "", "desc": r["description"] or ""}
            for r in rows]


@app.get("/api/analytics/by-cause")
def api_by_cause():
    conn = get_db()
    rows = conn.execute(
        "SELECT event_cause, COUNT(*) cnt, ROUND(AVG(impact_score),1) avg_impact, "
        "SUM(requires_road_closure) closures FROM events GROUP BY event_cause ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [{"cause": r["event_cause"], "count": r["cnt"],
             "avg_impact": r["avg_impact"], "closures": r["closures"]} for r in rows]


@app.get("/api/analytics/by-zone")
def api_by_zone():
    conn = get_db()
    rows = conn.execute(
        "SELECT zone, COUNT(*) cnt, ROUND(AVG(impact_score),1) avg_impact "
        "FROM events WHERE zone IS NOT NULL GROUP BY zone ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [{"zone": r["zone"], "count": r["cnt"], "avg_impact": r["avg_impact"]} for r in rows]


@app.get("/api/analytics/by-hour")
def api_by_hour():
    conn = get_db()
    rows = conn.execute(
        "SELECT hour_of_day, COUNT(*) cnt FROM events "
        "WHERE hour_of_day IS NOT NULL GROUP BY hour_of_day ORDER BY hour_of_day"
    ).fetchall()
    conn.close()
    return [{"hour": r["hour_of_day"], "count": r["cnt"]} for r in rows]


@app.get("/api/analytics/by-corridor")
def api_by_corridor():
    conn = get_db()
    rows = conn.execute(
        "SELECT corridor, COUNT(*) cnt, ROUND(AVG(impact_score),1) avg_impact "
        "FROM events WHERE corridor IS NOT NULL GROUP BY corridor ORDER BY cnt DESC LIMIT 15"
    ).fetchall()
    conn.close()
    return [{"corridor": r["corridor"], "count": r["cnt"], "avg_impact": r["avg_impact"]} for r in rows]


@app.get("/api/analytics/by-day")
def api_by_day():
    conn = get_db()
    rows = conn.execute(
        "SELECT day_of_week, COUNT(*) cnt FROM events "
        "WHERE day_of_week IS NOT NULL GROUP BY day_of_week"
    ).fetchall()
    conn.close()
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    data = {r["day_of_week"]: r["cnt"] for r in rows}
    return [{"day": d, "count": data.get(d, 0)} for d in day_order]


@app.get("/api/analytics/event-driven")
def api_event_driven():
    conn = get_db()
    causes = "'public_event','procession','vip_movement','protest','construction','congestion'"
    rows = conn.execute(
        f"SELECT event_cause, event_type, COUNT(*) cnt, "
        f"ROUND(AVG(impact_score),1) avg_impact, ROUND(AVG(duration_hours),1) avg_dur "
        f"FROM events WHERE event_cause IN ({causes}) "
        f"GROUP BY event_cause, event_type ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [{"cause": r["event_cause"], "type": r["event_type"],
             "count": r["cnt"], "avg_impact": r["avg_impact"],
             "avg_duration": r["avg_dur"]} for r in rows]


@app.post("/api/predict")
def api_predict(
    event_cause: str = Form(...), event_type: str = Form("planned"),
    zone: str = Form(""), corridor: str = Form(""),
    junction: str = Form(""), hour_of_day: int = Form(12),
    day_of_week: str = Form("Monday"), requires_road_closure: bool = Form(False),
    estimated_crowd: int = Form(0), description: str = Form(""),
):
    event = EventInput(
        event_cause=event_cause, event_type=event_type,
        zone=zone or None, corridor=corridor or None,
        junction=junction or None, hour_of_day=hour_of_day,
        day_of_week=day_of_week, requires_road_closure=requires_road_closure,
        estimated_crowd=estimated_crowd, description=description,
    )
    impact = predict_impact(event)
    resources = recommend_resources(event, impact)
    similar = find_similar_events(event, limit=5)
    return {
        "impact": {
            "score": impact.impact_score,
            "risk_level": impact.risk_level,
            "duration_hours": impact.predicted_duration_hours,
            "corridors": impact.affected_corridors,
            "junctions": impact.affected_junctions,
        },
        "resources": {
            "personnel": resources.recommended_personnel,
            "barricades": resources.barricade_points,
            "diversions": resources.diversion_routes,
            "equipment": resources.equipment,
        },
        "similar_events": [
            {"id": s.id, "cause": s.event_cause, "desc": s.description[:100],
             "zone": s.zone, "corridor": s.corridor, "duration": s.duration_hours,
             "impact": s.impact_score, "date": s.start_datetime[:10]}
            for s in similar
        ],
    }


@app.get("/api/dropdowns")
def api_dropdowns():
    conn = get_db()
    causes = [r[0] for r in conn.execute(
        "SELECT DISTINCT event_cause FROM events ORDER BY event_cause").fetchall()]
    zones = [r[0] for r in conn.execute(
        "SELECT DISTINCT zone FROM events WHERE zone IS NOT NULL ORDER BY zone").fetchall()]
    corridors = [r[0] for r in conn.execute(
        "SELECT DISTINCT corridor FROM events WHERE corridor IS NOT NULL ORDER BY corridor").fetchall()]
    junctions = [r[0] for r in conn.execute(
        "SELECT DISTINCT junction FROM events WHERE junction IS NOT NULL ORDER BY junction LIMIT 50").fetchall()]
    conn.close()
    return {"causes": causes, "zones": zones, "corridors": corridors, "junctions": junctions}
