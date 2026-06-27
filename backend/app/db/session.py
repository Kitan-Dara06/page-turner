import socket
from typing import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# --- Resolve host to IPv4 for Supabase ---
# Supabase pooler and direct hosts resolve to both IPv4 and IPv6.
# On networks without IPv6, psycopg2 tries the IPv6 address first
# and fails with "Network is unreachable".
# We resolve the hostname here, pass the IPv4 address as hostaddr
# (TCP connection target), and keep the hostname for SNI (tenant id).
_connect_args = {
    "sslmode": "require",
    "connect_timeout": 10,
    "options": "-c statement_timeout=10000",
}

_uri = settings.DATABASE_URI
try:
    _parsed = urlparse(_uri)
    if _parsed.hostname and "supabase" in _parsed.hostname:
        _addrs = socket.getaddrinfo(
            _parsed.hostname, _parsed.port or 5432, socket.AF_INET
        )
        if _addrs:
            _connect_args["hostaddr"] = _addrs[0][4][0]
            if _parsed.port:
                _connect_args["port"] = _parsed.port
except Exception:
    pass

engine = create_engine(
    _uri,
    pool_pre_ping=True,
    pool_timeout=15,
    pool_recycle=300,
    pool_size=10,
    max_overflow=20,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
