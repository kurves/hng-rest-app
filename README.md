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
