"""Database initialization and data ingestion for Event Congestion Intelligence."""
import csv
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "events.db"
CSV_PATH = r"C:\Users\a0v0f63\Downloads\Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            event_type TEXT,
            event_cause TEXT,
            latitude REAL,
            longitude REAL,
            end_latitude REAL,
            end_longitude REAL,
            address TEXT,
            end_address TEXT,
            zone TEXT,
            corridor TEXT,
            junction TEXT,
            police_station TEXT,
            priority TEXT,
            requires_road_closure INTEGER,
            start_datetime TEXT,
            end_datetime TEXT,
            status TEXT,
            description TEXT,
            direction TEXT,
            veh_type TEXT,
            veh_no TEXT,
            created_date TEXT,
            resolved_datetime TEXT,
            closed_datetime TEXT,
            hour_of_day INTEGER,
            day_of_week TEXT,
            duration_hours REAL,
            impact_score REAL
        );

        CREATE TABLE IF NOT EXISTS resource_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            recommended_personnel INTEGER,
            barricade_points TEXT,
            diversion_routes TEXT,
            predicted_duration_hours REAL,
            predicted_impact_score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

        CREATE TABLE IF NOT EXISTS event_outcomes (
            event_id TEXT PRIMARY KEY,
            actual_duration_hours REAL,
            actual_personnel_deployed INTEGER,
            actual_road_closure INTEGER,
            effectiveness_rating INTEGER,
            lessons_learned TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );
    """)
    conn.commit()
    conn.close()


def _parse_dt(val: str) -> str | None:
    v = val.strip() if val else ""
    if not v or v == "NULL":
        return None
    return v


def _parse_float(val: str) -> float | None:
    v = val.strip() if val else ""
    if not v or v == "NULL":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _extract_hour(dt_str: str | None) -> int | None:
    if not dt_str:
        return None
    try:
        return int(dt_str.split(" ")[1].split(":")[0])
    except (IndexError, ValueError):
        return None


def _extract_day_of_week(dt_str: str | None) -> str | None:
    if not dt_str:
        return None
    try:
        date_part = dt_str.split(" ")[0]
        d = datetime.strptime(date_part, "%Y-%m-%d")
        return d.strftime("%A")
    except (ValueError, IndexError):
        return None


def _calc_duration(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        s = start.split("+")[0].split(".")[0].strip()
        e = end.split("+")[0].split(".")[0].strip()
        fmt = "%Y-%m-%d %H:%M:%S"
        sd = datetime.strptime(s, fmt)
        ed = datetime.strptime(e, fmt)
        hours = (ed - sd).total_seconds() / 3600
        return round(hours, 2) if hours > 0 else None
    except (ValueError, IndexError):
        return None


def calculate_impact_score(event_cause: str, road_closure: bool, hour: int | None,
                           zone: str | None, corridor: str | None) -> float:
    base_scores = {
        "public_event": 6.0, "procession": 5.5, "vip_movement": 7.0,
        "protest": 7.5, "construction": 3.5, "congestion": 4.5,
        "accident": 5.5, "vehicle_breakdown": 2.5, "tree_fall": 3.5,
        "water_logging": 4.5, "pot_holes": 2.5, "road_conditions": 3.5,
        "others": 2.5, "Debris": 2.5, "test_demo": 1.0
    }
    score = base_scores.get(event_cause, 3.0)
    # Additive bonuses (not multiplicative) to avoid everything hitting 10
    if road_closure:
        score += 1.5
    if hour and hour in (8, 9, 10, 17, 18, 19, 20):
        score += 0.8
    hotspot_zones = {"North Zone 1", "East Zone 1", "Central Zone 2"}
    if zone and zone in hotspot_zones:
        score += 0.5
    if corridor and corridor != "Non-corridor":
        score += 0.4
    return min(round(score, 1), 10.0)


def ingest_csv():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if count > 0:
        print(f"Database already has {count} events. Skipping ingestion.")
        conn.close()
        return

    print(f"Ingesting data from {CSV_PATH}...")
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            start_dt = _parse_dt(row.get("start_datetime", ""))
            end_dt = _parse_dt(row.get("end_datetime", ""))
            road_closure = row.get("requires_road_closure", "").strip() == "TRUE"
            hour = _extract_hour(start_dt)
            zone = row.get("zone", "").strip()
            zone = zone if zone and zone != "NULL" else None
            corridor = row.get("corridor", "").strip() or None
            event_cause = row.get("event_cause", "").strip()

            impact = calculate_impact_score(event_cause, road_closure, hour, zone, corridor)

            batch.append((
                row.get("id", "").strip(),
                row.get("event_type", "").strip(),
                event_cause,
                _parse_float(row.get("latitude", "")),
                _parse_float(row.get("longitude", "")),
                _parse_float(row.get("endlatitude", "")),
                _parse_float(row.get("endlongitude", "")),
                row.get("address", "").strip() or None,
                row.get("end_address", "").strip() or None,
                zone,
                corridor,
                row.get("junction", "").strip() if row.get("junction", "").strip() != "NULL" else None,
                row.get("police_station", "").strip() if row.get("police_station", "").strip() != "NULL" else None,
                row.get("priority", "").strip(),
                1 if road_closure else 0,
                start_dt, end_dt,
                row.get("status", "").strip(),
                row.get("description", "").strip() if row.get("description", "").strip() != "NULL" else None,
                row.get("direction", "").strip() if row.get("direction", "").strip() != "NULL" else None,
                row.get("veh_type", "").strip() if row.get("veh_type", "").strip() != "NULL" else None,
                row.get("veh_no", "").strip() if row.get("veh_no", "").strip() != "NULL" else None,
                _parse_dt(row.get("created_date", "")),
                _parse_dt(row.get("resolved_datetime", "")),
                _parse_dt(row.get("closed_datetime", "")),
                hour,
                _extract_day_of_week(start_dt),
                _calc_duration(start_dt, end_dt),
                impact,
            ))

    conn.executemany("""
        INSERT OR IGNORE INTO events (
            id, event_type, event_cause, latitude, longitude,
            end_latitude, end_longitude, address, end_address,
            zone, corridor, junction, police_station, priority,
            requires_road_closure, start_datetime, end_datetime,
            status, description, direction, veh_type, veh_no,
            created_date, resolved_datetime, closed_datetime,
            hour_of_day, day_of_week, duration_hours, impact_score
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, batch)
    conn.commit()
    print(f"Ingested {len(batch)} events.")
    conn.close()


if __name__ == "__main__":
    init_db()
    ingest_csv()
