import hmac
from fastapi import Header, HTTPException
from src.config import settings

async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Day 16: FastAPI Security dependency that checks the X-API-Key header
    against the QUERYFORCE_API_KEY stored in .env.
    Applied to all /api/v1/* routes.
    Uses hmac.compare_digest() for constant-time comparison to prevent timing attacks.
    """
    expected_key = settings.QUERYFORCE_API_KEY.get_secret_value()
    if not hmac.compare_digest(x_api_key.encode(), expected_key.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return x_api_key
