"""Dataset export: the stored signals of one company as CSV and Excel.

Columns mirror the Monday Morning Brief fields, so the exported dataset
is exactly what the executive sees - exported from real stored rows,
never re-generated or embellished.
"""
import csv
import os

from openpyxl import Workbook

from .db import connect

COLUMNS = ["Type", "Publication", "Link", "Title", "Description", "Relevance",
           "Score", "Priority", "Evidence", "Impact", "Published", "Fetched"]


def company_signal_rows(db_path, company_id):
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """SELECT s.*, src.name AS source_name, src.category AS category
               FROM signals s JOIN sources src ON src.id = s.source_id
               WHERE s.company_id = ? ORDER BY s.score DESC, s.fetched_at DESC""",
            (company_id,)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        out.append({
            "Type": r["category"], "Publication": r["source_name"],
            "Link": r["link"], "Title": r["title"],
            "Description": r["description"], "Relevance": r["relevance"],
            "Score": r["score"], "Priority": r["priority"],
            "Evidence": r["evidence"], "Impact": r["impact_text"],
            "Published": r["published_at"], "Fetched": r["fetched_at"],
        })
    return out


def export_company(db_path, company_id, outdir, basename):
    rows = company_signal_rows(db_path, company_id)
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, basename + ".csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    xlsx_path = os.path.join(outdir, basename + ".xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Signals"
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[c] for c in COLUMNS])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22
    wb.save(xlsx_path)
    return csv_path, xlsx_path, len(rows)
