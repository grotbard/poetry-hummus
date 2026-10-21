#!/usr/bin/env bash
# Sets up the Poetry Hummus club app for local development:
# backend venv + dependencies, frontend node_modules, and a .env to edit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Python: pydantic-core has no wheels for very new interpreters, so pick a
# version we know builds, newest first within the supported range.
# ---------------------------------------------------------------------------
bold "1/4  Locating a supported Python (3.11-3.13)"
PYTHON=""
for candidate in python3.13 python3.12 python3.11; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  # Fall back to `python3` only if its version is in range.
  if command -v python3 >/dev/null 2>&1 \
     && python3 -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info < (3,14) else 1)' 2>/dev/null; then
    PYTHON="$(command -v python3)"
  else
    die "Need Python 3.11-3.13. Install one, e.g.: brew install python@3.13"
  fi
fi
ok "using $PYTHON ($("$PYTHON" --version 2>&1))"

# ---------------------------------------------------------------------------
bold "2/4  Backend virtualenv and dependencies"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
  ok "created backend/.venv"
else
  ok "backend/.venv already exists"
fi

./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements-dev.txt
ok "installed Python dependencies (FastAPI, SQLAlchemy, Alembic, asyncpg)"

# ---------------------------------------------------------------------------
bold "3/4  Environment file"
if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a real signing key so sessions aren't signed with the sample value.
  SECRET="$(./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
  else
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
  fi
  ok "created backend/.env with a generated SECRET_KEY"
  warn "still to fill in: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BOOTSTRAP_ADMIN_PASSWORD"
else
  ok "backend/.env already exists (left untouched)"
fi

# ---------------------------------------------------------------------------
bold "4/4  Frontend dependencies"
cd "$ROOT/frontend"
command -v npm >/dev/null 2>&1 || die "npm not found. Install Node.js 20+ first."
if [ -f package-lock.json ]; then
  npm ci --silent --no-fund --no-audit
else
  npm install --silent --no-fund --no-audit
fi
ok "installed frontend dependencies (React, Vite, Tailwind)"

# ---------------------------------------------------------------------------
cd "$ROOT"
cat <<'NEXT'

Setup complete. Next steps:

  1. Edit backend/.env — Google OAuth credentials and an admin password.
     See docs/SETUP.md for how to create the Google OAuth client.

  2. Start Postgres (listens on 5433 to avoid clashing with a local install):
       docker compose up -d db
     Then point backend/.env at it:
       DATABASE_URL=postgresql+asyncpg://poet:poet@localhost:5433/poetry_hummus

  3. Run the two dev servers in separate terminals:
       cd backend  && .venv/bin/uvicorn app.main:app --reload
       cd frontend && npm run dev

     web  → http://localhost:5173
     api  → http://localhost:8000/docs

  Or skip all of the above and run everything in containers:
       docker compose up --build

  Tests:
       cd backend  && .venv/bin/python -m pytest -q
       cd frontend && npm run typecheck

NEXT
