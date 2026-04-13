from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from datetime import datetime, timezone

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["GET"],
    allow_headers=["*"],
)

GENDERIZE_URL = "https://api.genderize.io"



def error_response(message: str, status_code: int):
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message}
    )


@app.get("/api/classify")
async def classify(name: str = Query(None)):
    # --- Input Validation ---
    if name is None or (isinstance(name, str) and name.strip() == ""):
        return error_response("Missing or empty name", 400)

    if not isinstance(name, str):
        return error_response("Name must be a string", 422)

    try:
        # --- External API Call ---
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(GENDERIZE_URL, params={"name": name})
        
        if response.status_code != 200:
            return error_response("Upstream service error", 502)

        data = response.json()

        gender = data.get("gender")
        probability = data.get("probability")
        count = data.get("count")

        # --- Genderize Edge Case ---
        if gender is None or count == 0:
            return error_response(
                "No prediction available for the provided name", 400
            )

        # --- Processing ---
        sample_size = count
        is_confident = (
            (probability is not None and probability >= 0.7) and
            (sample_size is not None and sample_size >= 100)
        )

        processed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "status": "success",
            "data": {
                "name": name,
                "gender": gender,
                "probability": probability,
                "sample_size": sample_size,
                "is_confident": is_confident,
                "processed_at": processed_at
            }
        }

    except httpx.RequestError:
        return error_response("Failed to reach external service", 502)
    except Exception:
        return error_response("Internal server error", 500)


from mangum import Mangum
handler = Mangum(app)