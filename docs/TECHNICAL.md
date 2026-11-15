# Signal Stack - Technical Documentation

## 1. Architecture

A single Python/Flask application with server-rendered pages (no build
step, no frontend framework). Layers:

| Layer | Module | Responsibility |
|---|---|---|
| Web | `web.py`, `templates/` | Dashboard, profile, interview, stack, brief, settings |
| Research | `research.py` | Fetch company website, extract labelled facts |
| Interview | `interview.py` | Generate exactly 10 adaptive questions per company |
| Stack | `stack.py` | Discover/propose sources in 4 categories |
| Monitoring | `monitor.py` | Fetch sources, deduplicate, store history, record runs |
| Ranking | `ranking.py` | Explainable 1-100 intelligence score |
| Automation | `scheduler.py` | Background thread: interval + 10 PM runs |
| Storage | `db.py` | One local SQLite file (companies, research_items, interview_answers, sources, signals, runs, settings) |
| Export | `exporter.py` | CSV/XLSX dataset of stored signals |

Data flow: website -> research items -> profile (+interview answers) ->
stack -> monitoring runs -> ranked signals -> Monday Morning Brief.

## 2. Research and the fact/assumption contract

`research.py` fetches the homepage with `requests` (12s timeout, honest
user-agent) and parses it with BeautifulSoup: page title, meta
description, H1/H2 headings, long paragraphs and any RSS/Atom feed link.
Each extracted string becomes a research item labelled **VERIFIED FACT**
with the page URL stored as its source. A keyword pass over the site's
own text suggests a sector. Sector-based inferences (e.g. "demand is
probably seasonal around admission cycles") are stored separately as
**ASSUMPTION**, sourced to "Signal Stack inference - not verified", and
the interview explicitly asks the user to validate them. If the site
cannot be fetched, the failure is recorded as an assumption item and no
facts are claimed.

## 3. Source discovery: include / exclude / remove

**Include** a source when it is public and fetchable without login or
payment; topically tied to the company, a named competitor, its
customers or its sector; updated at least monthly; and attributable to a
real publisher or the company/competitor itself. The builder combines:
the company's own verified RSS feed (Internal), a website-change watch
on its homepage (Internal), Google News RSS searches for the company
name and its sector (Market), one Google News RSS feed per named
competitor (Competitors), and customer-voice + buyer-trend searches
(Customers). Google News RSS is used because it is public, free,
query-flexible and reliably fetchable - it stands in for dozens of
individual publisher feeds without scraping them.

**Exclude**: login-walled/paywalled pages, crawler-blocking social
profiles, off-topic generic homepages, dead feeds (the company's own
feed is verified with a live parse before being added).

**Remove** (one click in the UI): sources that fail repeatedly, drift
off-topic, or duplicate another source. Removal never deletes history -
previously fetched signals stay stored and labelled with their source.

## 4. Crawling and monitoring

Each source has a type (`rss` or `webpage`) and a crawl frequency.
A monitoring run processes every source whose last successful crawl is
older than its frequency (a manual "Run now" forces all). RSS sources
are parsed with `feedparser` (max 12 newest entries). Webpage sources
are fetched and their heading text is hashed (SHA-256); a changed hash
creates one "website content changed" signal containing the new
headings. Items are deduplicated on `(source_id, link)`. Every run is
recorded with status success/partial/failed and counts.

## 5. Ranking: the intelligence score

Deterministic and fully explainable - no ML black box. For each signal:

```
score = 0.30*relevance + 0.25*impact + 0.20*authority
      + 0.15*confidence + 0.10*freshness        (clamped to 1-100)
```

- **Relevance**: overlap between the signal text and the company's own
  terms (goals, products, sector, name and tracked competitors)
  collected from the profile and interview. If the profile has no terms at all, relevance is a
  disclosed neutral 30; if terms exist but none match, relevance is 10.
- **Impact**: weighted business-event keywords (acquisition 18, funding
  16, launch 14, regulation 14, pricing 10, ...), capped at 100.
- **Authority**: stored per source (own feed 90, own site 85, Google
  News 55-65, manually added sources default 60, user-adjustable).
- **Confidence**: presence of a link (+25), a publication date (+25),
  and a substantive description (+10/+20).
- **Freshness**: 100 today, decaying 3.5 points/day; undated items get
  35 because freshness cannot be proven.

Priority: **High >= 70, Medium 40-69, Low < 40**. The brief prints, for
every item, its component breakdown as the priority reason, the matched
terms/event words as evidence, and a category-specific impact statement.

## 6. AI analysis approach

There is deliberately **no LLM dependency** (the brief mandates $0 cost
and free tools only, and ranking must be auditable). "Analysis" here is
transparent rules-based NLP: keyword/term matching, event detection and
templated impact reasoning. This keeps every score reproducible and
explainable to an executive. The design leaves a clean seam: `ranking.
score_signal()` is a pure function, so an LLM scorer could later be
added beside it and compared against the rules-based baseline.

## 7. Scheduling and automation

`scheduler.py` runs one daemon thread that wakes every minute and reads
settings from SQLite: enabled flag, interval (**2h / 12h / 24h**) and an
optional **daily 22:00 run**. When due, it executes a normal monitoring
run for every company, so automation inherits identical ranking,
dedupe and fallback behaviour. Manual "Run monitoring now" always
forces a full fetch regardless of schedule.

## 8. Reliability and fallback

A failing source raises inside its own try/except only: the run is
marked *partial*, the source's `last_status` shows the exact error, and
previously stored signals remain in the brief, badged "cached (source
currently failing)". The brief page shows a banner whenever the latest
run was partial/failed. Nothing is ever fabricated to fill a gap - an
empty brief is shown as empty. Timeouts are bounded (12s), retries are
left to the next scheduled run, and the scheduler thread can never
crash the web process.

## 9. Scaling note

SQLite + a single process comfortably serves dozens of companies and
hundreds of sources. To scale: (1) move fetching into a worker queue
(e.g. RQ/Celery) so runs parallelise per source; (2) migrate SQLite ->
PostgreSQL (the schema is standard SQL); (3) add per-domain rate
limiting and ETag/Last-Modified conditional fetches; (4) cache parsed
feeds in Redis. The module boundaries already isolate each change.

## 10. Cost statement

**Total recurring cost: $0.** Python, Flask, SQLite, requests,
feedparser, BeautifulSoup and openpyxl are all free/open-source.
Google News RSS is a free public feed. No paid API, no cloud service,
no LLM key is required or used.

## 11. Tests

`pytest -q` - 7 integrated tests, all offline (network substituted with
fixtures): ranking bounds/priority + explanation, exactly-10 adaptive
interview differing across companies, research fact/assumption
labelling, stack coverage of all 4 categories, monitoring store +
dedupe + failure fallback with cache survival, brief page fields +
CSV/XLSX export, and the full add-company HTTP flow.
