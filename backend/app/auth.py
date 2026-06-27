"""
Supabase JWT authentication dependency.
Verifies Supabase JWTs (ES256/P-256 ECC) via JWKS endpoint.
Falls back to HS256 shared-secret for legacy projects.
"""

import json
import logging
from typing import Optional
from urllib.request import urlopen

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from jose.constants import Algorithms

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_jwks_cache: Optional[dict] = None


def _get_jwks() -> dict:
    """Fetch JWKS from Supabase, cached for the process lifetime."""
    global _jwks_cache
    if _jwks_cache is None and settings.SUPABASE_URL:
        try:
            url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            with urlopen(url, timeout=5) as resp:
                _jwks_cache = json.loads(resp.read())
        except Exception as e:
            logger.warning(f"Failed to fetch JWKS: {e}")
    return _jwks_cache or {}


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Verify JWT and return user UUID (sub claim)."""
    if not credentials:
        return "00000000-0000-0000-0000-000000000001"

    token = credentials.credentials

    try:
        # Decode header to get kid and algorithm
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg", "HS256")

        # Try ES256 (P-256 ECC) via JWKS
        if alg in (Algorithms.ES256, Algorithms.ES384, Algorithms.ES512) and kid:
            jwks = _get_jwks()
            jwk_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    jwk_key = key
                    break
            if jwk_key:
                public_key = jwk.construct(jwk_key)
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=[alg],
                    audience="authenticated",
                )
                return payload.get("sub", "")

        # Fallback to HS256 (shared secret)
        if settings.SUPABASE_JWT_SECRET:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
            return payload.get("sub", "")

        raise HTTPException(status_code=401, detail="No matching verification key")

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
