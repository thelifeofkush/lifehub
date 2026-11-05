# 🧭 LifeHub

A self-hosted home for small "life tracking" apps. One Docker container serves a
dashboard; every folder you drop into `apps/` becomes a new tracker automatically.

- **Stack:** Python · FastAPI · Jinja2 · SQLite (no JS build step; optional Plaid bank sync)
- **Data:** one SQLite file at `./data/lifehub.db` (mounted volume — back it up)
- **Included apps:** Habits, Journal, Money (income and expenses), and a Duncan planner launcher

## Run it

```bash
docker compose up -d --build
```

Open <http://localhost:8000>. Stop with `docker compose down` (data is kept in `./data`).

Install and start Docker Desktop first (Linux containers). The default port is
bound to `127.0.0.1`, so only this computer can access it. For a home server,
change the mapping to `"8000:8000"` to allow your LAN to connect.

Duncan opens your existing hosted planner in a new tab. It does not sync or
migrate planner data into the local database. The other three apps store data locally.

> **Security:** set `LIFEHUB_USERNAME` and `LIFEHUB_PASSWORD` to enable the
> single-owner login. Login is required when bank sync is configured or bank
> connections exist. Keep it on your own machine/network. To make it
> reachable only from the computer it runs on, keep the default port mapping in
> `docker-compose.yml` as `"127.0.0.1:8000:8000"`. If you expose it beyond your LAN,
> put it behind a reverse proxy with authentication (e.g. Caddy/Traefik + basic auth,
> Tailscale, or Cloudflare Access).

## Automatic bank sync and income

The **Money** app supports monthly income, spending after refunds, transfers,
and optional Plaid automatic sync. It includes category doughnut charts, monthly
purchase comparisons, per-credit-card breakdowns, and daily saved balance history.
Categories are automatic with editable overrides. Balance history begins when
the first snapshot is saved and survives restarts. Existing expense entries are preserved.
Follow the [Bank of America setup guide](docs/bank-sync.md) to create a Plaid
Trial account, configure server secrets, test Sandbox, and connect your real bank.
Plaid's free Trial supports Bank of America and Transactions with up to 10
bank-login connections. It uses `PLAID_ENV=production`; a paid plan is not
required for this setup. See the guide for eligibility and connection limits.

## Add a new app

```bash
cp -r apps/_template apps/sleep
mv apps/sleep/templates/_template apps/sleep/templates/sleep
```

Then in `apps/sleep/`:

1. `__init__.py` — set `manifest` (name, icon, description), change `SLUG = "sleep"`,
   write your `init_db` (tables prefixed `sleep_`) and your routes.
2. `templates/sleep/index.html` — your page. It extends `base.html`, so the nav and
   styling come for free. Replace `/myapp/` links with `/sleep/`.
3. Rebuild: `docker compose up -d --build` (or use dev mode below).

That's it — no registration step. The app appears in the nav and home page.

Use lowercase folder names starting with a letter, followed by letters, digits,
or underscores. Folders beginning with `_` are ignored. Treat app folders as
trusted server code: every app can access the shared database.

PowerShell equivalent:

```powershell
Copy-Item apps/_template apps/sleep -Recurse
Rename-Item apps/sleep/templates/_template sleep
```

### The app contract

| Thing | Required | Notes |
|---|---|---|
| `apps/<slug>/__init__.py` | yes | Folder name = URL prefix |
| `manifest = {name, icon, description}` | yes | Shown in nav/home |
| `router = APIRouter()` | yes | Mounted at `/<slug>` |
| `init_db(conn)` | no | Called on startup; use `CREATE TABLE IF NOT EXISTS` |
| Templates at `templates/<slug>/*.html` | — | Referenced as `"<slug>/file.html"` |

Helpers: `from core.db import db` (`with db() as c:` auto-commits) and
`from core.web import render, redirect`. A broken app is logged and skipped; it
won't take the rest down.

## Development

Hot reload: uncomment the two volume lines and the `command:` line in
`docker-compose.yml`, then `docker compose up --build`.

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn core.main:app --reload
```

On Windows, activate with `.venv\Scripts\Activate.ps1` instead of `source`.
For tests, install `requirements-dev.txt` and run
`python -m unittest discover -s tests -v`.

### Backups and hosting

Stop the container before copying `data/lifehub.db` for a consistent backup.
Restore by stopping LifeHub, replacing that file, and starting it again.
Never commit the database or personal data to GitHub.

This repository targets Docker on your computer, a home server, or a VPS.
It needs a persistent writable `./data` volume. A static website host cannot
run this Python/SQLite application. For internet hosting, configure an
authenticated HTTPS reverse proxy before exposing it.

## Project layout

```
core/            # platform: server, db helper, app discovery, base layout, CSS
apps/
  _template/     # copy me to start a new app
  habits/ journal/ expenses/
data/            # created at runtime (gitignored)
Dockerfile  docker-compose.yml  requirements.txt
```

## Ideas for next apps

Sleep, workouts, weight/body metrics, reading list, medication, mood check-ins,
gratitude log, goals/OKRs, time tracking, subscriptions, meal log, contacts to keep in touch with.
