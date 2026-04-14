from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import httpx
import asyncio
import sqlite3
from datetime import datetime, timezone
import time
import random

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

# --- DB (serverless-safe: /tmp) ---
DB_PATH = "/tmp/profiles.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    gender TEXT,
    gender_probability REAL,
    sample_size INTEGER,
    age INTEGER,
    age_group TEXT,
    country_id TEXT,
    country_probability REAL,
    created_at TEXT
)
""")
conn.commit()


# --- Helpers ---
def error_response(message: str, status_code: int):
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message}
    )


def get_age_group(age: int) -> str:
    if 0 <= age <= 12:
        return "child"
    elif 13 <= age <= 19:
        return "teenager"
    elif 20 <= age <= 59:
        return "adult"
    else:
        return "senior"


# UUID v7-like (time-ordered)
def uuid7():
    ts = int(time.time() * 1000)
    rand = random.getrandbits(48)
    return f"{ts:012x}-{rand:012x}"


# --- Endpoint ---
@app.post("/api/profiles")
async def create_profile(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("Invalid JSON body", 400)

    name = body.get("name")

    # --- Validation ---
    if name is None or (isinstance(name, str) and name.strip() == ""):
        return error_response("Missing or empty name", 400)

    if not isinstance(name, str):
        return error_response("Name must be a string", 422)

    name = name.strip().lower()

    # --- Idempotency ---
    cursor.execute("SELECT * FROM profiles WHERE name = ?", (name,))
    existing = cursor.fetchone()

    if existing:
        return {
            "status": "success",
            "message": "Profile already exists",
            "data": {
                "id": existing[0],
                "name": existing[1],
                "gender": existing[2],
                "gender_probability": existing[3],
                "sample_size": existing[4],
                "age": existing[5],
                "age_group": existing[6],
                "country_id": existing[7],
                "country_probability": existing[8],
                "created_at": existing[9],
            }
        }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            gender_res, age_res, nation_res = await asyncio.gather(
                client.get("https://api.genderize.io", params={"name": name}),
                client.get("https://api.agify.io", params={"name": name}),
                client.get("https://api.nationalize.io", params={"name": name})
            )

        if not all(r.status_code == 200 for r in [gender_res, age_res, nation_res]):
            return error_response("Upstream service error", 502)

        gender_data = gender_res.json() if gender_res.content else {}
        age_data = age_res.json() if age_res.content else {}
        nation_data = nation_res.json() if nation_res.content else {}

        # --- Genderize ---
        gender = gender_data.get("gender")
        probability = float(gender_data.get("probability") or 0)
        count = int(gender_data.get("count") or 0)

        if gender is None or count == 0:
            return error_response("No prediction available for the provided name", 404)

        # --- Agify ---
        age = age_data.get("age")
        if age is None:
            return error_response("No age data available", 404)

        age_group = get_age_group(age)

        # --- Nationalize ---
        countries = nation_data.get("country") or []
        if not countries:
            return error_response("No country data available", 404)

        top_country = max(countries, key=lambda x: x.get("probability", 0))
        country_id = top_country.get("country_id")
        country_probability = float(top_country.get("probability") or 0)

        # --- Metadata ---
        profile_id = uuid7()
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # --- Store ---
        cursor.execute("""
        INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id,
            name,
            gender,
            probability,
            count,
            age,
            age_group,
            country_id,
            country_probability,
            created_at
        ))
        conn.commit()

        return {
            "status": "success",
            "data": {
                "id": profile_id,
                "name": name,
                "gender": gender,
                "gender_probability": probability,
                "sample_size": count,
                "age": age,
                "age_group": age_group,
                "country_id": country_id,
                "country_probability": country_probability,
                "created_at": created_at
            }
        }

    except httpx.RequestError:
        return error_response("Failed to reach external services", 502)
    except Exception:
        return error_response("Internal server error", 500)


# --- Vercel handler ---
handler = Mangum(app)