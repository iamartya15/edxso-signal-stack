# Signal Stack - Company Intelligence & Executive Briefing Engine

**EDXSO AI Engineer Intern - Assignment 1 submission by Amartya Kushwaha**

Signal Stack turns public information about a company into a weekly
executive decision brief. You give it a company name and website; it
researches the company, interviews you with 10 questions generated from
that research, builds a stack of intelligence sources, monitors them on
a schedule, ranks everything it finds with a fully explainable score,
and produces a **Monday Morning Brief**.

No mock data is presented as real: research items are labelled
**VERIFIED FACT** (with the named public source) or **ASSUMPTION**
(Signal Stack's own inference), monitoring stores only items it actually
fetched, and when a source fails the brief honestly falls back to cached
data and says so.

## Demo video

`demo-signal-stack.mp4` in this repo (5 min 17 s) is a captioned walkthrough of the live app: dashboard, labelled research, the adaptive 10-question interview, the Signal Stack, the scheduler, and a real Monday Morning Brief.

**Live demo:** https://edxso-signal-stack.onrender.com — the app running live (free hosting, so the first load may take up to a minute while the service wakes).

## Quick start

```bash
git clone <this-repo> && cd edxso-assignment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python seed.py        # loads the 3 sample companies + live research + a real monitoring run
python run.py         # http://127.0.0.1:5000
```

Then open the dashboard, or run the tests and the dataset export:

```bash
pytest -q
python export_dataset.py            # Meet University dataset -> data/*.csv + data/*.xlsx
```

## The flow

1. **Research** - Add a company (name + website). Signal Stack fetches
   the public website and builds a profile where every claim is labelled
   VERIFIED FACT (with source URL) or ASSUMPTION.
2. **Editable profile** - Correct or extend anything: sector, products,
   goals, customers, competitors. Goals directly drive ranking.
3. **Adaptive interview** - Exactly 10 questions generated from *this*
   company's research (its sector, the offerings on its own homepage,
   known/missing competitors...). Two companies get different interviews.
   Tagged answers flow back into the profile.
4. **Signal Stack** - Sources across 4 categories - **Customers,
   Competitors, Market, Internal** - each with a reason for inclusion,
   an authority weight and a crawl frequency. Add/remove sources freely.
5. **Monitoring** - One click (or the scheduler) fetches every due
   source, deduplicates, ranks and stores items in SQLite forever.
   Failing sources degrade gracefully to cached data.
6. **Monday Morning Brief** - The top signals with Type, Publication,
   Link, Title, Description, Relevance, Score, Priority, Evidence and
   Impact - each score explained in plain language.

## Sample data

`python seed.py` preloads the three companies required by the assignment:

| Company | Website | Category |
|---|---|---|
| Meet University | meetuniversity.com | Education (primary demo) |
| boAt | boat-lifestyle.com | B2C - consumer electronics |
| Zoho | zoho.com | B2B - SaaS |

Each gets a generated sample report (open its Monday Morning Brief)
built from a **real live monitoring run**. The Meet University dataset
is exported to `data/meet-university-signals.csv` and `.xlsx`.

## Automation

Settings page: enable/disable automatic monitoring, choose a **2h /
12h / 24h** interval, and/or a **daily 10:00 PM** run. Automatic runs
respect each source's own crawl frequency.

## Tech

Python + Flask (server-rendered pages), SQLite (local database),
`requests` + `feedparser` + BeautifulSoup for real fetching, `openpyxl`
for Excel export, `pytest` for tests. **Total cost: $0** - every library
is free/open-source and no paid API is used anywhere.

Full architecture, ranking formula, source criteria, reliability model
and scaling notes: **[docs/TECHNICAL.md](docs/TECHNICAL.md)**.

## Project layout

```
run.py                  entry point (starts app + scheduler)
seed.py                 loads the 3 sample companies through the real pipeline
export_dataset.py       CSV/XLSX dataset export for a company
signalstack/            the application package
  db.py                 SQLite schema and storage
  research.py           website research with VERIFIED/ASSUMPTION labelling
  interview.py          adaptive 10-question generator
  stack.py              source discovery across the 4 categories
  monitor.py            fetching, dedupe, run history, cache fallback
  ranking.py            explainable 1-100 intelligence score
  scheduler.py          2h/12h/24h + 10 PM automation
  exporter.py           CSV/XLSX export of stored signals
  web.py                Flask routes
  templates/, static/   server-rendered UI
tests/                  pytest suite (7 tests, all offline)
data/                   SQLite DB (runtime) + exported datasets
docs/TECHNICAL.md       technical documentation
```
