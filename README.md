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
cp .env.example .env        # then fill in SECRET_KEY and ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f web  # migrations → seed → admin → gunicorn
```

The app listens on `http://127.0.0.1:8000` (this machine only). On every start
the entrypoint applies migrations, loads `data/` if the database has no
questions yet, and creates/updates the admin account from `ADMIN_USERNAME` /
`ADMIN_PASSWORD`.

### Expose it with Tailscale Funnel

```bash
sudo tailscale funnel --bg 8000   # public https://<machine>.<tailnet>.ts.net
tailscale funnel status
sudo tailscale funnel reset       # stop publishing
```

Funnel must be enabled for your tailnet (the first run prints a link to the
admin console if it is not).

### Back up the database

Users, progress and edited questions live in the `db_data` volume:

```bash
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db/asep.db'); d=sqlite3.connect('/data/db/backup.db'); s.backup(d)"
docker compose cp web:/data/db/backup.db ./asep-backup.db
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
| `ratelimit.py` | in-memory limiter for login/register |
| `cli.py` | `flask seed`, `flask ensure-admin` |
| `views/` | `main` (pages), `auth`, `api` (JSON for `static/app.js`), `admin` |
| `data/` | extracted question bank (seed source) |
| `themata/` | source PDFs (not shipped in the image) |
