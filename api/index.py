from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import httpx, asyncio, sqlite3, time, random
from datetime import datetime, timezone

app = FastAPI()

# --- CORS (explicit header guarantee) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB ---
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
def error_response(msg, code):
    return JSONResponse(
        status_code=code,
        content={"status": "error", "message": msg},
        headers={"Access-Control-Allow-Origin": "*"}
    )

def uuid7():
    ts = int(time.time() * 1000)
    rand = random.getrandbits(48)
    return f"{ts:012x}-{rand:012x}"

def age_group(age):
    if age <= 12: return "child"
    if age <= 19: return "teenager"
    if age <= 59: return "adult"
    return "senior"

def success(data, message=None):
    res = {"status": "success", "data": data}
    if message:
        res["message"] = message
    return JSONResponse(res, headers={"Access-Control-Allow-Origin": "*"})

# --- POST ---
@app.post("/api/profiles")
async def create_profile(request: Request):
    try:
        body = await request.json()
    except:
        return error_response("Invalid JSON body", 400)

    name = body.get("name")

    if name is None or (isinstance(name, str) and name.strip() == ""):
        return error_response("Missing or empty name", 400)
    if not isinstance(name, str):
        return error_response("Name must be a string", 422)

    name = name.strip().lower()

    # --- Idempotency ---
    cursor.execute("SELECT * FROM profiles WHERE name=?", (name,))
    row = cursor.fetchone()
    if row:
        return success(format_row(row), "Profile already exists")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            g, a, n = await asyncio.gather(
                client.get("https://api.genderize.io", params={"name": name}),
                client.get("https://api.agify.io", params={"name": name}),
                client.get("https://api.nationalize.io", params={"name": name}),
            )

        if not all(r.status_code == 200 for r in [g, a, n]):
            return error_response("Upstream service error", 502)

        g, a, n = g.json(), a.json(), n.json()

        # Gender
        gender = g.get("gender")
        prob = float(g.get("probability") or 0)
        count = int(g.get("count") or 0)
        if gender is None or count == 0:
            return error_response("No prediction available for the provided name", 404)

        # Age
        age = a.get("age")
        if age is None:
            return error_response("No age data available", 404)

        # Country
        countries = n.get("country") or []
        if not countries:
            return error_response("No country data available", 404)

        top = max(countries, key=lambda x: x.get("probability", 0))
        cid = top.get("country_id")
        cprob = float(top.get("probability") or 0)

        pid = uuid7()
        created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        cursor.execute("""
        INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pid, name, gender, prob, count, age, age_group(age), cid, cprob, created))
        conn.commit()

        return success(format_row((pid, name, gender, prob, count, age, age_group(age), cid, cprob, created)))

    except:
        return error_response("Internal server error", 500)

# --- GET list with filtering ---
@app.get("/api/profiles")
def list_profiles(
    gender: str = Query(None),
    age_group_q: str = Query(None, alias="age_group"),
    country_id: str = Query(None)
):
    query = "SELECT * FROM profiles WHERE 1=1"
    params = []

    if gender:
        query += " AND LOWER(gender)=?"
        params.append(gender.lower())

    if age_group_q:
        query += " AND age_group=?"
        params.append(age_group_q.lower())

    if country_id:
        query += " AND country_id=?"
        params.append(country_id.upper())

    cursor.execute(query, params)
    rows = cursor.fetchall()

    return success([format_row(r) for r in rows])

# --- GET by ID ---
@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str):
    cursor.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
    row = cursor.fetchone()
    if not row:
        return error_response("Profile not found", 404)
    return success(format_row(row))

# --- DELETE ---
@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str):
    cursor.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
    if not cursor.fetchone():
        return error_response("Profile not found", 404)

    cursor.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    conn.commit()

    return JSONResponse(status_code=204, content=None,
                        headers={"Access-Control-Allow-Origin": "*"})

# --- Formatter ---
def format_row(r):
    return {
        "id": r[0],
        "name": r[1],
        "gender": r[2],
        "gender_probability": r[3],
        "sample_size": r[4],
        "age": r[5],
        "age_group": r[6],
        "country_id": r[7],
        "country_probability": r[8],
        "created_at": r[9],
    }

# --- Vercel handler ---
handler = Mangum(app)