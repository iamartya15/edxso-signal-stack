"""Built-in scheduler (no external services, $0).

A single background thread wakes up once a minute and checks the
settings stored in the database:

  * interval mode: run all companies every N hours (N = 2, 12 or 24)
  * 10 PM mode:    additionally run once a day at 22:00 local time

"Run now" is always available in the UI. The scheduler is started by
run.py only (never during tests), and every automatic run is just a
normal monitoring run, so it inherits the same failure/caching behaviour.
"""
import threading
import time
from datetime import datetime

from .db import connect, get_setting, set_setting, now_iso
from .monitor import run_monitor

_started = False


def _tick(db_path):
    conn = connect(db_path)
    try:
        if get_setting(conn, "scheduler_enabled", "1") != "1":
            return
        interval = int(get_setting(conn, "scheduler_interval_hours", "24") or 24)
        ten_pm = get_setting(conn, "scheduler_ten_pm", "0") == "1"
        last_auto = get_setting(conn, "last_auto_run", "")
        company_ids = [r["id"] for r in conn.execute("SELECT id FROM companies")]
    finally:
        conn.close()
    if not company_ids:
        return

    now = datetime.now()
    due = False
    if not last_auto:
        due = True
    else:
        try:
            elapsed = (datetime.now().astimezone() -
                       datetime.fromisoformat(last_auto)).total_seconds() / 3600
            due = elapsed >= interval
        except ValueError:
            due = True
    ten_pm_due = False
    if ten_pm and now.hour == 22:
        conn = connect(db_path)
        try:
            ten_pm_due = get_setting(conn, "last_ten_pm_run_date", "") != now.strftime("%Y-%m-%d")
        finally:
            conn.close()

    if due or ten_pm_due:
        for cid in company_ids:
            run_monitor(db_path, cid, force=False)
        conn = connect(db_path)
        try:
            set_setting(conn, "last_auto_run", now_iso())
            if ten_pm_due:
                set_setting(conn, "last_ten_pm_run_date", now.strftime("%Y-%m-%d"))
        finally:
            conn.close()


def start_scheduler(db_path):
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                _tick(db_path)
            except Exception:
                pass  # scheduler must never crash the web app
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="signalstack-scheduler").start()
