#!/usr/bin/env python3
"""Interactive Zero-Friction Supabase Setup Wizard for AUREN.

Automates:
1. Collecting Supabase Project URL and anon key.
2. Automatically writing backend/.env and frontend/.env.
3. Optionally connecting to PostgreSQL to deploy all 24 database migrations automatically.
"""

import asyncio
import getpass
import os
from pathlib import Path
import re
import sys
import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
SCHEMA_FILE = REPO_ROOT / "supabase" / "schema_deploy.sql"


async def verify_supabase_api(url: str, anon_key: str) -> bool:
    clean_url = url.strip().rstrip("/")
    jwks_url = f"{clean_url}/auth/v1/.well-known/jwks.json"
    print(f"\n[1/3] Verifying connection to {clean_url}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(jwks_url)
            if res.status_code == 200:
                print("  ✓ Supabase Auth JWKS endpoint reachable.")
                return True
            else:
                print(f"  ⚠ Warning: JWKS endpoint returned status {res.status_code}.")
                return False
    except Exception as exc:
        print(f"  ✗ Connection error: {exc}")
        return False


async def apply_migrations(db_url: str) -> bool:
    print("\n[2/3] Connecting to PostgreSQL to apply migrations...")
    try:
        import asyncpg
    except ImportError:
        print("  ✗ asyncpg not found. Skipping direct database migration.")
        return False

    if not SCHEMA_FILE.exists():
        print(f"  ✗ Schema file {SCHEMA_FILE} not found.")
        return False

    sql_content = SCHEMA_FILE.read_text(encoding="utf-8")
    try:
        conn = await asyncpg.connect(db_url, timeout=15)
        print("  ✓ Connected to Supabase PostgreSQL database.")
        print("  -> Applying consolidated schema migrations (this may take 5-10s)...")
        await conn.execute(sql_content)
        await conn.close()
        print("  ✓ All tables, RLS policies, and RPC functions deployed successfully!")
        return True
    except Exception as exc:
        print(f"  ✗ Database migration warning: {exc}")
        print("  (You can also paste supabase/schema_deploy.sql in the Supabase SQL Editor).")
        return False


def write_env_files(url: str, anon_key: str, db_url: str = ""):
    print("\n[3/3] Writing environment configuration files...")
    clean_url = url.strip().rstrip("/")
    clean_anon = anon_key.strip()

    # Pre-generate secure 256-bit HMAC secret if not present
    import secrets
    hmac_secret = secrets.token_urlsafe(32)

    backend_env = f"""# AUREN Backend Staging Configuration
ENVIRONMENT=development
PORT=8000
HOST=0.0.0.0
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173", "https://frontend-alpha-steel-64.vercel.app"]

# Supabase Configuration
SUPABASE_URL={clean_url}
SUPABASE_ANON_KEY={clean_anon}
CHAT_REPOSITORY_TYPE=auto

# Memory Background Worker Database Connection
WORKER_DATABASE_URL={db_url}

# AI Provider Configuration (Default: Gemini)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash

# Private Journal HMAC Secret
JOURNAL_HMAC_SECRET={hmac_secret}
"""

    frontend_env = f"""# AUREN Frontend Staging Configuration
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_SUPABASE_URL={clean_url}
VITE_SUPABASE_ANON_KEY={clean_anon}
"""

    (BACKEND_DIR / ".env").write_text(backend_env, encoding="utf-8")
    (FRONTEND_DIR / ".env").write_text(frontend_env, encoding="utf-8")

    print(f"  ✓ Written: {BACKEND_DIR / '.env'}")
    print(f"  ✓ Written: {FRONTEND_DIR / '.env'}")


async def main():
    print("=" * 65)
    print("         AUREN — Interactive Supabase Setup Wizard")
    print("=" * 65)
    print("\nYou only need your Project URL and anon public key from Supabase.\n")

    # 1. Project URL
    url = input("1. Enter Supabase Project URL (e.g. https://xyzcompany.supabase.co): ").strip()
    while not url.startswith("https://") or "supabase.co" not in url:
        print("   Please enter a valid Supabase URL starting with https:// and ending with .supabase.co")
        url = input("1. Enter Supabase Project URL: ").strip()

    # 2. Anon Key
    anon_key = input("\n2. Enter Supabase 'anon' 'public' API Key: ").strip()
    while len(anon_key) < 20:
        print("   The anon key is usually a long string starting with 'eyJ...'")
        anon_key = input("2. Enter Supabase 'anon' API Key: ").strip()

    # 3. Database Password (optional)
    ref_match = re.search(r"https://([a-zA-Z0-9_-]+)\.supabase\.co", url)
    project_ref = ref_match.group(1) if ref_match else ""

    print("\n3. Database Password (OPTIONAL - to auto-deploy tables):")
    print("   Press ENTER to skip if you prefer using the Supabase SQL Editor.")
    db_password = getpass.getpass("   Database Password: ").strip()

    db_url = ""
    if db_password and project_ref:
        # Default Supabase direct connection string
        db_url = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"

    # Verify API
    await verify_supabase_api(url, anon_key)

    # Apply migrations if DB password provided
    if db_url:
        await apply_migrations(db_url)

    # Write files
    write_env_files(url, anon_key, db_url)

    print("\n" + "=" * 65)
    print("  ✓ Setup Complete! AUREN is now configured for your Supabase project.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())

