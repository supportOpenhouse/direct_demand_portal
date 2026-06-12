# Deployment — Direct Demand Portal

Frontend → **Vercel** · API + scheduler → **Render** · DB → **Neon Postgres**.

## 1. Neon (database)

1. Create a Neon project (region close to users, e.g. `ap-southeast-1`).
2. Use the `main` branch for production; create a `dev` branch for local/dev work.
3. Copy the **direct (unpooled)** connection string and convert the scheme for asyncpg:
   `postgresql+asyncpg://USER:PASSWORD@HOST/dbname?ssl=require`
   (The API keeps a small pool — 5+5 — well within Neon limits. If the API ever scales
   past one instance, switch to the `-pooler` host; see notes in `backend/app/db.py`.)
4. First-time setup runs automatically on Render deploy (`alembic upgrade head` is the
   pre-deploy command). To seed demo data once:
   `DATABASE_URL=... uv run python -m app.seed` from `backend` (idempotent).

## 2. Google OAuth (login)

1. Google Cloud console → APIs & Services → Credentials → **Create OAuth client ID** (Web application).
2. Authorized JavaScript origins: `http://localhost:5173` and your Vercel domain(s)
   (`https://<project>.vercel.app`, plus any custom domain).
3. No redirect URIs needed (Google Identity Services button flow).
4. Put the client ID in BOTH places:
   - Render env `GOOGLE_CLIENT_ID`
   - Vercel env `VITE_GOOGLE_CLIENT_ID`
5. Only emails present in the `users` table can log in (role comes from the table —
   edit `users.role` to grant admin/cm/rm). The seed provisions `support@openhouse.in` as admin.

## 3. Render (API)

1. New → Blueprint → point at this repo; `render.yaml` defines the `direct-demand-api` service
   (rootDir `backend`, uv build, Alembic pre-deploy, uvicorn start).
2. Fill the `sync: false` env vars: `DATABASE_URL` (Neon, asyncpg scheme), `GOOGLE_CLIENT_ID`,
   `CORS_ORIGINS` (your exact Vercel URL, comma-separated for several).
   `JWT_SECRET` is generated; `CORS_ORIGIN_REGEX` already allows `*.vercel.app` previews;
   `RUN_SCHEDULER=true` runs the TAT/reminder/goldmine jobs in-process.
3. Plan: **Starter** (free tier spin-down pauses the scheduler).
4. Health check: `GET /docs` (or add a `/healthz` route later).
5. Scaling past one instance: enable the commented-out worker block in `render.yaml`
   and set `RUN_SCHEDULER=false` on the web service.

## 4. Vercel (frontend)

1. New project → import repo → **Root Directory: `frontend`** → framework preset Vite
   (build `pnpm build`, output `dist` — auto-detected; `frontend/vercel.json` provides the SPA rewrite).
2. Env vars:
   - `VITE_API_URL` = `https://direct-demand-api.onrender.com` (no trailing slash)
   - `VITE_GOOGLE_CLIENT_ID` = OAuth client ID
   - `VITE_MAPS_API_KEY` = optional; without it the visit planner uses estimates + a map placeholder.
     With it (Maps JavaScript API enabled, billing on) the live map renders.

## 5. Production go-live checklist

The API **refuses to start** with `ENV=production` (set in render.yaml) unless all of
these hold — so a misconfigured deploy fails loudly instead of running insecurely:

- `DEV_LOGIN_ENABLED` unset/false (password-less login must never reach prod)
- `JWT_SECRET` is a random secret of 32+ chars (Render's "Generate" satisfies this)
- `GOOGLE_CLIENT_ID` is set (the only login path in prod)
- `DATABASE_URL` is Postgres, not SQLite

**Users = login allowlist.** Only emails in the `users` table (active=true) can sign in
with Google; the row's `role` (admin/cm/rm) controls what they see. Manage it without SQL
from `backend/`:

```bash
uv run python -m app.add_user list
uv run python -m app.add_user add rahul@openhouse.in "Rahul Verma" rm --team "Team Gurgaon"
uv run python -m app.add_user add priya@openhouse.in "Priya Nair" cm --team "Team Gurgaon"
uv run python -m app.add_user deactivate rm3@openhouse.in
```

(Admins can also POST /v1/users via the API docs.)

**Clearing demo data.** The seed loads fake leads/inventory and demo logins for evaluation.
Before real traffic, from `backend/` with the prod `DATABASE_URL`:

```bash
uv run python -m app.purge_demo --yes --remove-demo-users
```

Keeps users/teams/societies/localities/settings; always keeps `support@openhouse.in`.
Then add your real team with `add_user` above.

## 6. Smoke test after deploy

1. `curl -X POST https://<render>/v1/auth/dev-login` → must be **404** (dev login disabled in prod).
2. Log in on the Vercel URL with a provisioned Google account.
3. `POST /v1/leads/ingest` with a JSON body → lead appears in New Leads with a TAT chip,
   assigned to an RM, activity logged.
4. Watch Render logs for `tat_sweep` / `reminders_due` scheduler lines (every 5 min).

## Local development (no Postgres needed)

```bash
# api — SQLite + seeded data
cd backend && cp .env.example .env
uv sync && uv run python -m app.devdb
uv run uvicorn app.main:app --reload --port 8000

# web
cd frontend && cp .env.example .env   # VITE_API_URL=http://localhost:8000
pnpm install && pnpm dev              # http://localhost:5173
```

`DEV_LOGIN_ENABLED=true` (in `backend/.env.example`) exposes quick logins on the login
page for `support@openhouse.in` / `admin@` / `cm@` / `rm1@openhouse.in` — never set it in prod.
