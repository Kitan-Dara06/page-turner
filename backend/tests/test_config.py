"""
Tests for app.config — validates all environment variables are wired correctly
and the LLM provider defaults to Google Gemini.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


class TestConfigLoading:
    """Verify every .env key resolves without error."""

    def test_database_uri_is_set(self):
        """DATABASE_URI must be set for the app to boot."""
        from app.config import settings

        assert settings.DATABASE_URI is not None
        assert settings.DATABASE_URI.startswith("postgresql")

    def test_redis_url_resolves(self):
        """REDIS_URL is computed from Upstash env vars or falls back to localhost."""
        from app.config import settings

        assert settings.REDIS_URL is not None
        assert settings.REDIS_URL.startswith("redis://")

    def test_upstash_vars_construct_redis_url(self):
        """When UPSTASH vars are provided, they construct the Redis URL."""
        from app.config import Settings

        s = Settings(
            DATABASE_URI="postgresql://u:p@localhost:5432/test",
            UPSTASH_REDIS_REST_URL="https://valid-host.upstash.io",
            UPSTASH_REDIS_REST_TOKEN="test-token-123",
            UPSTASH_PORT=6379,
        )
        assert (
            s.REDIS_URL == "redis://default:test-token-123@valid-host.upstash.io:6379"
        )

    def test_redis_fallback_to_localhost(self):
        """When no Upstash vars are set, fall back to localhost Redis."""
        from app.config import Settings

        s = Settings(
            DATABASE_URI="postgresql://u:p@localhost:5432/test",
            UPSTASH_REDIS_REST_URL="",
            UPSTASH_REDIS_REST_TOKEN="",
        )
        assert s.REDIS_URL == "redis://localhost:6379/0"

    def test_qdrant_url_defaults(self):
        """Qdrant defaults to localhost when not configured."""
        from app.config import settings

        assert settings.QDRANT_URL is not None

    def test_llm_provider_defaults_to_google(self):
        """LLM_PROVIDER defaults to 'google' for Gemini."""
        from app.config import Settings

        s = Settings(DATABASE_URI="postgresql://u:p@localhost:5432/test")
        assert s.LLM_PROVIDER == "google"

    def test_reddit_unavailable(self):
        """REDDIT_AVAILABLE is hardcoded to False."""
        from app.config import settings

        assert settings.REDDIT_AVAILABLE is False

    def test_all_optional_keys_can_be_none(self):
        """Optional API keys can be None without crashing."""
        from app.config import Settings

        s = Settings(
            DATABASE_URI="postgresql://u:p@localhost:5432/test",
            TAVILY_API_KEY=None,
            UPSTASH_REDIS_REST_URL="",
            UPSTASH_REDIS_REST_TOKEN="",
        )
        assert s.ANTHROPIC_API_KEY is None
        assert s.GOOGLE_API_KEY is None
        assert s.TAVILY_API_KEY is None
        assert s.QDRANT_API_KEY is None
