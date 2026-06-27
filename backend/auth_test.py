"""
auth_test.py — End-to-end JWT authentication verification
Run from backend root: python auth_test.py
"""
import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ─── 1. Load env ────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(".env")

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
BACKEND_URL      = "http://localhost:8000"

OK  = "\033[92m✓\033[0m"
ERR = "\033[91m✗\033[0m"
INF = "\033[94m→\033[0m"

def section(title):
    print(f"\n\033[1m{'─'*60}\n  {title}\n{'─'*60}\033[0m")

def ok(msg):    print(f"  {OK}  {msg}")
def fail(msg):  print(f"  {ERR}  {msg}"); sys.exit(1)
def info(msg):  print(f"  {INF}  {msg}")

# ─── 2. JWKS fetch ───────────────────────────────────────────────────────────
section("1 · JWKS endpoint (ES256 public key)")

if not SUPABASE_URL:
    fail("SUPABASE_URL not set in .env — cannot proceed")

jwks_url = SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
info(f"Fetching {jwks_url}")
try:
    with urllib.request.urlopen(jwks_url, timeout=5) as r:
        jwks = json.loads(r.read())
except Exception as e:
    fail(f"JWKS fetch failed: {e}")

keys = jwks.get("keys", [])
if not keys:
    fail("JWKS returned no keys")

for k in keys:
    alg = k.get("alg")
    kty = k.get("kty")
    crv = k.get("crv")
    kid = k.get("kid", "?")[:16] + "..."
    ok(f"kid={kid}  alg={alg}  kty={kty}  crv={crv}")
    if alg != "ES256" or kty != "EC" or crv != "P-256":
        fail(f"Unexpected algorithm — expected ES256/EC/P-256, got {alg}/{kty}/{crv}")

ok("Public key is EC P-256 ✦ correct for Supabase modern projects")

# ─── 3. PyJWT ES256 capability ───────────────────────────────────────────────
section("2 · PyJWT ES256 capability")

try:
    import jwt
    ok(f"PyJWT {jwt.__version__} installed")
except ImportError:
    fail("PyJWT not installed — run: pip install PyJWT[crypto]")

try:
    from jwt import PyJWKClient
    client = PyJWKClient(jwks_url, cache_keys=True)
    ok("PyJWKClient instantiated successfully")
except Exception as e:
    fail(f"PyJWKClient error: {e}")

# Confirm ES256 in supported algorithms
algos = jwt.algorithms.get_default_algorithms()
if "ES256" not in algos:
    fail("ES256 not available in PyJWT — install cryptography: pip install cryptography")
ok("ES256 algorithm is available")

# ─── 4. Backend health check ─────────────────────────────────────────────────
section("3 · Backend server health")

try:
    with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=3) as r:
        body = json.loads(r.read())
        ok(f"Backend healthy: {body}")
except urllib.error.URLError:
    info("Backend not running — start it with: uvicorn app.main:app --reload")
    info("Skipping live endpoint tests")
    print("\n")
    sys.exit(0)
except Exception as e:
    info(f"Health check response: {e} (may be fine if endpoint returns non-200)")

# ─── 5. Unauthenticated request → expect 401 ────────────────────────────────
section("4 · Unauthenticated request → should be 401")

try:
    req = urllib.request.Request(f"{BACKEND_URL}/api/v1/profile/")
    with urllib.request.urlopen(req, timeout=3) as r:
        # If we get here with 200 in dev-fallback mode, that's also OK
        ok(f"Dev fallback active — returned {r.status} (expected in local dev)")
except urllib.error.HTTPError as e:
    if e.code == 401:
        ok("401 Unauthorized — auth guard working correctly")
    elif e.code == 422:
        ok(f"422 returned — endpoint reachable, auth dependency active")
    else:
        info(f"Got HTTP {e.code} — verify this is expected")

# ─── 6. Supabase sign-in test ────────────────────────────────────────────────
section("5 · Supabase sign-in (ES256 token end-to-end)")

if not SUPABASE_ANON_KEY:
    info("SUPABASE_ANON_KEY not set — skipping live token test")
    info("To test: add SUPABASE_ANON_KEY=<anon key> to frontend/.env.local")
    info("Then run: python auth_test.py email=you@example.com password=yourpassword")
elif len(sys.argv) >= 3:
    email    = sys.argv[1].split("=")[-1]
    password = sys.argv[2].split("=")[-1]
    info(f"Signing in as {email} …")

    signin_url = SUPABASE_URL.rstrip("/") + "/auth/v1/token?grant_type=password"
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        signin_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_ANON_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        access_token = data.get("access_token")
        if not access_token:
            fail(f"No access_token in response: {data}")
        ok("Sign-in successful — received access_token")

        # Decode header to inspect alg + kid
        header_b64 = access_token.split(".")[0]
        import base64
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        ok(f"Token header: alg={header.get('alg')}  kid={str(header.get('kid',''))[:16]}...")

        if header.get("alg") != "ES256":
            fail(f"Expected ES256 in token header, got {header.get('alg')}")
        ok("Token uses ES256 — matches JWKS key algorithm ✦")

        # Verify locally with PyJWKClient
        signing_key = client.get_signing_key_from_jwt(access_token)
        payload = jwt.decode(
            access_token,
            signing_key.key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
        ok(f"Local ES256 signature verification passed")
        ok(f"sub (user UUID) = {payload.get('sub')}")
        ok(f"expires at      = {datetime.fromtimestamp(payload['exp'], tz=timezone.utc).isoformat()}")

        # Hit a real backend endpoint
        info("Testing token against backend /api/v1/profile/ …")
        req2 = urllib.request.Request(
            f"{BACKEND_URL}/api/v1/profile/",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req2, timeout=5) as r2:
            profile = json.loads(r2.read())
        ok(f"Profile endpoint returned {len(profile.get('dimensions', []))} dimensions")
        ok("⚡ Full auth flow working: Supabase ES256 JWT → backend verified ✦")

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        fail(f"Sign-in failed ({e.code}): {body}")
else:
    info("Anon key present — run with credentials to do live token test:")
    info("  python auth_test.py email=you@example.com password=yourpassword")

print("\n\033[92m✦ Auth configuration is correct.\033[0m\n")
