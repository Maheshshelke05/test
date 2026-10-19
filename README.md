# CampusBite — local MVP

College food ordering and canteen management, built from
`CampusBite_Complete_MVP_Product_Technical_Plan.pdf`.

| Part | Path | Stack | Local URL |
|---|---|---|---|
| API + worker | `backend/` | FastAPI, SQLAlchemy 2, SQLite or Postgres, optional Redis | http://localhost:8000/docs |
| Student app | `apps/student/` | Expo SDK 58 / React Native | Expo Go, or web on :8081 |
| Kitchen app | `apps/kitchen/` | Expo SDK 58 / React Native | Expo Go, or web on :8082 |
| Admin console | `apps/admin/` | React + Vite | http://localhost:3000 |

## Quick start (Windows)

```powershell
.\start-local.ps1            # first run installs everything and seeds demo data
.\start-local.ps1 -Reseed    # wipe and reseed
```

### Manual start

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/...
.venv/Scripts/python seed.py
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

cd apps/admin   && npm install && npm run dev            # :3000
cd apps/student && npm install && npx expo start         # press w for web, or scan QR
cd apps/kitchen && npm install && npx expo start --port 8082
```

On a physical phone, the apps reach the API at the dev machine's LAN IP, which they read from Metro.
To override it, set `EXPO_PUBLIC_API_URL=http://<your-ip>:8000`. Allow port 8000 through Windows Firewall.

## Deploying to a server (Ubuntu)

One command from Git Bash (Windows), macOS or Linux builds the three web apps and installs everything on a fresh Ubuntu server: PostgreSQL, Redis, Nginx, the API (2 workers) and a background worker as systemd services, plus daily database backups.

```bash
SERVER=ubuntu@3.110.189.207 SSH_KEY=~/Downloads/test.pem ./deploy/deploy.sh
```

| URL | What |
|---|---|
| `http://<server>/` | Student app |
| `http://<server>/kitchen/` | Kitchen app |
| `http://<server>/admin/` | Admin console |
| `http://<server>/docs` | API docs |

- Run the same command for every release. The database, secrets and uploaded data are kept, and demo data is loaded only into an empty database.
- Secrets are generated on the server, in `/opt/campusbite/backend/.env` (mode 600).
- No SMS provider is wired in yet, so everyone logs in with the **pilot OTP** stored as `OTP_FIXED_CODE` in that file. The script prints it at the end. Share it only with pilot users. The public dev code `123456` does not work in production.
- HTTPS: point a domain at the server, then run `DOMAIN=food.example.com CERTBOT_EMAIL=you@example.com SERVER=... ./deploy/deploy.sh`. Camera QR scanning and location in mobile browsers need HTTPS. Over plain HTTP, kitchen staff type the pickup code instead.
- The EC2 security group must allow inbound TCP 80 (and 443 for HTTPS).
- Logs: `journalctl -u campusbite-api -u campusbite-worker -f`. Backups: `/var/backups/campusbite/` (kept 14 days).
- `BUILD_ONLY=1 PUBLIC_URL=http://localhost:8300 ./deploy/deploy.sh` builds the release into `deploy/.release/` without uploading.

### Postgres + Redis (Docker)

```bash
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api python seed.py
```

Or run only `db redis` from compose and point `backend/.env` at them (see `.env.example`).

## Demo accounts (OTP is always `123456` in local mode)

| Role | Phone |
|---|---|
| Super admin | 9000000000 |
| College admin (North Campus only) | 9000000001 |
| Kitchen owner / cashier / cook, kitchen *n* = 1…9 | 910000000*n* / 920000000*n* / 930000000*n* |
| Owner of the pending kitchen "Biryani Bros" | 9100000010 |
| Student Aarav (North Campus: kitchens 1–3) | 9800000001 |
| Other students | 9800000002 … 9800000030 |

The seed creates 3 colleges, 9 approved kitchens and 1 pending kitchen, 180 dishes, and 200 historical orders.
Kitchen 8 (Desi Thali House) is paused, so you can see the closed state.
Cheese Maggi at Campus Canteen has 20 portions, which matches the pilot walkthrough in §22.

## What's implemented (PRD mapping)

- **Auth (§03)**: phone OTP (deterministic in local mode, rate-limited, attempt-limited), rotating refresh tokens, server-side revocation. Tokens use SecureStore on devices. An expired access token is renewed silently, and parallel requests share one refresh, because refresh tokens are single-use. Starting the app without internet shows a retry screen instead of logging the user out.
- **Scope enforcement (§02, §14)**: every route checks role and kitchen/college membership on the server. Roles are re-read on every request, so removing a staff member takes effect immediately. Out-of-scope reads return 404.
- **Student app (§03–04)**: onboarding, profile, college picker (search, plus optional browser location), home, kitchens with filters, typo-tolerant dish search, kitchen menu with category tabs, variant/add-on sheet, favourites, one-kitchen cart with a server quote, pay-at-counter or sandbox UPI/card, live tracking timeline, rotating QR + 6-digit pickup code, cancel, rating, reorder at current prices, support tickets, notification inbox.
- **Kitchen app (§05)**: registration and approval gate, live queue (New/Accepted/Preparing/Ready/Done) with a chime and vibration, accept with ETA, reject with reason, role-based actions (cashier vs cook), pickup verification, accepting/busy toggles, menu CRUD with add-ons, stock and sold-out, staff invites and removal, hours/settings, sales report (GMV, commission, net payout, p50/p90 prep time, peak hours, top items).
- **Admin console (§06)**: dashboard, live orders with filters and a detail drawer (history, payments, refunds, cancel and refund), kitchen moderation, colleges, users (flag/suspend), payments and refunds, per-kitchen report and CSV export, support, audit log, feature flags.
- **Order integrity (§09–10)**: fulfilment state and payment state are separate; transitions are validated against a state machine with an optimistic `version` check; idempotency keys on order creation; atomic conditional stock decrement, so the last portion is sold exactly once; immutable order-item snapshots in integer paise; stock is released on reject/cancel/expiry.
- **Payments**: a mock gateway emits HMAC-signed webhook events through the same handler a live provider would use. Events are deduplicated by event id. Refunds go INITIATED → SUCCEEDED and are settled by the worker.
- **Pickup**: the code is derived from a server secret and a per-order nonce. Only its hash is compared. It expires, locks after 5 wrong tries, rotates when the student reopens it, and is consumed atomically.
- **Realtime (§12)**: a WebSocket with user, kitchen and admin rooms. Clients authenticate with their first message, `{"type": "auth", "token": ...}`, so access tokens never appear in URLs or access logs. Events are published only after the DB commit (in-process, or Redis pub/sub when `REDIS_URL` is set). Clients refetch over REST on every event or reconnect, and also poll as a fallback.
- **Worker**: expires unpaid online orders after 15 minutes, settles refunds, and flags orders the kitchen hasn't accepted within 10 minutes.

## Tests

### Backend (API, business rules, worker)

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

### Browser end-to-end (all three apps, like a real user)

`e2e/` (36 tests) drives the real Student, Kitchen and Admin web builds in Microsoft Edge with Playwright: sign-up, ordering, live kitchen queue, pickup (typed code, QR payload, and a real camera QR scan using a fake video), menu editing, staff, hours, admin moderation, refunds, CSV export, feature flags and more.
It builds the apps, seeds its own database (`e2e/.build/e2e.db`), and runs on ports 8100/8181/8182/8130, so it never touches your dev data or servers.

```bash
backend/.venv/Scripts/pip install -r e2e/requirements.txt
backend/.venv/Scripts/python -m pytest e2e -q                  # build + run (a few minutes)
E2E_SKIP_BUILD=1 backend/.venv/Scripts/python -m pytest e2e -q # reuse the last build
E2E_HEADED=1 ...                                               # watch it click through
```

Screenshots of failures go to `e2e/.build/shots/`, and API logs to `e2e/.build/api.log`.
Use `E2E_CHANNEL=chrome` for Google Chrome, or `playwright install chromium` with `E2E_CHANNEL=chromium`.

42 tests. `test_mvp.py` covers the §15 QA matrix: the full pilot walkthrough, a last-item race between two buyers, a double-tapped checkout, a repeated and forged webhook, wrong and locked pickup codes, cross-college and cross-kitchen denial, a price change before checkout, reject → refund → stock restore, a stale version conflict, a closed kitchen and sold-out items, add-on pricing, registration → approval with college-admin scoping, immediate staff revocation, unpaid-order expiry, OTP limits, typo search, WebSocket delivery, and weekly hours with holiday closures. `test_more.py` covers sessions (refresh rotation, logout, suspension), staff permissions, menu add-ons and order snapshots, reports, worker flags, late payments, admin moderation, scoping, CSV export, support tickets and feature flags.

## Database migrations (Alembic)

The schema lives in `backend/migrations/`. The API applies pending migrations on startup, and `seed.py` builds the schema from them.
After you change `app/models.py`:

```bash
cd backend
.venv/Scripts/alembic revision --autogenerate -m "describe the change"
.venv/Scripts/alembic upgrade head      # or just restart the API
.venv/Scripts/alembic check             # confirms models and migrations match
```

## Opening hours

Kitchen owners set a weekly schedule (closed days, and windows past midnight such as 18:00–02:00) and one-off closed days (holiday, exam day, festival) under **More → Hours & settings**.
Students see "Closed today" with the reason and the next opening time, and ordering is blocked server-side.

## Known gaps / next steps

- Kitchen pickup has a camera QR scanner (`expo-camera`) plus manual code entry. Camera scanning needs a real device or a webcam; it was not exercised in automated tests.
- Scheduled pickup slots are not built yet. The `scheduled_pickup` flag is reserved.
- No live SMS or payment provider: the OTP and the gateway are stubs behind the same interfaces.
- No admin MFA. Push notifications are an in-app inbox plus realtime toasts.
- The backend suite passes on both SQLite and PostgreSQL (`TEST_DATABASE_URL=postgresql+psycopg://... pytest`). Redis fan-out is covered with fakeredis, and the production stack (Nginx + PostgreSQL + worker + pilot OTP) was exercised end to end in a browser.
