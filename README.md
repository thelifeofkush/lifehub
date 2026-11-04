# 🧭 LifeHub

A self-hosted home for small "life tracking" apps. One Docker container serves a
dashboard; every folder you drop into `apps/` becomes a new tracker automatically.

- **Stack:** Python · FastAPI · Jinja2 · SQLite (no JS build step, no external services)
- **Data:** one SQLite file at `./data/lifehub.db` (mounted volume — back it up)
- **Included apps:** Habits, Journal, Expenses

## Run it

```bash
docker compose up -d --build
```

Open <http://localhost:8000>. Stop with `docker compose down` (data is kept in `./data`).

> **Security:** there is no login. Keep it on your own machine/network. To make it
> reachable only from the computer it runs on, change the port mapping in
> `docker-compose.yml` to `"127.0.0.1:8000:8000"`. If you expose it beyond your LAN,
> put it behind a reverse proxy with authentication (e.g. Caddy/Traefik + basic auth,
> Tailscale, or Cloudflare Access).

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
