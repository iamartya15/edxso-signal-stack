"""Integrated tests for Signal Stack. All offline: network calls are
substituted with fixtures, so the suite passes with no internet."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signalstack import create_app           # noqa: E402
from signalstack import monitor, ranking, research  # noqa: E402
from signalstack.db import connect, now_iso  # noqa: E402
from signalstack.exporter import export_company  # noqa: E402
from signalstack.interview import generate_questions  # noqa: E402
from signalstack.stack import build_stack    # noqa: E402


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    from signalstack.db import init_db
    init_db(path)
    return path


@pytest.fixture()
def app(db_path):
    return create_app(db_path)


def add_company(db_path, **overrides):
    data = {"name": "Acme Edu", "website": "https://acme.example",
            "category": "Education (B2C)", "sector": "Education",
            "products": "University admissions counselling",
            "goals": "Grow student applications",
            "customers": "Students", "competitors": "RivalEd",
            "location": "", "description": ""}
    data.update(overrides)
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO companies (name, website, category, sector, products,
               goals, customers, competitors, location, description, created_at,
               updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["name"], data["website"], data["category"], data["sector"],
             data["products"], data["goals"], data["customers"],
             data["competitors"], data["location"], data["description"],
             now_iso(), now_iso()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# 1 ---------------------------------------------------------------------
def test_ranking_score_bounds_and_priority():
    terms = ranking.terms_from("grow student applications", "admissions counselling")
    strong = ranking.score_signal(
        terms, "Competitors",
        "RivalEd launches free admissions counselling and raises funding",
        "RivalEd announced a launch and new funding round for its student "
        "applications platform, expanding aggressively across India this quarter.",
        authority=90, published_dt=datetime.now(timezone.utc), has_link=True)
    assert 1 <= strong["score"] <= 100
    assert strong["priority"] == "High"
    assert strong["score"] >= 70
    weak = ranking.score_signal(
        terms, "Market", "Local weather update", "Rain expected tomorrow.",
        authority=30, published_dt=datetime.now(timezone.utc) - timedelta(days=60),
        has_link=False)
    assert weak["priority"] == "Low"
    assert weak["score"] < strong["score"]
    assert "score" in weak["priority_reason"]  # ranking is explained, not magic


# 2 ---------------------------------------------------------------------
def test_interview_is_exactly_ten_and_adaptive():
    edu = {"name": "Acme Edu", "sector": "Education", "products": "",
           "goals": "", "competitors": "", "customers": "", "location": ""}
    saas = {"name": "CloudDesk", "sector": "SaaS / Software",
            "products": "CRM software", "goals": "Grow SMB subscriptions",
            "competitors": "Salesforce", "customers": "SMBs", "location": "Pune"}
    q_edu = generate_questions(edu, [])
    q_saas = generate_questions(saas, [])
    assert len(q_edu) == 10 and len(q_saas) == 10
    text_edu = " ".join(q["question"] for q in q_edu)
    text_saas = " ".join(q["question"] for q in q_saas)
    assert text_edu != text_saas                      # adaptive, not identical
    assert "Acme Edu" in text_edu and "CloudDesk" in text_saas
    assert "Salesforce" in text_saas                  # known competitor is referenced
    assert "students and parents" in text_edu         # sector-aware wording


# 3 ---------------------------------------------------------------------
def test_research_labels_facts_and_assumptions(monkeypatch):
    def fake_fetch(url):
        return {"title": "Acme - Study Abroad Counselling",
                "description": "Helping students reach universities abroad.",
                "headings": ["Study Abroad Counselling", "IELTS Prep"],
                "paragraphs": ["We help students apply to universities in the UK and USA."],
                "feeds": [], "final_url": url}
    monkeypatch.setattr(research, "fetch_site", fake_fetch)
    items, sector, feeds, error = research.build_research("Acme", "https://acme.example")
    assert error is None and sector == "Education"
    facts = [i for i in items if i["label"] == "VERIFIED FACT"]
    assumptions = [i for i in items if i["label"] == "ASSUMPTION"]
    assert facts and all(i["source"] == "https://acme.example" for i in facts)
    assert assumptions and all("not verified" in i["source"] for i in assumptions)


# 4 ---------------------------------------------------------------------
def test_stack_covers_all_four_categories(db_path):
    cid = add_company(db_path)
    conn = connect(db_path)
    try:
        company = conn.execute("SELECT * FROM companies WHERE id = ?",
                               (cid,)).fetchone()
        sources = build_stack(dict(company), feeds_found=[])
    finally:
        conn.close()
    categories = {s["category"] for s in sources}
    assert categories == {"Customers", "Competitors", "Market", "Internal"}
    assert len(sources) >= 6
    assert all(s["reason"] for s in sources)          # every source justifies itself
    rival = [s for s in sources if s["category"] == "Competitors"]
    assert any("RivalEd" in s["name"] for s in rival)  # named competitor tracked


# 5 ---------------------------------------------------------------------
class FakeEntry(dict):
    __getattr__ = dict.get


def fake_feed(entries):
    class P:
        bozo = 0
    p = P()
    p.entries = entries
    return p


def test_monitor_stores_dedupes_and_falls_back(db_path, monkeypatch):
    cid = add_company(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            """INSERT INTO sources (company_id, name, url, category, reason,
               source_type, authority, frequency_hours, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (cid, "Acme news", "https://news.example/feed", "Market", "test",
             "rss", 70, 12, now_iso()))
        conn.commit()
    finally:
        conn.close()

    entry = FakeEntry(title="Acme Edu raises funding to grow student applications",
                      link="https://news.example/1",
                      summary="Acme Edu announced funding to expand admissions counselling.",
                      published_parsed=None, updated_parsed=None)
    monkeypatch.setattr(monitor, "parse_feed", lambda url: fake_feed([entry]))
    r1 = monitor.run_monitor(db_path, cid, force=True)
    assert r1["status"] == "success" and r1["new_signals"] == 1
    r2 = monitor.run_monitor(db_path, cid, force=True)
    assert r2["new_signals"] == 0                      # duplicates never stored twice

    def boom(url):
        raise RuntimeError("network down")
    monkeypatch.setattr(monitor, "parse_feed", boom)
    r3 = monitor.run_monitor(db_path, cid, force=True)
    assert r3["status"] == "failed"                    # failure is contained
    conn = connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM signals WHERE company_id = ?",
                         (cid,)).fetchone()["n"]
        src = conn.execute("SELECT last_status FROM sources WHERE company_id = ?",
                           (cid,)).fetchone()
    finally:
        conn.close()
    assert n == 1                                      # cached signal survives
    assert src["last_status"].startswith("failed")     # ...and failure is visible


# 6 ---------------------------------------------------------------------
def test_brief_flow_and_export(app, db_path, monkeypatch):
    cid = add_company(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            """INSERT INTO sources (company_id, name, url, category, reason,
               source_type, authority, frequency_hours, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (cid, "Acme news", "https://news.example/feed", "Market", "test",
             "rss", 70, 12, now_iso()))
        conn.commit()
    finally:
        conn.close()
    entry = FakeEntry(title="New policy expands student applications window",
                      link="https://news.example/2",
                      summary="A policy update expands the applications window for students.",
                      published_parsed=None, updated_parsed=None)
    monkeypatch.setattr(monitor, "parse_feed", lambda url: fake_feed([entry]))
    monitor.run_monitor(db_path, cid, force=True)

    client = app.test_client()
    resp = client.get(f"/company/{cid}/brief")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for field in ("Acme news", "Score", "Priority", "Evidence", "Impact", "Relevance"):
        assert field in html

    csv_path, xlsx_path, n = export_company(db_path, cid, str(os.path.dirname(db_path)), "acme-signals")
    assert n == 1 and os.path.exists(csv_path) and os.path.exists(xlsx_path)


# 7 ---------------------------------------------------------------------
def test_full_user_flow_via_http(app, monkeypatch):
    def fake_fetch(url):
        return {"title": "Acme Edu - Admissions", "description": "Admissions help.",
                "headings": ["Admissions Counselling"], "paragraphs": [],
                "feeds": [], "final_url": url}
    monkeypatch.setattr(research, "fetch_site", fake_fetch)
    client = app.test_client()
    resp = client.post("/companies", data={"name": "Acme Edu",
                                           "website": "https://acme.example",
                                           "category": "Education (B2C)"},
                       follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "VERIFIED FACT" in html and "ASSUMPTION" in html
    resp = client.get("/company/1/interview")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).count("textarea") >= 10
