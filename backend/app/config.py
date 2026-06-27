from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL
    DATABASE_URI: str

    # Redis / Upstash
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""
    UPSTASH_PORT: int = 6379
    REDIS_URL: Optional[str] = None

    # Qdrant
    QDRANT_URL: str = ""
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_VECTOR_SIZE: int = 1536

    # LLM
    LLM_PROVIDER: str = "google"
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    gemini_api_key: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 8  # hot-path timeout; fallback to direct vector search

    # Google Books / Voyage / Tavily
    GOOGLE_BOOKS_API_KEY: Optional[str] = None
    VOYAGE_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # Reddit
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_AVAILABLE: bool = False

    # Taxonomy
    TAXONOMY_VERSION: int = 13

    # ── Phase 3 Auth (Supabase JWT — ES256/P-256 ECC) ──────────────────
    # JWKS endpoint derived automatically from SUPABASE_URL:
    #   {SUPABASE_URL}/auth/v1/.well-known/jwks.json
    # Tokens are signed with Supabase's private P-256 key;
    # verified here with the matching public key — no secret needed.
    SUPABASE_URL: Optional[str] = None  # ← Set this (e.g. https://xyz.supabase.co)
    SUPABASE_ANON_KEY: Optional[str] = None  # frontend use only, not for verification
    # Legacy fallback only — for HS256 projects (pre-2024).
    # Leave unset if your project uses ES256 (all modern Supabase projects).
    SUPABASE_JWT_SECRET: Optional[str] = None
    # Your own Supabase user UUID → Authentication → Users → click your row
    # Only this UUID can access /api/admin/* endpoints
    ADMIN_USER_UUID: Optional[str] = None

    # ── CORS ───────────────────────────────────────────────────
    # Space-separated allowed origins. Add staging/prod domains when deploying.
    FRONTEND_ORIGINS: str = "http://localhost:3000 https://page-turner-seven.vercel.app"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _compute_derived(self) -> "Settings":
        # Redis URL
        if (
            not self.REDIS_URL
            and self.UPSTASH_REDIS_REST_URL
            and self.UPSTASH_REDIS_REST_TOKEN
        ):
            host = self.UPSTASH_REDIS_REST_URL.replace("https://", "")
            self.REDIS_URL = (
                f"rediss://default:{self.UPSTASH_REDIS_REST_TOKEN}"
                f"@{host}:{self.UPSTASH_PORT}"
            )
        if not self.REDIS_URL:
            self.REDIS_URL = "redis://localhost:6379/0"
        # Gemini key aliases
        if not self.GOOGLE_API_KEY and self.gemini_api_key:
            self.GOOGLE_API_KEY = self.gemini_api_key
        if not self.GOOGLE_API_KEY and self.GEMINI_API_KEY:
            self.GOOGLE_API_KEY = self.GEMINI_API_KEY
        return self

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split() if o.strip()]


settings = Settings()
