# ΑΣΕΠ 2027 — Τράπεζα Θεμάτων (web app)

Flask web app for studying the 2026 ASEP question bank (1988 questions, 11
categories): random quizzes and full browsing for everyone; per-user progress
(stats, "wrong only" / "unseen only" quizzes) after a free sign-up; and an
admin area to edit questions, import/export the bank and manage users.

The questions were extracted from the PDFs in `themata/` into `data/`
(`index.json` + `categories/<slug>.json`). The app loads them into the
database on first start.

## Run with Docker (production)

Production uses an existing PostgreSQL server (the container has no database of
its own). All configuration lives in the git-ignored `env/` folder, created from
the tracked templates:

```bash
cp env/app.env.example env/app.env             # SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
cp env/database.env.example env/database.env   # the PostgreSQL connection
# edit both files, then:
docker compose up -d --build
docker compose logs -f web  # migrations → seed → admin → gunicorn
```

`env/database.env` holds the connection to the server:

| Key | Meaning |
|---|---|
| `HOST` | PostgreSQL server host name or IP |
| `PORT` | server port (`5432` if left empty) |
| `ADMIN` | database user name |
| `DATABASE` | an existing database on the server |
| `PASSWORD` | the user's password (special characters are fine) |

The user needs `CREATE` on schema `public`, and the server must accept
connections from this machine (`pg_hba.conf`). The tables are created by the
migrations on every start, so the database can start empty. Alternatively set a
single `DATABASE_URL` (it takes precedence over the keys above; `postgres://` and
`postgresql://` are rewritten to the psycopg driver). With `SESSION_COOKIE_SECURE=1`,
as in `docker-compose.yaml`, the app refuses to start on SQLite.

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

**Check that visitor IPs arrive.** After turning Funnel on:
1. Load the site from a phone on mobile data; check the access log that the
   raw `X-Forwarded-For` header ends with the phone's public IP.
2. Run `curl -H 'X-Forwarded-For: 203.0.113.9' https://<machine>.<tailnet>.ts.net/`.
   Check the logged header value: the LAST entry must be your real IP, not
   203.0.113.9. (ProxyFix with `x_for=1` in `app.py` trusts only the last entry.)
   If it logs just `203.0.113.9`, Funnel is passing client headers through;
   set `x_for=0` instead.
3. If the logged IP is `-` or a local address, all visitors share one IP for
   rate limiting. Check your Funnel and proxy chain.

### Upgrade

Back up the database first (see below), then rebuild and restart. Migrations run
on start:

```bash
docker compose up -d --build
```

### Sessions and the admin account

- Rotating `SECRET_KEY` logs everyone out. Resetting a user's password (Διαχείριση
  → Χρήστες) logs that user out everywhere, including "remember me" cookies.
- `ADMIN_PASSWORD` is re-applied on every start, so changing it in `env/app.env`
  and restarting resets the admin's password. `ADMIN_USERNAME` must be 3-32
  characters from `a-z 0-9 _ . -`.
- Renaming `ADMIN_USERNAME` does **not** demote the old admin; it creates a new
  admin account. Remove the old one's rights in Διαχείριση → Χρήστες.

### `env/*.env` quoting

Always wrap `PASSWORD` in single quotes. Wrap other values that contain `$` or `#` in single quotes, otherwise Compose treats
`$` as a variable and may cut the value at `#`. Single quotes are literal for both Docker Compose and the shell:

```
PASSWORD='your-password-here'
ADMIN_PASSWORD='pa$$word#with-specials'
```

### Back up the database

Users, progress and edited questions live in your PostgreSQL database. Dump it
from the host (needs `pg_dump` 18 or newer, as new as the server):

```bash
mkdir -p ~/asep-backups
set -a; . env/database.env; set +a
PGPASSWORD="$PASSWORD" pg_dump -h "$HOST" -p "$PORT" -U "$ADMIN" -Fc "$DATABASE" > ~/asep-backups/asep-$(date +%F).dump
```

Keep the dump somewhere safe: it contains every user's password hash. Run these
commands in a throwaway shell: with those variables exported, a local `flask`
command would use the production database instead of SQLite.

### Restore a backup

Stop the app, restore, and start it again. `--clean --if-exists` drops the
existing tables first:

```bash
docker compose stop
set -a; . env/database.env; set +a
PGPASSWORD="$PASSWORD" pg_restore --clean --if-exists -h "$HOST" -p "$PORT" -U "$ADMIN" -d "$DATABASE" ~/asep-backups/asep-YYYY-MM-DD.dump
docker compose start
```

The question bank alone can also be downloaded from **Διαχείριση → Εισαγωγή /
Εξαγωγή → Λήψη zip**.

## Local development

Only Docker Compose reads `env/`. Unless `DATABASE_URL` or the connection keys
(`HOST`, `ADMIN`, `DATABASE`, `PASSWORD`) are exported in your shell, the app
uses a local SQLite file (`asep.db`, or the path in `ASEP_DB`). That fallback is
for development only.

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

### Run the tests on PostgreSQL

The tests use a throwaway SQLite file per test. To run them on PostgreSQL as
well, point `TEST_DATABASE_URL` at a scratch database whose name contains `test`
(every test drops and recreates all its tables; the run aborts otherwise):

```bash
docker run -d --rm --name asep-pg-test -e POSTGRES_USER=asep_test -e POSTGRES_PASSWORD=asep-test -e POSTGRES_DB=asep_test -p 127.0.0.1:55432:5432 postgres:18
TEST_DATABASE_URL=postgresql+psycopg://asep_test:asep-test@127.0.0.1:55432/asep_test .venv/bin/python -m pytest
```

## Layout

| Path | Purpose |
|---|---|
| `app.py` | `create_app()` factory, config from env vars, `database_uri()` |
| `env/` | `*.env.example` templates; the real `app.env` / `database.env` are git-ignored |
| `models.py` | Category, Question, User, Attempt |
| `bank.py` | validate / seed / import / export the JSON bank |
| `stats.py` | per-user progress from the latest attempt per question |
| `ratelimit.py` | in-memory limiter for login, register and answer recording |
| `cli.py` | `flask seed`, `flask ensure-admin` |
| `views/` | `main` (pages), `auth`, `api` (JSON for `static/app.js`), `admin` |
| `data/` | extracted question bank (seed source) |
| `themata/` | source PDFs (not shipped in the image) |
