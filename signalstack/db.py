"""SQLite storage layer for Signal Stack.

A single local SQLite file is the entire database (allowed by the brief:
"database must be locally hosted"). Every table the product needs lives
here: companies, labelled research items, interview Q&A, the signal stack
(sources), fetched signals (full history), monitoring runs and settings.
"""
import sqlite3
import os
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    website TEXT NOT NULL,
    category TEXT DEFAULT '',          -- B2C / B2B / Education ...
    sector TEXT DEFAULT '',            -- detected or user-set sector
    description TEXT DEFAULT '',
    products TEXT DEFAULT '',          -- products / services, free text
    goals TEXT DEFAULT '',             -- business goals used for relevance
    customers TEXT DEFAULT '',         -- target customers, free text
    competitors TEXT DEFAULT '',       -- comma separated competitor names
    location TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    label TEXT NOT NULL,               -- 'VERIFIED FACT' or 'ASSUMPTION'
    text TEXT NOT NULL,
    source TEXT DEFAULT '',            -- named source for facts
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interview_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    position INTEGER NOT NULL,
    question TEXT NOT NULL,
    field TEXT DEFAULT '',
    answer TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(company_id, position)
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL,            -- Customers / Competitors / Market / Internal
    reason TEXT DEFAULT '',            -- why this source is in the stack
    source_type TEXT DEFAULT 'rss',    -- rss / webpage
    authority INTEGER DEFAULT 60,      -- 0-100 authority weight used in ranking
    frequency_hours INTEGER DEFAULT 24,
    active INTEGER DEFAULT 1,
    last_status TEXT DEFAULT 'never fetched',
    last_fetched_at TEXT DEFAULT '',
    last_hash TEXT DEFAULT '',
    last_snapshot TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(company_id, url)
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    title TEXT NOT NULL,
    link TEXT DEFAULT '',
    description TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    fetched_at TEXT NOT NULL,
    relevance INTEGER DEFAULT 0,
    impact_component INTEGER DEFAULT 0,
    authority INTEGER DEFAULT 0,
    confidence INTEGER DEFAULT 0,
    freshness INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,           -- final intelligence score 1-100
    priority TEXT DEFAULT 'Low',       -- High / Medium / Low
    evidence TEXT DEFAULT '',
    impact_text TEXT DEFAULT '',
    priority_reason TEXT DEFAULT '',
    UNIQUE(source_id, link)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    status TEXT DEFAULT 'running',     -- success / partial / failed
    sources_ok INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,
    new_signals INTEGER DEFAULT 0,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
"""

DEFAULT_SETTINGS = {
    "scheduler_enabled": "1",
    "scheduler_interval_hours": "24",   # one of 2 / 12 / 24
    "scheduler_ten_pm": "0",            # also run daily at 22:00
    "last_auto_run": "",
    "last_ten_pm_run_date": "",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path):
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
    finally:
        conn.close()


def get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
