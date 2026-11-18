import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx
import csv
import io
import os
from collections import Counter


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fire Sentinel API",
    description="AI-based Industrial Fire Intelligence Prototype",
    version="1.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# RISK ENGINE
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
# REPRESENTATIVE FALLBACK DATA
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


# ============================================================
# BUILD INCIDENT
# ============================================================

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
        "User-Agent": "FireSentinel-SIH2026/1.0"
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

            parts = [city, state, country]

            return ", ".join(
                part for part in parts if part
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

    # Approximate India bounding box:
    # west, south, east, north
    india_bbox = "68,6,97,37"

    # VIIRS NOAA-21 NRT
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{FIRMS_MAP_KEY}/VIIRS_NOAA21_NRT/"
        f"{india_bbox}/1"
    )

    try:

        async with httpx.AsyncClient(timeout=30.0) as client:

            response = await client.get(url)

            response.raise_for_status()

            text = response.text

            reader = csv.DictReader(io.StringIO(text))

            rows = list(reader)

            print(f"NASA FIRMS returned {len(rows)} detections.")

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

        confidence_raw = row.get("confidence", "nominal")

        # Convert confidence to a numerical score
        if str(confidence_raw).lower() == "high":
            confidence = 90
        elif str(confidence_raw).lower() == "nominal":
            confidence = 65
        elif str(confidence_raw).lower() == "low":
            confidence = 40
        else:
            try:
                confidence = float(confidence_raw)
            except:
                confidence = 60

        # ----------------------------------------------------
        # Prototype contextual inference
        #
        # IMPORTANT:
        # FIRMS detects thermal anomalies.
        # It does NOT directly say "industrial fire".
        #
        # This is therefore a prototype classifier until
        # OSM/Sentinel/XGBoost classification is connected.
        # ----------------------------------------------------

        if frp >= 80:
            incident_type = "Industrial Fire"
            industrial_proximity = 85

        elif frp >= 45:
            incident_type = "Wildfire"
            industrial_proximity = 25

        else:
            incident_type = "Agricultural Burn"
            industrial_proximity = 10

        # FIRMS detections are treated as short-term events
        # until temporal persistence is calculated.
        persistence = 25

        population = 35
        wind_exposure = 40
        fire_history = 30

        # Higher confidence slightly increases risk.
        population += confidence * 0.15

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


# ============================================================
# GET LIVE INCIDENTS
# ============================================================

async def get_live_incidents():

    rows = await fetch_firms_data()

    if not rows:
        return []

    converted = []

    # Limit dashboard to top 50 detections.
    # This keeps the prototype fast.
    for index, row in enumerate(rows[:50], start=1):

        incident = convert_firms_incident(row, index)

        if incident:
            converted.append(incident)

    return converted


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

    return {
        "status": "online",
        "service": "Fire Sentinel API",
        "pipeline": "operational",
        "firms_configured": bool(FIRMS_MAP_KEY)
    }


# ============================================================
# INCIDENTS
# ============================================================

@app.get("/api/incidents")
async def get_incidents():

    live_incidents = await get_live_incidents()

    # If NASA returns data → use it
    if live_incidents:

        return live_incidents

    # Otherwise preserve working prototype
    return fallback_incidents


# ============================================================
# SINGLE INCIDENT
# ============================================================

@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):

    live_incidents = await get_live_incidents()

    all_incidents = live_incidents or fallback_incidents

    for incident in all_incidents:

        if incident["id"] == incident_id:

            return incident

    return {
        "error": "Incident not found"
    }


# ============================================================
# RISK TEST
# ============================================================

@app.get("/api/risk-test")
def risk_test():

    result = calculate_risk(
        frp=90,
        population=80,
        industrial_proximity=95,
        persistence=70,
        wind_exposure=85,
        fire_history=60,
    )

    return {
        "incident": "FIR-001",
        **result
    }


# ============================================================
# RESPONSE ALERT
# ============================================================

@app.post("/api/alerts/{incident_id}")
async def generate_alert(incident_id: str):

    live_incidents = await get_live_incidents()

    all_incidents = live_incidents or fallback_incidents

    for incident in all_incidents:

        if incident["id"] == incident_id:

            return {
                "status": "alert_generated",
                "incident": incident_id,
                "priority": incident["priority"],
                "risk_score": incident["risk_score"],
                "message": "Emergency response alert generated"
            }

    return {
        "status": "error",
        "message": "Incident not found"
    }

# ============================================================
# REVERSE GEOCODING ENDPOINT
# ============================================================

@app.get("/api/location")
async def get_location(lat: float, lng: float):

    location = await get_location_name(lat, lng)

    return {
        "location": location,
        "latitude": lat,
        "longitude": lng
    }