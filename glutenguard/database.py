"""SQLite storage for past GlutenGuard scans.

Same pattern as RecallRadar's database.py: a single local .db file, one table, plain
sqlite3 (no ORM). GlutenGuard had no persistence before this — every check was stateless —
so this is new, not a migration.

One table is enough here. Unlike RecallRadar's recalls/recall_products split (driven by a
real one-to-many relationship with inconsistent structure per category), a GlutenGuard scan
is one classification result for one input — there's nothing to normalize out.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "glutenguard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    input_type TEXT NOT NULL,
    product_name TEXT NOT NULL,
    classification TEXT NOT NULL,
    summary TEXT NOT NULL,
    result_json TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_scan(conn: sqlite3.Connection, result, input_type: str) -> int:
    """Save a GlutenGuardResult to history. Returns the new scan's row id.

    Stores the full result as JSON (result_json) alongside a few pulled-out columns
    (product_name, classification, summary) so the history list can render without
    deserializing every row, while the PDF export and detail view can still get the complete
    structured result back via load_scan.
    """
    cursor = conn.execute(
        """
        INSERT INTO scans (input_type, product_name, classification, summary, result_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            input_type,
            result.product_name,
            result.classification,
            result.summary,
            result.model_dump_json(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_scan_history(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    """Most recent scans first."""
    return conn.execute(
        "SELECT * FROM scans ORDER BY scanned_at DESC LIMIT ?", (limit,)
    ).fetchall()


def load_scan_result(row: sqlite3.Row):
    """Reconstruct a GlutenGuardResult from a stored scan row, for PDF export or re-display."""
    from engine import GlutenGuardResult

    return GlutenGuardResult(**json.loads(row["result_json"]))


def delete_scan(conn: sqlite3.Connection, scan_id: int) -> None:
    conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    conn.commit()


def clear_history(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM scans")
    conn.commit()


if __name__ == "__main__":
    conn = get_connection()
    print(f"Database ready at: {DB_PATH}")
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", [t["name"] for t in tables])
    conn.close()
