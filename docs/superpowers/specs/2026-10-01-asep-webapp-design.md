# ASEP 2027 Web App — Design

**Date:** 2026-10-01
**Status:** Draft — awaiting user review

## Goal

Turn the static ASEP question-bank site (`~/air/Asep_2027`) into a Python web app
that runs in a Docker container and is exposed publicly through Tailscale Funnel.
It keeps the existing quiz/browse experience, adds per-user progress tracking, and
gives the owner an admin area to maintain the question bank and users.

## Decisions (agreed)

| Topic | Decision |
|---|---|
| Stack | Flask 3 + Flask-SQLAlchemy + Flask-Migrate + SQLite + gunicorn, mirroring `SimpleDiscography` |
| Users | Open sign-up (username + password). Guests can quiz/browse; progress saves only when logged in |
| Question source | The 2026 PDFs in `themata/` **replace** the old `.docx` bank |
| Extraction | Done once, by hand-supervised extraction (not part of the app). Result lives in `data/` |
| Admin | Edit questions in browser, import/export JSON, manage users. **No** PDF upload |

## Question data (already produced)

`data/index.json` — `[{ name, slug, count, source }]`, 11 categories, 1988 questions.
`data/categories/<slug>.json` — `[{ id, n, q, a, c }]`:

- `id` — `"<slug>-<n>"`, stable primary key (e.g. `dioikitiko-dikaio-57`)
- `n` — question number as printed in the PDF
- `q` — question text; may contain `\n` where line structure matters (1 table, 1 list, 1 poem)
- `a` — exactly 4 options, index 0–3 = α/β/γ/δ
- `c` — 0-based index of the correct option (taken from the red text in the PDF)

Same shape as the static site's files (plus `n`), so it also drops into the old site.
Validation done: numbering contiguous 1..N per file, 4 options / 1 correct everywhere,
1977 answers agree with the old docx bank, 5 differ because ASEP changed them (each
confirmed against the PDF), 6 new/reworded.

## Architecture

```
ASEP-2027/
  app.py              create_app() factory, registers blueprints, ProxyFix
  config.py           settings from env vars
  extensions.py       db, migrate, login_manager, csrf, limiter
  models.py           Category, Question, User, Attempt
  bank.py             load/validate/export question JSON (seed + admin import/export)
  stats.py            per-user progress queries
  views/
    main.py           page routes: home, quiz, browse, stats
    api.py            JSON API used by static/app.js
    auth.py           register, login, logout
    admin.py          questions, import/export, users
  templates/          base.html + pages (Bootstrap 5, same look as the static site)
  static/app.js       quiz + browse UI, ported from the static site to call the API
  static/style.css
  data/               extracted question bank (seed source)
  migrations/         Alembic (Flask-Migrate)
  tests/              pytest
  Dockerfile, docker-compose.yaml, docker/entrypoint.sh
  requirements.txt, .env.example, .dockerignore, README.md
```

`themata/` (source PDFs) and `docs/` are excluded from the image.

## Data model

- **Category** — `id`, `slug` (unique), `name`, `position`
- **Question** — `id` (string PK, `<slug>-<n>`), `category_id`, `number`, `text`,
  `options` (JSON list of 4 strings), `correct` (0–3), `updated_at`
- **User** — `id`, `username` (unique, 3–32 chars `[A-Za-z0-9_.-]`), `password_hash`
  (werkzeug), `is_admin`, `is_active`, `created_at`, `last_login_at`
- **Attempt** — `id`, `user_id`, `question_id`, `chosen` (0–3), `is_correct`,
  `mode` (`quiz` | `browse`), `created_at`. Deleting a question or user cascades.

A question's **status** for a user is derived from its *latest* attempt:
unseen (no attempts) / correct / wrong.

## Features

### Guests and users
- **Home** — category selector with counts (as today), mode cards.
- **Quiz** — 25 random questions from the chosen category or all; answer, score,
  review (same flow as the static site). Logged-in users get two extra pools:
  *Unseen only* (status unseen) and *Wrong only* (status wrong). If a pool has fewer
  than 25 questions, the quiz uses all of them; an empty pool shows a message.
  Each answer is POSTed as an Attempt when logged in.
- **Browse** — paginated list, click an option to check it. Logged-in clicks are
  recorded as `browse` attempts. Text with `\n` renders with `white-space: pre-line`.
- **Stats** (logged in) — per category: total, answered, correct %, wrong count, with
  "quiz my wrong ones" / "quiz unseen" shortcuts; overall totals.

### Auth
- Register (username, password ≥ 8 chars, confirm), login, logout via Flask-Login.
- Disabled users cannot log in. Login and register are rate-limited per IP
  (Flask-Limiter, in-memory) to blunt brute force/spam on the public URL.

### Admin (`is_admin` only; 403 otherwise)
- **Questions** — search by text/category, edit text/options/correct answer, add a
  question to a category (next `n`), delete a question (with confirmation).
- **Export** — download the whole bank as a zip of `index.json` + `categories/*.json`
  in the format above.
- **Import** — pick the target category, upload a JSON file in the category format
  (every `id` must start with that category's slug) → validate → preview counts
  (added / changed / unchanged / removed, and how many user attempts would be
  deleted) → confirm to apply. Matching is by `id`. The whole category is replaced
  by the file's contents.
- **Users** — list with signup date, last login, attempt count; disable/enable,
  grant/revoke admin, reset password, delete. An admin cannot disable or delete
  themselves.

## API (JSON, same-origin, CSRF-protected for POST)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/categories` | categories with counts |
| GET | `/api/questions?category=<slug>&page=<n>` | browse page (all if no category) |
| GET | `/api/quiz?category=<slug>&pool=all\|unseen\|wrong&size=25` | random quiz set |
| POST | `/api/attempts` | `{question_id, chosen, mode}` → `{is_correct}`; 401 for guests |

Questions are sent with their correct index, as the static site does — this is a
study tool, so hiding answers from the client is not a goal.

## Startup and deployment

`docker/entrypoint.sh`:
1. `flask db upgrade`
2. `flask seed` — if the questions table is empty, load `data/` (idempotent)
3. `flask ensure-admin` — create/update the admin from `ADMIN_USERNAME` /
   `ADMIN_PASSWORD` if both are set
4. `exec gunicorn -b 0.0.0.0:8000 -w ${WEB_CONCURRENCY:-3} "app:create_app()"`

`docker-compose.yaml`: one `web` service, port `127.0.0.1:8000:8000` (only
reachable locally; Funnel provides public access), named volume `db_data:/data/db`,
env `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SESSION_COOKIE_SECURE=1`,
`restart: unless-stopped`. `.env.example` documents the variables.

Exposure: `tailscale funnel --bg 8000` → `https://<machine>.<tailnet>.ts.net`.
`ProxyFix` trusts one proxy hop so redirects/URLs use https. README covers build,
run, Funnel, and backing up the SQLite volume.

## Error handling

- API errors return JSON `{error}` with proper status (400 bad input, 401 guest,
  403 non-admin, 404 unknown question/category).
- Admin import rejects files that fail validation (bad shape, ≠4 options, `c` out of
  range, duplicate ids, unknown category slug) with a message listing the problems;
  nothing is written until the user confirms the preview.
- Custom 404/500 pages in the site's style.

## Testing (pytest, temp SQLite per test)

- `bank`: loading `data/` yields 11 categories / 1988 questions; validation rejects
  malformed JSON; export → import round-trip is a no-op.
- `auth`: register, duplicate username, login/logout, disabled user, rate limit.
- `api`: categories/questions/quiz shapes; `unseen`/`wrong` pools; attempts saved for
  users, 401 for guests.
- `stats`: latest-attempt status logic.
- `admin`: non-admin gets 403; edit question; import preview + apply; user
  disable/delete; self-protection.

## Out of scope

- PDF upload / in-app extraction
- Email verification, password-reset-by-email, OAuth
- Changes to the old static site in `~/air/Asep_2027` (its data can be swapped for
  the new `data/` files separately if wanted)
