# ΑΣΕΠ 2027 — Τράπεζα Θεμάτων (web app)

Flask web app for studying the 2026 ASEP question bank (1988 questions, 11
categories): random quizzes and full browsing for everyone; per-user progress
(stats, "wrong only" / "unseen only" quizzes) after a free sign-up; and an
admin area to edit questions, import/export the bank and manage users.

The questions were extracted from the PDFs in `themata/` into `data/`
(`index.json` + `categories/<slug>.json`). The app loads them into SQLite on
first start.

## Run with Docker (production)

```bash
cp .env.example .env        # then fill in SECRET_KEY, ADMIN_USERNAME and ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f web  # migrations → seed → admin → gunicorn
```

The app listens on `http://127.0.0.1:8000` (this machine only). On every start
the entrypoint applies migrations, loads `data/` if the database has no
categories yet, and creates/updates the admin account from `ADMIN_USERNAME` /
`ADMIN_PASSWORD`.

gunicorn runs `WEB_CONCURRENCY` worker processes (default 3), each with
`GUNICORN_THREADS` threads (default 8); both are set in `docker-compose.yaml`.
Every request is logged to `docker compose logs web`.

### Expose it with Tailscale Funnel

```bash
sudo tailscale funnel --bg 8000   # public https://<machine>.<tailnet>.ts.net
tailscale funnel status
sudo tailscale funnel reset       # stop publishing
```

Funnel must be enabled for your tailnet (the first run prints a link to the
admin console if it is not).

**Check that visitor IPs arrive.** After turning Funnel on, open the site from
outside (for example a phone on mobile data) and look at the access lines:

```bash
docker compose logs web
```

The first field of each line must be the visitor's real IP. If it is `-` or a
local address, the login/register rate limits cannot tell visitors apart.

### Upgrade

Back up first (see below), then rebuild and restart. Migrations run on start:

```bash
docker compose up -d --build
```

### Sessions and the admin account

- Rotating `SECRET_KEY` logs everyone out. Resetting a user's password (Διαχείριση
  → Χρήστες) logs that user out everywhere, including "remember me" cookies.
- `ADMIN_PASSWORD` is re-applied on every start, so changing it in `.env` and
  restarting resets the admin's password. `ADMIN_USERNAME` must be 3-32
  characters from `a-z 0-9 _ . -`.
- Renaming `ADMIN_USERNAME` does **not** demote the old admin; it creates a new
  admin account. Remove the old one's rights in Διαχείριση → Χρήστες.

### `.env` quoting

Wrap values that contain `$` or `#` in single quotes, otherwise Compose treats
`$` as a variable and may cut the value at `#`:

```
ADMIN_PASSWORD='pa$$word#with-specials'
```

### Back up the database

Users, progress and edited questions live in the `db_data` volume:

```bash
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db/asep.db'); d=sqlite3.connect('/data/db/backup.db'); s.backup(d)"
docker compose cp web:/data/db/backup.db ./asep-backup.db
docker compose exec web rm /data/db/backup.db   # once the copy is safely out
```

Keep `asep-backup.db` somewhere safe: it contains every user's password hash.

### Restore a backup

Stop the app, copy the backup over `/data/db/asep.db` inside the volume, and
start it again. Run the copy as the container's own user (not `docker compose
cp`, which would leave the file owned by root) and drop the old database's
leftover `-wal`/`-shm` files so SQLite cannot replay them into the restored one:

```bash
docker compose stop
docker compose run --rm --no-deps -v "$PWD":/backup --entrypoint sh web \
  -c 'cp /backup/asep-backup.db /data/db/asep.db && rm -f /data/db/asep.db-wal /data/db/asep.db-shm'
docker compose start
```

The question bank alone can also be downloaded from **Διαχείριση → Εισαγωγή /
Εξαγωγή → Λήψη zip**.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export FLASK_APP=app
.venv/bin/flask db upgrade && .venv/bin/flask seed
ADMIN_USERNAME=admin ADMIN_PASSWORD=change-me-now .venv/bin/flask ensure-admin
.venv/bin/flask run --debug --port 8001
.venv/bin/python -m pytest
```

On this machine the system Python has no `ensurepip`, so create the venv with
`python3 -m venv --without-pip .venv` and install with another pip:
`<other-venv>/bin/pip --python .venv/bin/python install -r requirements.txt`.

## Layout

| Path | Purpose |
|---|---|
| `app.py` | `create_app()` factory, config from env vars |
| `models.py` | Category, Question, User, Attempt |
| `bank.py` | validate / seed / import / export the JSON bank |
| `stats.py` | per-user progress from the latest attempt per question |
| `ratelimit.py` | in-memory limiter for login, register and answer recording |
| `cli.py` | `flask seed`, `flask ensure-admin` |
| `views/` | `main` (pages), `auth`, `api` (JSON for `static/app.js`), `admin` |
| `data/` | extracted question bank (seed source) |
| `themata/` | source PDFs (not shipped in the image) |
