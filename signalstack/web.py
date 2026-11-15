"""Web routes: dashboard, profile+research, interview, stack, brief, settings."""
import re
from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, send_file, url_for)

from . import interview as interview_mod
from . import monitor as monitor_mod
from . import research as research_mod
from . import stack as stack_mod
from .db import connect, get_setting, now_iso, set_setting
from .exporter import export_company

bp = Blueprint("web", __name__)


def db():
    return connect(current_app.config["DB_PATH"])


def get_company(conn, cid):
    return conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "company"


def do_research(conn, company):
    items, sector, feeds, error = research_mod.build_research(
        company["name"], company["website"])
    conn.execute("DELETE FROM research_items WHERE company_id = ?", (company["id"],))
    for it in items:
        conn.execute(
            "INSERT INTO research_items(company_id, label, text, source, created_at) "
            "VALUES (?,?,?,?,?)",
            (company["id"], it["label"], it["text"], it["source"], now_iso()))
    if sector and not company["sector"]:
        conn.execute("UPDATE companies SET sector = ?, updated_at = ? WHERE id = ?",
                     (sector, now_iso(), company["id"]))
    conn.commit()
    return feeds, error


def do_build_stack(conn, company, feeds):
    proposed = stack_mod.build_stack(dict(company), feeds)
    added = 0
    for s in proposed:
        cur = conn.execute(
            """INSERT OR IGNORE INTO sources
               (company_id, name, url, category, reason, source_type, authority,
                frequency_hours, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (company["id"], s["name"], s["url"], s["category"], s["reason"],
             s["source_type"], s["authority"], s["frequency_hours"], now_iso()))
        added += cur.rowcount
    conn.commit()
    return added


@bp.route("/")
def index():
    conn = db()
    try:
        companies = conn.execute(
            """SELECT c.*,
                 (SELECT COUNT(*) FROM sources s WHERE s.company_id = c.id) AS n_sources,
                 (SELECT COUNT(*) FROM signals g WHERE g.company_id = c.id) AS n_signals,
                 (SELECT status FROM runs r WHERE r.company_id = c.id ORDER BY r.id DESC LIMIT 1) AS last_run
               FROM companies c ORDER BY c.id""").fetchall()
        settings = {k: get_setting(conn, k) for k in
                    ("scheduler_enabled", "scheduler_interval_hours",
                     "scheduler_ten_pm", "last_auto_run")}
    finally:
        conn.close()
    return render_template("index.html", companies=companies, settings=settings)


@bp.route("/companies", methods=["POST"])
def create_company():
    name = request.form.get("name", "").strip()
    website = request.form.get("website", "").strip()
    if not name or not website:
        flash("Company name and website are both required.", "error")
        return redirect(url_for("web.index"))
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO companies(name, website, category, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (name, research_mod.normalise_url(website),
             request.form.get("category", "").strip(), now_iso(), now_iso()))
        cid = cur.lastrowid
        conn.commit()
        company = get_company(conn, cid)
        feeds, error = do_research(conn, company)
        company = get_company(conn, cid)
        added = do_build_stack(conn, company, feeds)
        flash(f"Research complete for {name}: profile created and {added} sources "
              f"added to its Signal Stack." + (f" Note: {error}" if error else ""),
              "ok")
        return redirect(url_for("web.company", cid=cid))
    finally:
        conn.close()


@bp.route("/company/<int:cid>")
def company(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        if c is None:
            flash("Company not found.", "error")
            return redirect(url_for("web.index"))
        items = conn.execute(
            "SELECT * FROM research_items WHERE company_id = ? ORDER BY id",
            (cid,)).fetchall()
        answers = conn.execute(
            "SELECT COUNT(*) AS n FROM interview_answers WHERE company_id = ? AND answer != ''",
            (cid,)).fetchone()["n"]
    finally:
        conn.close()
    return render_template("company.html", c=c, items=items, answered=answers)


@bp.route("/company/<int:cid>/profile", methods=["POST"])
def update_profile(cid):
    fields = ("name", "website", "category", "sector", "description", "products",
              "goals", "customers", "competitors", "location")
    conn = db()
    try:
        sets = ", ".join(f"{f} = ?" for f in fields)
        conn.execute(f"UPDATE companies SET {sets}, updated_at = ? WHERE id = ?",
                     [request.form.get(f, "").strip() for f in fields] + [now_iso(), cid])
        conn.commit()
        flash("Profile saved.", "ok")
    finally:
        conn.close()
    return redirect(url_for("web.company", cid=cid))


@bp.route("/company/<int:cid>/research/run", methods=["POST"])
def rerun_research(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        feeds, error = do_research(conn, c)
        flash("Research refreshed from the live website." +
              (f" Note: {error}" if error else ""), "ok")
    finally:
        conn.close()
    return redirect(url_for("web.company", cid=cid))


@bp.route("/company/<int:cid>/interview", methods=["GET", "POST"])
def interview_view(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        if c is None:
            flash("Company not found.", "error")
            return redirect(url_for("web.index"))
        items = conn.execute(
            "SELECT * FROM research_items WHERE company_id = ?", (cid,)).fetchall()
        questions = interview_mod.generate_questions(
            dict(c), [dict(i) for i in items])
        if request.method == "POST":
            for pos, q in enumerate(questions, start=1):
                ans = request.form.get(f"q{pos}", "").strip()
                conn.execute(
                    """INSERT INTO interview_answers(company_id, position, question, field, answer, created_at)
                       VALUES (?,?,?,?,?,?)
                       ON CONFLICT(company_id, position) DO UPDATE SET answer = excluded.answer""",
                    (cid, pos, q["question"], q["field"], ans, now_iso()))
                if ans and q["field"] in interview_mod.PROFILE_FIELDS:
                    conn.execute(
                        f"UPDATE companies SET {q['field']} = ?, updated_at = ? WHERE id = ?",
                        (ans, now_iso(), cid))
            conn.commit()
            flash("Interview saved. Tagged answers were merged into the company "
                  "profile, and relevance ranking now uses them.", "ok")
            return redirect(url_for("web.company", cid=cid))
        saved = {r["position"]: r["answer"] for r in conn.execute(
            "SELECT * FROM interview_answers WHERE company_id = ?", (cid,))}
    finally:
        conn.close()
    return render_template("interview.html", c=c, questions=questions, saved=saved)


@bp.route("/company/<int:cid>/stack", methods=["GET", "POST"])
def stack_view(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        if c is None:
            flash("Company not found.", "error")
            return redirect(url_for("web.index"))
        if request.method == "POST":
            conn.execute(
                """INSERT OR IGNORE INTO sources
                   (company_id, name, url, category, reason, source_type, authority,
                    frequency_hours, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (cid, request.form.get("name", "").strip(),
                 request.form.get("url", "").strip(),
                 request.form.get("category", "Market"),
                 request.form.get("reason", "").strip(),
                 request.form.get("source_type", "rss"),
                 int(request.form.get("authority", 60) or 60),
                 int(request.form.get("frequency_hours", 24) or 24), now_iso()))
            conn.commit()
            flash("Source added to the stack.", "ok")
            return redirect(url_for("web.stack_view", cid=cid))
        sources = conn.execute(
            "SELECT * FROM sources WHERE company_id = ? ORDER BY category, id",
            (cid,)).fetchall()
        runs = conn.execute(
            "SELECT * FROM runs WHERE company_id = ? ORDER BY id DESC LIMIT 8",
            (cid,)).fetchall()
    finally:
        conn.close()
    return render_template("stack.html", c=c, sources=sources, runs=runs)


@bp.route("/company/<int:cid>/stack/build", methods=["POST"])
def stack_build(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        items = conn.execute(
            "SELECT * FROM research_items WHERE company_id = ?", (cid,)).fetchall()
        feeds = []
        for it in items:
            if "RSS/Atom feed:" in it["text"]:
                feeds.append(it["text"].split("RSS/Atom feed:")[1].strip())
        added = do_build_stack(conn, c, feeds)
        flash(f"Stack rebuilt: {added} new source(s) added.", "ok")
    finally:
        conn.close()
    return redirect(url_for("web.stack_view", cid=cid))


@bp.route("/company/<int:cid>/stack/<int:sid>/remove", methods=["POST"])
def stack_remove(cid, sid):
    conn = db()
    try:
        conn.execute("DELETE FROM sources WHERE id = ? AND company_id = ?", (sid, cid))
        conn.commit()
        flash("Source removed. Its previously fetched signals stay in history.", "ok")
    finally:
        conn.close()
    return redirect(url_for("web.stack_view", cid=cid))


@bp.route("/company/<int:cid>/monitor/run", methods=["POST"])
def monitor_run(cid):
    result = monitor_mod.run_monitor(current_app.config["DB_PATH"], cid, force=True)
    flash(f"Monitoring run finished: {result['status']} - "
          f"{result['sources_ok']} source(s) ok, {result['sources_failed']} failed, "
          f"{result['new_signals']} new signal(s)." +
          (f" {result['note']}" if result.get("note") else ""), "ok")
    return redirect(url_for("web.stack_view", cid=cid))


@bp.route("/company/<int:cid>/brief")
def brief(cid):
    conn = db()
    try:
        c = get_company(conn, cid)
        if c is None:
            flash("Company not found.", "error")
            return redirect(url_for("web.index"))
        signals = conn.execute(
            """SELECT s.*, src.name AS publication, src.category AS category,
                      src.last_status AS source_status
               FROM signals s JOIN sources src ON src.id = s.source_id
               WHERE s.company_id = ? ORDER BY s.score DESC, s.fetched_at DESC
               LIMIT 25""", (cid,)).fetchall()
        last_run = conn.execute(
            "SELECT * FROM runs WHERE company_id = ? ORDER BY id DESC LIMIT 1",
            (cid,)).fetchone()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM signals WHERE company_id = ?",
            (cid,)).fetchone()["n"]
    finally:
        conn.close()
    stale = bool(last_run and last_run["status"] in ("partial", "failed"))
    return render_template("brief.html", c=c, signals=signals, last_run=last_run,
                           total=total, stale=stale)


@bp.route("/company/<int:cid>/export/<fmt>")
def export(cid, fmt):
    conn = db()
    try:
        c = get_company(conn, cid)
    finally:
        conn.close()
    if c is None:
        flash("Company not found.", "error")
        return redirect(url_for("web.index"))
    csv_path, xlsx_path, n = export_company(
        current_app.config["DB_PATH"], cid,
        current_app.config["DATA_DIR"], f"{slug(c['name'])}-signals")
    path = csv_path if fmt == "csv" else xlsx_path
    flash(f"Exported {n} stored signal(s).", "ok")
    return send_file(path, as_attachment=True)


@bp.route("/settings", methods=["GET", "POST"])
def settings_view():
    conn = db()
    try:
        if request.method == "POST":
            set_setting(conn, "scheduler_enabled",
                        "1" if request.form.get("enabled") else "0")
            interval = request.form.get("interval", "24")
            if interval not in ("2", "12", "24"):
                interval = "24"
            set_setting(conn, "scheduler_interval_hours", interval)
            set_setting(conn, "scheduler_ten_pm",
                        "1" if request.form.get("ten_pm") else "0")
            flash("Scheduler settings saved.", "ok")
            return redirect(url_for("web.settings_view"))
        settings = {k: get_setting(conn, k) for k in
                    ("scheduler_enabled", "scheduler_interval_hours",
                     "scheduler_ten_pm", "last_auto_run")}
    finally:
        conn.close()
    return render_template("settings.html", settings=settings)
