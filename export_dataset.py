"""Export the demonstration dataset for a company (default: Meet University).

Writes data/<company>-signals.csv and data/<company>-signals.xlsx from the
signals actually stored in the database by monitoring runs.

Usage:  python export_dataset.py ["Company Name"]
"""
import sys

from signalstack import create_app
from signalstack.db import connect
from signalstack.exporter import export_company
from signalstack.web import slug


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "Meet University"
    app = create_app()
    conn = connect(app.config["DB_PATH"])
    try:
        row = conn.execute("SELECT id FROM companies WHERE name = ?", (name,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise SystemExit(f"Company not found: {name} (run seed.py first)")
    csv_path, xlsx_path, n = export_company(
        app.config["DB_PATH"], row["id"], app.config["DATA_DIR"],
        f"{slug(name)}-signals")
    print(f"Exported {n} stored signals -> {csv_path} and {xlsx_path}")


if __name__ == "__main__":
    main()
