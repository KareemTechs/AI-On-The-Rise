# Demo: create a SQLite database with one table and insert one row.

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recalls (
            nid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            organization TEXT,
            category TEXT,
            recall_class TEXT,
            last_updated TEXT,
            url TEXT
        )
    """)


def insert_recall(conn, recall):
    conn.execute(
        """
        INSERT OR IGNORE INTO recalls
            (nid, title, organization, category, recall_class, last_updated, url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recall["nid"],
            recall["title"],
            recall["organization"],
            recall["category"],
            recall["recall_class"],
            recall["last_updated"],
            recall["url"],
        ),
    )


if __name__ == "__main__":
    # Start fresh each run so this demo is repeatable.
    DB_PATH.unlink(missing_ok=True)

    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    # A real record pulled from the live CFIA feed (see 01_parse_cfia_rss.py).
    sample_recall = {
        "nid": "82436",
        "title": "Coaticook brand White Cheddar cheeses recalled due to Listeria monocytogenes",
        "organization": "CFIA",
        "category": "Dairy",
        "recall_class": "Class 1",
        "last_updated": "2026-08-03",
        "url": "https://recalls-rappels.canada.ca/en/alert-recall/coaticook-brand-white-cheddar-cheeses-recalled-due-listeria-monocytogenes",
    }

    insert_recall(conn, sample_recall)
    conn.commit()

    print(f"Database created at: {DB_PATH}")
    print("-" * 60)

    cursor = conn.execute("SELECT * FROM recalls")
    columns = [description[0] for description in cursor.description]
    for row in cursor.fetchall():
        for col, val in zip(columns, row):
            print(f"{col:15s} {val}")

    conn.close()
