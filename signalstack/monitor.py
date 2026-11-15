"""Monitoring engine.

Fetches every due source in a company's Signal Stack, stores new items
as ranked signals (history is kept forever in the signals table), and
records a run row describing what happened.

Reliability contract:
  * A failing source never blocks the others - the run is marked partial.
  * When a source fails, previously stored signals stay in the database
    and keep appearing in the brief; the UI labels them as cached data
    and shows the source's failure status.
  * Duplicate items (same source + link) are never stored twice.
"""
import hashlib
import time
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from . import ranking
from .db import connect, now_iso
from .research import UA

MAX_ENTRIES_PER_FEED = 12


def parse_feed(url):
    """Wrapper so tests can substitute feed fetching."""
    return feedparser.parse(url, agent=UA["User-Agent"])


def fetch_webpage(url):
    resp = requests.get(url, headers=UA, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    heads = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        t = " ".join(h.get_text(" ").split())
        if t and t not in heads:
            heads.append(t)
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else url
    return title, " | ".join(heads[:10])


def _entry_datetime(entry):
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


def _store_signal(conn, company, source, title, link, description, published_dt):
    terms = ranking.terms_from(company["goals"], company["products"],
                               company["sector"], company["name"],
                               company["competitors"])
    result = ranking.score_signal(
        terms, source["category"], title, description,
        source["authority"], published_dt, has_link=bool(link))
    cur = conn.execute(
        """INSERT OR IGNORE INTO signals
           (company_id, source_id, title, link, description, published_at,
            fetched_at, relevance, impact_component, authority, confidence,
            freshness, score, priority, evidence, impact_text, priority_reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (company["id"], source["id"], title[:400], link, (description or "")[:1200],
         published_dt.isoformat(timespec="seconds") if published_dt else "",
         now_iso(), result["relevance"], result["impact_component"],
         result["authority"], result["confidence"], result["freshness"],
         result["score"], result["priority"], result["evidence"],
         result["impact_text"], result["priority_reason"]))
    return cur.rowcount  # 1 if inserted, 0 if it was a duplicate


def _due(source, force):
    if force or not source["last_fetched_at"]:
        return True
    try:
        last = datetime.fromisoformat(source["last_fetched_at"])
    except ValueError:
        return True
    hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    return hours >= (source["frequency_hours"] or 24)


def run_monitor(db_path, company_id, force=False):
    """Run one monitoring pass for a company. Returns the run summary dict."""
    conn = connect(db_path)
    try:
        company = conn.execute("SELECT * FROM companies WHERE id = ?",
                               (company_id,)).fetchone()
        if company is None:
            return {"status": "failed", "note": "company not found"}
        cur = conn.execute(
            "INSERT INTO runs(company_id, started_at, status) VALUES (?, ?, 'running')",
            (company_id, now_iso()))
        run_id = cur.lastrowid
        conn.commit()

        sources = conn.execute(
            "SELECT * FROM sources WHERE company_id = ? AND active = 1 ORDER BY id",
            (company_id,)).fetchall()
        ok = failed = new_signals = 0
        for source in sources:
            if not _due(source, force):
                continue
            try:
                added = 0
                if source["source_type"] == "webpage":
                    title, snapshot = fetch_webpage(source["url"])
                    digest = hashlib.sha256(snapshot.encode()).hexdigest()
                    if source["last_hash"] and digest != source["last_hash"]:
                        added = _store_signal(
                            conn, company, source,
                            f"Website content changed: {source['name']}",
                            source["url"] + "#change-" + digest[:8],
                            f"New homepage headings detected: {snapshot[:600]}",
                            datetime.now(timezone.utc))
                    conn.execute(
                        "UPDATE sources SET last_hash = ?, last_snapshot = ? WHERE id = ?",
                        (digest, snapshot[:2000], source["id"]))
                else:
                    parsed = parse_feed(source["url"])
                    entries = getattr(parsed, "entries", None)
                    if entries is None or (len(entries) == 0 and getattr(parsed, "bozo", 0)):
                        raise RuntimeError("feed returned no entries")
                    for entry in entries[:MAX_ENTRIES_PER_FEED]:
                        added += _store_signal(
                            conn, company, source,
                            getattr(entry, "title", "Untitled"),
                            getattr(entry, "link", ""),
                            getattr(entry, "summary", "") or getattr(entry, "description", ""),
                            _entry_datetime(entry))
                conn.execute(
                    "UPDATE sources SET last_status = 'ok', last_fetched_at = ? WHERE id = ?",
                    (now_iso(), source["id"]))
                ok += 1
                new_signals += added
            except Exception as exc:  # one bad source must not sink the run
                conn.execute(
                    "UPDATE sources SET last_status = ?, last_fetched_at = ? WHERE id = ?",
                    (f"failed: {exc.__class__.__name__}: {exc}"[:200], now_iso(), source["id"]))
                failed += 1
            conn.commit()

        status = "success" if failed == 0 else ("partial" if ok > 0 else "failed")
        note = ("" if failed == 0 else
                f"{failed} source(s) failed; brief is showing cached data for those.")
        conn.execute(
            """UPDATE runs SET finished_at = ?, status = ?, sources_ok = ?,
               sources_failed = ?, new_signals = ?, note = ? WHERE id = ?""",
            (now_iso(), status, ok, failed, new_signals, note, run_id))
        conn.commit()
        return {"run_id": run_id, "status": status, "sources_ok": ok,
                "sources_failed": failed, "new_signals": new_signals, "note": note}
    finally:
        conn.close()
