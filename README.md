# JobFndr

A single-user job finding assistant. It pulls internships, junior and mid-level
remote roles from free public job APIs on demand, ranks them against your CV
with a hybrid rule + semantic scorer, and drafts application messages you send
yourself.

Built for one operator — there is no sign-up, no multi-user auth, and no
background scheduler. Jobs are fetched only when you press **Scan jobs**.

```
React SPA (nginx)  ──/api──▶  FastAPI  ──▶  PostgreSQL + pgvector
                                  │
                                  ├──▶ 9 public job sources (HTTP, robots-checked)
                                  ├──▶ SentenceTransformers (all-MiniLM-L6-v2)
                                  └──▶ Anthropic API (proposal drafting, optional)
```

---

## Quick start

```bash
cp .env.example .env      # then edit if the default ports are taken
docker compose up --build
```

First build takes a few minutes: it installs CPU-only PyTorch and bakes the
384-dimension embedding model into the backend image so the first scan does not
stall on a download.

| Service  | URL                        |
| -------- | -------------------------- |
| Frontend | http://localhost:3000      |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5433`           |

If a port is already in use, change `FRONTEND_PORT`, `BACKEND_PORT` or
`POSTGRES_PORT` in `.env` and re-run `docker compose up -d`.

### Tell it who you are

Set these in `.env` before the first run. They seed the single profile row and
supply the contact address in the crawler's User-Agent (polite-crawling
etiquette — it gives site operators someone to reach). A CV upload overwrites
the name and email with whatever it parses.

```bash
OPERATOR_NAME=Your Name
OPERATOR_EMAIL=you@example.com
OPERATOR_LOCATION=City, Country
```

### First run

1. Open the app and go to **Profile**.
2. Under **CV**, choose your CV PDF. It is parsed into skills, languages,
   education and experience, then embedded. Anything the parser gets wrong is
   editable on the same page.
3. Go to **Jobs** and press **Scan jobs**. Expect roughly 40 seconds for a
   first scan of ~1000 postings across all sources.
4. Open a job to see *why* it matched, then **Shortlist**, **Maybe later**,
   **Mark applied** or **Reject** it.
5. Press **Draft proposal**, edit the text, and copy it. JobFndr never sends
   anything on your behalf.

### Experience your CV does not list

If you have a role that is not in the PDF, put it in
`data/manual_experience.json` (copy `data/manual_experience.example.json`):

```json
[
  {
    "role": "Trust & Safety Specialist",
    "company": "Example Corp",
    "dates": "2024 - 2025",
    "description": "Content moderation and policy enforcement."
  }
]
```

These entries survive CV re-uploads, are embedded alongside the CV text, and
count toward the domain weights — so adding a Trust & Safety role genuinely
lifts Trust & Safety jobs up the deck rather than just displaying a line. The
file is gitignored; only the example is committed.

### Configuring the LLM key

Proposal drafting works without a key — it falls back to a draft assembled
locally from your profile and the match explanation. For AI-written drafts:

```bash
# .env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-opus-5
```

Then `docker compose restart backend`. The nav rail shows which mode is active.
`LLM_PROVIDER=openai` uses the OpenAI SDK with the same `LLM_API_KEY` and
`LLM_MODEL` settings.

---

## How ranking works

Every job gets a `final_score` in `[0, 1]`:

```
final_score = 0.4 × rule_score + 0.6 × semantic_score
```

Both weights are configurable via `RULE_WEIGHT` / `SEMANTIC_WEIGHT`.

**Hard filters** run first. A job that fails is kept and demoted to 25% of its
score rather than deleted, so you can still see it and read why it was cut:

- not remote,
- seniority outside internship / junior / mid-level,
- format outside freelance / part-time / full-time,
- requires a language you do not speak,
- remote but restricted to a region you cannot work from.

**Rule score** is a weighted blend of five components:

| Component | Weight | What it measures                                        |
| --------- | ------ | ------------------------------------------------------- |
| domain    | 0.40   | Overlap between the job's domains and your CV's domains  |
| seniority | 0.25   | How well the level matches your targets                  |
| format    | 0.15   | Freelance / part-time / full-time alignment              |
| remote    | 0.10   | Remote-friendliness                                      |
| skills    | 0.10   | Literal mentions of your listed skills                   |

**Semantic score** is the cosine similarity between the job embedding and your
profile embedding, computed inside Postgres with pgvector and calibrated from
the useful `[0.05, 0.60]` band onto `[0, 1]`.

Every score ships with a JSONB `explanation` — matched domains and their
contributions, matched skills, seniority/format alignment, filter reasons and a
plain-English summary. That is what the **Why this matches you** panel renders.

### Tuning it

- **Profile → domain weights** — sliders per domain; saving re-embeds and
  re-ranks every stored job.
- **Profile → hard filters** — levels, formats and remote-only.
- `POST /api/jobs/rerank` re-scores stored jobs without re-fetching.

---

## Job sources

All free, all public, no paid providers. Nine adapters ship enabled; toggle
them in **Profile → sources**.

| Source            | Type     | Notes                                            |
| ----------------- | -------- | ------------------------------------------------ |
| Arbeitnow         | API      | Public job-board API, paginated                  |
| Remotive          | API      | Remote-only board; asks integrators to cache     |
| RemoteOK          | API      | Requires attribution and a link back             |
| Himalayas         | API      | Public remote-jobs API                           |
| Greenhouse boards | ATS      | Public company boards, no key                    |
| Lever boards      | ATS      | Public postings API, no key                      |
| Ashby boards      | ATS      | Public posting API, no key                       |
| RSS feeds         | RSS      | Publicly syndicated feeds, robots-checked        |
| HTML              | Scraping | Generic selector scraper, ships with no targets  |

**Politeness.** Every HTML and RSS fetch is gated on `robots.txt` and honours
any declared crawl-delay; `RESPECT_ROBOTS=true` is the default and should stay
that way for sites you do not control. Attribution required by a source is
surfaced on the job detail page.

**Following more companies.** The ATS adapters take a board list from their
`config` column, so adding a company is a config change, not code:

```sql
UPDATE job_source SET config = '{"boards": ["anthropic", "labelbox", "scaleai"]}'
WHERE name = 'greenhouse';
```

Adding a whole new source means one `JobSourceAdapter` subclass plus one line in
`app/services/sources/registry.py`.

---

## Project layout

```
backend/
  app/
    api/routes/        jobs, profile, proposals, sources, analytics, health
    services/          ranking, job_fetch, profile, proposal, cv_parser,
                       normalizer, taxonomy, sources/, llm/
    repositories/      all SQLAlchemy queries live here
    models/            SQLAlchemy models
    core/              config, database, embeddings
  sql/schema.sql       canonical DDL reference
  tests/               169 tests
frontend/
  src/components/      Panel, Button, ScoreGauge, JobCard, FiltersPanel, NavRail
  src/pages/           Dashboard, JobDetail, ProfileSettings, ProposalDraft, Analytics
  src/api/client.js    the only place that talks to the backend
  src/styles/          tokens, base, components
docker-compose.yml
```

Routes stay thin, services hold the business logic, repositories own every
query. The ranking engine is pure functions over plain dataclasses — no DB
session, no model — which is why it is fully unit-testable.

**Why nginx proxies `/api`:** the browser runs on your host and cannot resolve
the Docker hostname `backend`. The frontend container can, so it does the
name resolution and the app stays same-origin (no CORS in production). CORS is
still enabled for `vite dev` on the host.

---

## Development

```bash
# Backend tests (169, no DB or network required)
cd backend && pip install -r requirements.txt && pytest

# Or inside the container
docker compose exec backend python -m pytest tests/ -q

# Frontend dev server against the containerised backend
cd frontend && npm install && VITE_DEV_API=http://localhost:8000 npm run dev
```

The backend image bakes the source in, so after editing backend code run
`docker compose build backend && docker compose up -d backend`.

---

## API

| Method   | Path                        | Purpose                                  |
| -------- | --------------------------- | ---------------------------------------- |
| `GET`    | `/api/profile`              | Current profile                          |
| `PUT`    | `/api/profile`              | Edit skills/preferences, re-embed, re-rank |
| `POST`   | `/api/profile/cv`           | Upload a CV PDF, parse and embed         |
| `POST`   | `/api/jobs/scan`            | Fetch → normalize → embed → rank         |
| `GET`    | `/api/jobs`                 | List with filters, sorting, pagination   |
| `GET`    | `/api/jobs/{id}`            | Full detail plus match explanation       |
| `POST`   | `/api/jobs/{id}/label`      | Shortlist / maybe / applied / rejected   |
| `DELETE` | `/api/jobs/{id}/label`      | Clear the label                          |
| `POST`   | `/api/jobs/rerank`          | Re-score without re-fetching             |
| `POST`   | `/api/jobs/{id}/proposal`   | Draft an application message             |
| `GET`    | `/api/sources`              | Sources with job counts                  |
| `PUT`    | `/api/sources/{name}`       | Enable/disable a source                  |
| `GET`    | `/api/analytics`            | Dashboard counts                         |
| `GET`    | `/api/health`               | Liveness, DB and embedding-model status  |

Full interactive docs at `/docs`.

---

## Limitations

- **Yield is low by design.** A ~1000-job scan typically leaves 20–30 postings
  that are genuinely remote, reachable from your region, at your level and in a
  language you speak. That is the filters working, not a bug — turn off
  `remote_only` or widen the levels in Profile to see more.
- **ATS boards skew senior and on-site.** Greenhouse/Lever/Ashby supply most of
  the raw volume but few matches. The high-yield sources are Arbeitnow,
  RemoteOK, Remotive, Himalayas and the RSS feeds.
- **CV parsing is heuristic, not an LLM.** It runs offline with no API key, and
  it will miss unusual CV layouts. Everything it produces is editable.
- **Region detection reads the location string only.** A posting that hides
  "US only" in the body will still get through.
- **Scans are synchronous.** The request is held open for the duration (~40s).
  Fine for one user; it would need a task queue for more.
- **Old jobs are never pruned.** Postings accumulate across scans.

## Possible next steps

- A `DELETE /api/jobs/stale` sweep, or a `first_seen` age filter.
- Deduplicate the same role posted to several boards (title + company hash).
- Cover-letter length/tone presets, and per-company research in the prompt.
- More ATS boards focused on annotation, trust & safety and EU policy work.
- Track outcomes per source to learn which boards actually convert.
