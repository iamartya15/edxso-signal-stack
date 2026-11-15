"""Seed the three sample companies required by the assignment:

  1. Meet University  - education (the primary demo company)
  2. boAt             - B2C consumer electronics
  3. Zoho             - B2B SaaS

For each one this runs the *real* pipeline: live website research
(labelled facts/assumptions), Signal Stack construction, and a full
monitoring run that fetches live public feeds. Profile basics below are
seed-provided starting points (editable in the UI); every signal stored
by the monitoring run is fetched live - nothing is fabricated.

Usage:  python seed.py
"""
from signalstack import create_app
from signalstack.db import connect, now_iso
from signalstack.monitor import run_monitor
from signalstack.web import do_build_stack, do_research, get_company

SAMPLES = [
    {
        "name": "Meet University",
        "website": "https://meetuniversity.com",
        "category": "Education (B2C)",
        "sector": "Education",
        "location": "Gurugram, India",
        "description": "Online platform that helps students discover and apply "
                       "to universities abroad, with counselling and test prep.",
        "products": "University search and shortlisting, study-abroad "
                    "counselling, applications support, IELTS/GRE prep",
        "goals": "Grow student applications for partner universities; expand "
                 "counsellor network; increase IELTS/GRE enrolments",
        "customers": "Students in India planning undergraduate and postgraduate "
                     "study abroad, and their parents",
        "competitors": "IDP Education, Leverage Edu, upGrad Abroad, CollegeDekho",
    },
    {
        "name": "boAt",
        "website": "https://www.boat-lifestyle.com",
        "category": "B2C",
        "sector": "Consumer Electronics",
        "location": "Mumbai, India",
        "description": "Direct-to-consumer audio and wearables brand.",
        "products": "Wireless earbuds, headphones, smartwatches, speakers",
        "goals": "Defend earbuds market share; grow smartwatch revenue; "
                 "win festive-season sales",
        "customers": "Young online shoppers buying affordable audio and wearables",
        "competitors": "Noise, Fire-Boltt, JBL, Realme",
    },
    {
        "name": "Zoho",
        "website": "https://www.zoho.com",
        "category": "B2B",
        "sector": "SaaS / Software",
        "location": "Chennai, India",
        "description": "Business software suite (CRM, accounting, HR, office apps).",
        "products": "Zoho CRM, Zoho Books, Zoho People, Zoho Workplace, Zoho One",
        "goals": "Grow Zoho One adoption among SMBs; expand enterprise accounts; "
                 "increase India SMB market share",
        "customers": "Small and mid-sized businesses and their IT teams",
        "competitors": "Salesforce, HubSpot, Freshworks, Microsoft 365",
    },
]


def main():
    app = create_app()
    db_path = app.config["DB_PATH"]
    conn = connect(db_path)
    try:
        for sample in SAMPLES:
            existing = conn.execute("SELECT id FROM companies WHERE name = ?",
                                    (sample["name"],)).fetchone()
            if existing:
                print(f"- {sample['name']}: already seeded, skipping")
                continue
            cur = conn.execute(
                """INSERT INTO companies
                   (name, website, category, sector, location, description,
                    products, goals, customers, competitors, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sample["name"], sample["website"], sample["category"],
                 sample["sector"], sample["location"], sample["description"],
                 sample["products"], sample["goals"], sample["customers"],
                 sample["competitors"], now_iso(), now_iso()))
            cid = cur.lastrowid
            conn.commit()
            company = get_company(conn, cid)
            feeds, error = do_research(conn, company)
            company = get_company(conn, cid)
            added = do_build_stack(conn, company, feeds)
            print(f"- {sample['name']}: profile created, {added} stack sources"
                  + (f" (research note: {error})" if error else ""))
            result = run_monitor(db_path, cid, force=True)
            print(f"    monitoring: {result['status']} - {result['sources_ok']} ok, "
                  f"{result['sources_failed']} failed, {result['new_signals']} new signals")
    finally:
        conn.close()
    print("Seed complete. Start the app with: python run.py")


if __name__ == "__main__":
    main()
