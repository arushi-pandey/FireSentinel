import os
import csv
import io
import json
import smtplib
from datetime import datetime
from email.message import EmailMessage

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN",
    "https://fire-sentinel-omega.vercel.app"
)

ALERT_EMAIL = os.getenv("ALERT_EMAIL")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME or "")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fire Sentinel API",
    description="AI-based Industrial Fire Intelligence Prototype",
    version="2.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_ORIGIN,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    database_url = DATABASE_URL

    # Some providers still supply the older postgres:// format.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )


def initialize_database():
    """
    Create the alert-history table if it does not exist.
    The database is initialized lazily so the API can still
    start and report a useful error if DATABASE_URL is missing.
    """

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS response_alerts (
                    id BIGSERIAL PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    incident_name TEXT,
                    incident_type TEXT,
                    priority TEXT,
                    risk_score INTEGER,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    incident_snapshot JSONB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Pending',
                    notification_status TEXT DEFAULT 'Not configured',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

        connection.commit()

    finally:
        connection.close()


def database_ready():
    try:
        initialize_database()
        return True
    except Exception as error:
        print("Database check failed:", error)
        return False


# ============================================================
# RISK ENGINE — ORIGINAL FIRESENTINEL FORMULA
# ============================================================

def calculate_risk(
    frp: float,
    population: float,
    industrial_proximity: float,
    persistence: float,
    wind_exposure: float,
    fire_history: float
):

    thermal_score = frp * 0.25
    population_score = population * 0.20
    industrial_score = industrial_proximity * 0.20
    persistence_score = persistence * 0.15
    wind_score = wind_exposure * 0.10
    history_score = fire_history * 0.10

    total = (
        thermal_score
        + population_score
        + industrial_score
        + persistence_score
        + wind_score
        + history_score
    )

    risk_score = round(total)

    if risk_score >= 75:
        priority = "P1"
    elif risk_score >= 50:
        priority = "P2"
    else:
        priority = "P3"

    return {
        "risk_score": risk_score,
        "priority": priority,
        "breakdown": {
            "thermal_intensity": round(thermal_score),
            "population_exposure": round(population_score),
            "industrial_proximity": round(industrial_score),
            "persistence": round(persistence_score),
            "wind_exposure": round(wind_score),
            "fire_history": round(history_score),
        }
    }


# ============================================================
# REPRESENTATIVE FALLBACK DATA — ORIGINAL INCIDENTS
# ============================================================

raw_incidents = [
    {
        "id": "FIR-001",
        "name": "Industrial Thermal Event",
        "lat": 28.6139,
        "lng": 77.2090,
        "type": "Industrial Fire",
        "frp": 90,
        "temperature": "342 K",
        "population": 80,
        "industrial_proximity": 95,
        "persistence": 70,
        "wind_exposure": 85,
        "fire_history": 60,
    },
    {
        "id": "FIR-002",
        "name": "Persistent Thermal Source",
        "lat": 19.0760,
        "lng": 72.8777,
        "type": "Persistent Thermal",
        "frp": 60,
        "temperature": "318 K",
        "population": 55,
        "industrial_proximity": 90,
        "persistence": 100,
        "wind_exposure": 20,
        "fire_history": 75,
    },
    {
        "id": "FIR-003",
        "name": "Agricultural Burn",
        "lat": 30.7333,
        "lng": 76.7794,
        "type": "Agricultural Burn",
        "frp": 30,
        "temperature": "305 K",
        "population": 20,
        "industrial_proximity": 5,
        "persistence": 10,
        "wind_exposure": 15,
        "fire_history": 40,
    },
    {
        "id": "FIR-004",
        "name": "Wildfire Detection",
        "lat": 23.2599,
        "lng": 77.4126,
        "type": "Wildfire",
        "frp": 75,
        "temperature": "329 K",
        "population": 50,
        "industrial_proximity": 15,
        "persistence": 60,
        "wind_exposure": 70,
        "fire_history": 65,
    },
]


def build_incident(incident):
    risk = calculate_risk(
        frp=incident["frp"],
        population=incident["population"],
        industrial_proximity=incident["industrial_proximity"],
        persistence=incident["persistence"],
        wind_exposure=incident["wind_exposure"],
        fire_history=incident["fire_history"],
    )

    return {
        **incident,
        **risk
    }


fallback_incidents = [
    build_incident(incident)
    for incident in raw_incidents
]


# ============================================================
# LOCATION / REVERSE GEOCODING
# ============================================================

async def get_location_name(lat: float, lng: float):

    url = "https://nominatim.openstreetmap.org/reverse"

    params = {
        "lat": lat,
        "lon": lng,
        "format": "json",
        "zoom": 10,
        "addressdetails": 1,
    }

    headers = {
        "User-Agent": "FireSentinel-SIH2026/2.0"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                params=params,
                headers=headers
            )

            response.raise_for_status()

            data = response.json()
            address = data.get("address", {})

            city = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or address.get("county")
                or "Unknown location"
            )

            state = address.get("state", "")
            country = address.get("country", "")

            return ", ".join(
                part for part in [city, state, country] if part
            )

    except Exception as error:
        print("Reverse geocoding failed:", error)
        return "Location unavailable"


# ============================================================
# NASA FIRMS LIVE DATA
# ============================================================

async def fetch_firms_data():

    if not FIRMS_MAP_KEY:
        print("WARNING: FIRMS_MAP_KEY not found.")
        return []

    india_bbox = "68,6,97,37"

    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{FIRMS_MAP_KEY}/VIIRS_NOAA21_NRT/"
        f"{india_bbox}/1"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            reader = csv.DictReader(
                io.StringIO(response.text)
            )

            rows = list(reader)

            print(
                f"NASA FIRMS returned {len(rows)} detections."
            )

            return rows

    except Exception as error:
        print("NASA FIRMS request failed:", error)
        return []


# ============================================================
# LIVE FIRMS → FIRESENTINEL FORMAT
# ============================================================

def convert_firms_incident(row, index):

    try:
        lat = float(row.get("latitude", 0))
        lng = float(row.get("longitude", 0))
        frp = float(row.get("frp", 0) or 0)

        brightness = float(
            row.get("bright_ti4")
            or row.get("bright_ti5")
            or 300
        )

        confidence_raw = row.get(
            "confidence",
            "nominal"
        )

        if str(confidence_raw).lower() == "high":
            confidence = 90
        elif str(confidence_raw).lower() == "nominal":
            confidence = 65
        elif str(confidence_raw).lower() == "low":
            confidence = 40
        else:
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = 60

        # Prototype inference, not a confirmed fire classification.
        if frp >= 80:
            incident_type = "Industrial Fire"
            industrial_proximity = 85
        elif frp >= 45:
            incident_type = "Wildfire"
            industrial_proximity = 25
        else:
            incident_type = "Agricultural Burn"
            industrial_proximity = 10

        persistence = 25
        population = 35 + confidence * 0.15
        wind_exposure = 40
        fire_history = 30

        risk = calculate_risk(
            frp=min(frp, 100),
            population=min(population, 100),
            industrial_proximity=industrial_proximity,
            persistence=persistence,
            wind_exposure=wind_exposure,
            fire_history=fire_history,
        )

        return {
            "id": f"NASA-{index:04d}",
            "name": f"NASA FIRMS Hotspot {index:04d}",
            "location": "Live satellite detection",
            "lat": lat,
            "lng": lng,
            "type": incident_type,
            "frp": round(frp, 2),
            "temperature": f"{round(brightness)} K",
            "population": round(population),
            "industrial_proximity": industrial_proximity,
            "persistence": persistence,
            "wind_exposure": wind_exposure,
            "fire_history": fire_history,
            "confidence": round(confidence),
            "satellite": row.get("satellite", "VIIRS"),
            "acq_date": row.get("acq_date", ""),
            "acq_time": row.get("acq_time", ""),
            "source": "NASA FIRMS",
            **risk
        }

    except Exception as error:
        print("Could not convert FIRMS row:", error)
        return None


async def get_live_incidents():

    rows = await fetch_firms_data()

    if not rows:
        return []

    converted = []

    for index, row in enumerate(rows[:50], start=1):
        incident = convert_firms_incident(row, index)

        if incident:
            converted.append(incident)

    return converted


async def get_current_incidents():

    live_incidents = await get_live_incidents()

    return live_incidents or fallback_incidents


# ============================================================
# EMAIL NOTIFICATION
# ============================================================

def send_alert_email(incident):

    if not all([
        ALERT_EMAIL,
        SMTP_HOST,
        SMTP_USERNAME,
        SMTP_PASSWORD
    ]):
        return "Not configured"

    try:
        message = EmailMessage()

        message["Subject"] = (
            f"FireSentinel {incident.get('priority')} Alert"
        )
        message["From"] = EMAIL_FROM
        message["To"] = ALERT_EMAIL

        message.set_content(
            f"""
FIRESENTINEL EMERGENCY ALERT

Incident: {incident.get('name')}
Incident ID: {incident.get('id')}
Type: {incident.get('type')}
Priority: {incident.get('priority')}
Risk Score: {incident.get('risk_score')}

Latitude: {incident.get('lat')}
Longitude: {incident.get('lng')}

This is an automated prototype alert.
Please verify the incident before taking action.
"""
        )

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=15
        ) as server:

            server.starttls()
            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )
            server.send_message(message)

        return "Sent"

    except Exception as error:
        print("Email notification failed:", error)
        return "Failed"


# ============================================================
# ALERT STATUS MODEL
# ============================================================

class AlertStatusUpdate(BaseModel):
    status: str


VALID_ALERT_STATUSES = {
    "Pending",
    "Acknowledged",
    "Team Assigned",
    "Resolved"
}


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "message": "Fire Sentinel Backend is running",
        "data_source": "NASA FIRMS + Prototype Risk Engine"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():

    db_status = database_ready()

    return {
        "status": "online",
        "service": "Fire Sentinel API",
        "pipeline": "operational",
        "firms_configured": bool(FIRMS_MAP_KEY),
        "database": (
            "connected" if db_status else "unavailable"
        )
    }


# ============================================================
# INCIDENTS
# ============================================================

@app.get("/api/incidents")
async def get_incidents():

    return await get_current_incidents()


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):

    incidents = await get_current_incidents()

    for incident in incidents:
        if incident["id"] == incident_id:
            return incident

    raise HTTPException(
        status_code=404,
        detail="Incident not found"
    )


# ============================================================
# RISK TEST
# ============================================================

@app.get("/api/risk-test")
def risk_test():

    return calculate_risk(
        frp=90,
        population=80,
        industrial_proximity=95,
        persistence=70,
        wind_exposure=85,
        fire_history=60
    )


# ============================================================
# CREATE AND STORE ALERT
# ============================================================

@app.post("/api/alerts/{incident_id}")
async def create_alert(
    incident_id: str,
    background_tasks: BackgroundTasks
):

    incidents = await get_current_incidents()

    incident = next(
        (
            item for item in incidents
            if item["id"] == incident_id
        ),
        None
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    try:
        initialize_database()

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    INSERT INTO response_alerts (
                        incident_id,
                        incident_name,
                        incident_type,
                        priority,
                        risk_score,
                        latitude,
                        longitude,
                        incident_snapshot,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at;
                """, (
                    incident.get("id"),
                    incident.get("name"),
                    incident.get("type"),
                    incident.get("priority"),
                    incident.get("risk_score"),
                    incident.get("lat"),
                    incident.get("lng"),
                    Json(incident),
                    "Pending"
                ))

                saved_alert = cursor.fetchone()

            connection.commit()

        finally:
            connection.close()

        # Email is optional. The alert is saved even if email
        # is not configured or sending fails.
        email_status = send_alert_email(incident)

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE response_alerts
                    SET notification_status = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                """, (
                    email_status,
                    saved_alert["id"]
                ))

            connection.commit()

        finally:
            connection.close()

        return {
            "alert_generated": True,
            "alert_id": saved_alert["id"],
            "incident_id": incident_id,
            "priority": incident.get("priority"),
            "risk_score": incident.get("risk_score"),
            "status": "Pending",
            "notification_status": email_status,
            "message": "Alert saved successfully"
        }

    except Exception as error:
        print("Alert creation failed:", error)

        raise HTTPException(
            status_code=503,
            detail=(
                "Could not save alert. "
                "Check the PostgreSQL database configuration."
            )
        )


# ============================================================
# ALERT HISTORY
# ============================================================

@app.get("/api/alerts")
def get_alert_history(limit: int = 100):

    limit = max(1, min(limit, 500))

    try:
        initialize_database()

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        id,
                        incident_id,
                        incident_name,
                        incident_type,
                        priority,
                        risk_score,
                        latitude,
                        longitude,
                        status,
                        notification_status,
                        incident_snapshot,
                        created_at,
                        updated_at
                    FROM response_alerts
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (limit,))

                alerts = cursor.fetchall()

        finally:
            connection.close()

        return [
            {
                **dict(alert),
                "created_at": (
                    alert["created_at"].isoformat()
                    if alert["created_at"] else None
                ),
                "updated_at": (
                    alert["updated_at"].isoformat()
                    if alert["updated_at"] else None
                )
            }
            for alert in alerts
        ]

    except Exception as error:
        print("Alert history failed:", error)

        raise HTTPException(
            status_code=503,
            detail="Alert history is unavailable."
        )


# ============================================================
# UPDATE RESPONSE STATUS
# ============================================================

@app.patch("/api/alerts/{alert_id}/status")
def update_alert_status(
    alert_id: int,
    update: AlertStatusUpdate
):

    if update.status not in VALID_ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid status",
                "allowed_statuses": sorted(
                    VALID_ALERT_STATUSES
                )
            }
        )

    try:
        initialize_database()

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE response_alerts
                    SET status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, incident_id, status, updated_at;
                """, (
                    update.status,
                    alert_id
                ))

                updated = cursor.fetchone()

            connection.commit()

        finally:
            connection.close()

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Alert not found"
            )

        return {
            "message": "Alert status updated",
            "alert": {
                **dict(updated),
                "updated_at": (
                    updated["updated_at"].isoformat()
                    if updated["updated_at"] else None
                )
            }
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Status update failed:", error)

        raise HTTPException(
            status_code=503,
            detail="Could not update alert status."
        )


# ============================================================
# HISTORICAL ANALYTICS
# ============================================================

@app.get("/api/analytics")
def get_analytics():

    try:
        initialize_database()

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        COUNT(*) AS total_alerts,
                        COUNT(*) FILTER (
                            WHERE status != 'Resolved'
                        ) AS open_alerts,
                        COUNT(*) FILTER (
                            WHERE status = 'Resolved'
                        ) AS resolved_alerts,
                        COUNT(*) FILTER (
                            WHERE priority = 'P1'
                        ) AS p1_alerts,
                        COUNT(*) FILTER (
                            WHERE priority = 'P2'
                        ) AS p2_alerts,
                        COUNT(*) FILTER (
                            WHERE priority = 'P3'
                        ) AS p3_alerts
                    FROM response_alerts;
                """)

                totals = cursor.fetchone()

                cursor.execute("""
                    SELECT
                        DATE(created_at) AS alert_date,
                        COUNT(*) AS total
                    FROM response_alerts
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                    GROUP BY DATE(created_at)
                    ORDER BY alert_date;
                """)

                daily = cursor.fetchall()

        finally:
            connection.close()

        return {
            "totals": dict(totals),
            "daily_alerts": [
                {
                    "date": item["alert_date"].isoformat(),
                    "total": item["total"]
                }
                for item in daily
            ]
        }

    except Exception as error:
        print("Analytics failed:", error)

        raise HTTPException(
            status_code=503,
            detail="Analytics are unavailable."
        )


# ============================================================
# NEARBY INFRASTRUCTURE LOOKUP
# ============================================================

@app.get("/api/infrastructure")
async def get_nearby_infrastructure(
    lat: float,
    lng: float,
    radius: int = 5000
):

    radius = max(500, min(radius, 20000))

    overpass_url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json][timeout:25];
    (
      node(around:{radius},{lat},{lng})[amenity=hospital];
      way(around:{radius},{lat},{lng})[amenity=hospital];

      node(around:{radius},{lat},{lng})[amenity=fire_station];
      way(around:{radius},{lat},{lng})[amenity=fire_station];

      node(around:{radius},{lat},{lng})[industrial];
      way(around:{radius},{lat},{lng})[industrial];

      node(around:{radius},{lat},{lng})[amenity=school];
      way(around:{radius},{lat},{lng})[amenity=school];
    );
    out center tags;
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:

            response = await client.post(
                overpass_url,
                data={"data": query},
                headers={
                    "User-Agent": "FireSentinel-SIH2026/2.0"
                }
            )

            response.raise_for_status()

            elements = response.json().get("elements", [])

        results = []

        for element in elements:

            tags = element.get("tags", {})

            element_lat = element.get("lat")
            element_lng = element.get("lon")

            if element.get("type") == "way":
                center = element.get("center", {})
                element_lat = center.get("lat")
                element_lng = center.get("lon")

            if element_lat is None or element_lng is None:
                continue

            category = (
                tags.get("amenity")
                or tags.get("industrial")
                or "other"
            )

            results.append({
                "id": element.get("id"),
                "name": tags.get("name", "Unnamed location"),
                "category": category,
                "lat": element_lat,
                "lng": element_lng
            })

        return {
            "center": {
                "lat": lat,
                "lng": lng
            },
            "radius_meters": radius,
            "count": len(results),
            "infrastructure": results,
            "source": "OpenStreetMap Overpass API"
        }

    except Exception as error:
        print("Infrastructure lookup failed:", error)

        raise HTTPException(
            status_code=503,
            detail="Nearby infrastructure lookup is unavailable."
        )


# ============================================================
# LOCATION
# ============================================================

@app.get("/api/location")
async def get_location(lat: float, lng: float):

    location = await get_location_name(lat, lng)

    return {
        "location": location,
        "latitude": lat,
        "longitude": lng
    }