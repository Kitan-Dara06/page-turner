"""
app/dependencies.py
Central FastAPI dependency functions.

─────────────────────────────────────────────────────────────────────────
JWT verification strategy
─────────────────────────────────────────────────────────────────────────

Supabase has migrated all projects to ES256 (P-256 ECC) asymmetric signing.
The server signs tokens with its *private* key; we verify with the *public*
key fetched from the JWKS endpoint — we never need the JWT secret at all.

JWKS endpoint:
    {SUPABASE_URL}/auth/v1/.well-known/jwks.json

`jwt.PyJWKClient` (PyJWT 2.x) handles JWKS fetching, key caching by `kid`,
and automatic rotation refresh transparently.

Algorithm priority:
  1. ES256 via JWKS   — when SUPABASE_URL is configured (production)
  2. HS256 via secret — when only SUPABASE_JWT_SECRET is set (legacy projects)
  3. Dev fallback     — neither configured: header value used directly as UUID

Admin guard:
  `require_admin` additionally asserts user_uuid == ADMIN_USER_UUID.
  Set that to your own Supabase user UUID in .env so only you can hit
  /api/admin/*.

─────────────────────────────────────────────────────────────────────────
"""
import logging
from functools import lru_cache
from typing import Optional

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


# ── JWKS client (ES256) ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_jwks_client() -> Optional[pyjwt.PyJWKClient]:
    """
    Returns a cached PyJWKClient pointed at the Supabase JWKS endpoint.
    Keys are fetched on first use and cached in memory by `kid`.
    Returns None if SUPABASE_URL is not configured (dev mode).
    """
    if not settings.SUPABASE_URL:
        return None
    jwks_url = settings.SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    logger.info(f"JWKS client initialised → {jwks_url}")
    return pyjwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


# ── User identity ─────────────────────────────────────────────────────────────


def get_current_user_uuid(
    authorization: Optional[str] = Header(default=None),
) -> str:
    """
    Extracts and verifies the Supabase JWT from the Authorization header.

    Returns the `sub` claim (= the user's UUID in auth.users).

    Resolution order:
      1. ES256 / JWKS  — when SUPABASE_URL is set (P-256 ECC, all modern projects)
      2. HS256 / secret — when only SUPABASE_JWT_SECRET is set (legacy)
      3. Dev fallback  — no JWT config: treat header value as UUID directly
    """
    jwks_client = _get_jwks_client()

    # ── Dev / local fallback (no JWT config at all) ───────────────────────────
    if not jwks_client and not settings.SUPABASE_JWT_SECRET:
        if authorization:
            token = authorization.removeprefix("Bearer ").strip()
            if token:
                return token
        return "00000000-0000-0000-0000-000000000001"

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:].strip()  # strip "Bearer "

    # ── Path 1: ES256 via JWKS (P-256 ECC — Supabase default) ─────────────────
    if jwks_client:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )
            user_uuid: Optional[str] = payload.get("sub")
            if not user_uuid:
                raise HTTPException(status_code=401, detail="Token missing sub claim.")
            return user_uuid
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except pyjwt.PyJWTError as e:
            logger.warning(f"ES256 JWT verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # ── Path 2: HS256 via shared secret (legacy fallback) ─────────────────────
    try:
        payload = pyjwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_uuid = payload.get("sub")
        if not user_uuid:
            raise HTTPException(status_code=401, detail="Token missing sub claim.")
        return user_uuid
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.PyJWTError as e:
        logger.warning(f"HS256 JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Admin guard ───────────────────────────────────────────────────────────────


def require_admin(user_uuid: str = Depends(get_current_user_uuid)) -> str:
    """
    Restricts access to the configured ADMIN_USER_UUID only.

    Set ADMIN_USER_UUID in .env to your Supabase user UID.
    When not set, passes through in dev mode (all authenticated users pass).
    """
    if settings.ADMIN_USER_UUID and user_uuid != settings.ADMIN_USER_UUID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access only.",
        )
    return user_uuid
