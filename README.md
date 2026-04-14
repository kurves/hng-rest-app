## API Design and Data Persistence.

 ````POST endpoint```` at ````/api/profiles```` that accepts a name, calls three external APIs (Genderize, Agify, Nationalize), aggregates the responses, applies classification logic, and stores the result in a database.. 

## Data Processing rules:

- Call all three APIs using the provided name and aggregate the responses
- Extract gender, gender_probability, and count from Genderize. Rename count to sample_size
- Extract age from Agify. Classify age_group: 0–12 → child, 13–19 → teenager, 20–59 → adult, 60+ → senior
- Extract country list from Nationalize. Pick the country with the highest probability as country_id
- Store the processed result with a UUID v7 id and UTC created_at timestamp


### Input validation:
- **Idempotency:**  if the same name is submitted more than once, do not create a new record. Return the existing one with "message": "Profile already exists".

- Missing or empty name returns 400 Bad Request
- Non-string name returns 422 Unprocessable Entity


## Expected response format:
````
Expected response format:

{
  "status": "success",
  "data": {
    "id": "b3f9c1e2-7d4a-4c91-9c2a-1f0a8e5b6d12",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 46,
    "age_group": "adult",
    "country_id": "DRC",
    "country_probability": 0.85,
    "created_at": "2026-04-01T12:00:00Z"
  }
}
````










## Simple API Integration and Data Processing.

 ````GET endpoint```` at ````/api/classify```` that takes a name query parameter and calls the Genderize API. 

## Data Processing rules:

- Extract gender, probability, and count from the API response. Rename count to sample_size
- Compute is_confident: true when probability >= 0.7 AND sample_size >= 100. Both conditions. If either fails, it's false
- Generate processed_at on every request. UTC, ISO 8601. Not hardcoded
 
### Input validation:

- Missing or empty name returns 400 Bad Request
- Non-string name returns 422 Unprocessable Entity


## Expected response format:
````
{
 "status": "success",
 "data": {
  "name": "<name>",
  "gender": "male",
  "probability": 0.99,
  "sample_size": 1234,
  "is_confident": true,
  "processed_at": "2026-04-01T12:00:00Z"
 }
}
````
