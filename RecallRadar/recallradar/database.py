"""SQLite storage for recalls, their extracted product identifiers, household inventory, and
which alerts have already been sent.

Four tables, matching the design in DESIGN.md:
  - recalls: one row per NID, deduplicated on insert (INSERT OR IGNORE)
  - recall_products: the structured identifiers Claude extracts from each recall's detail
    page (brand, product name, lot numbers, UPC, affected regions) — one-to-many with recalls,
    since a single recall can list dozens of affected product variants, and some recalls have
    none at all (see DESIGN.md's note on consumer-product recalls with no structured table)
  - inventory: household products a user has saved, matched against recalls later
  - sent_alerts: one row per (recall, inventory item) pair that has already produced an alert
    — a UNIQUE constraint on that pair is what makes pipeline.py's repeated runs idempotent
    (see DESIGN.md step 8: "so the system does not repeatedly send the same alert")

recall_products is a separate table rather than columns on `recalls` because that relationship
is one-to-many and its presence is inconsistent across recall categories (see DESIGN.md) — most
consumer-product recalls have zero structured products, food/drug recalls often have many.
"""

import sqlite3

from recallradar.config import DATA_DIR, DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS recalls (
    nid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT,
    summary TEXT,
    organization TEXT,
    published TEXT,
    source_feed TEXT,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    detail_fetched INTEGER DEFAULT 0,
    recall_class TEXT
);

CREATE TABLE IF NOT EXISTS recall_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recall_nid TEXT NOT NULL REFERENCES recalls(nid),
    brand TEXT,
    product_name TEXT,
    lot_numbers TEXT,
    upc TEXT,
    affected_regions TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    upc TEXT,
    lot_number TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sent_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recall_nid TEXT NOT NULL REFERENCES recalls(nid),
    inventory_item_id INTEGER NOT NULL REFERENCES inventory(id),
    priority TEXT NOT NULL,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (recall_nid, inventory_item_id)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database's first creation.

    SQLite's CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists, so a
    database created before Week 2 wouldn't otherwise pick up new columns like recall_class.
    """
    existing_recall_columns = {row["name"] for row in conn.execute("PRAGMA table_info(recalls)")}
    if "recall_class" not in existing_recall_columns:
        conn.execute("ALTER TABLE recalls ADD COLUMN recall_class TEXT")

    existing_inventory_columns = {row["name"] for row in conn.execute("PRAGMA table_info(inventory)")}
    if "upc" not in existing_inventory_columns:
        conn.execute("ALTER TABLE inventory ADD COLUMN upc TEXT")
    if "lot_number" not in existing_inventory_columns:
        conn.execute("ALTER TABLE inventory ADD COLUMN lot_number TEXT")


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def insert_recall(conn: sqlite3.Connection, record) -> bool:
    """Insert a recall if its NID isn't already stored. Returns True if it was newly inserted.

    The caller (fetch and store pipeline) uses this return value to know which recalls are new
    and therefore need their detail page fetched — recalls already in the database don't need
    to be re-fetched or re-processed.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO recalls
            (nid, title, link, summary, organization, published, source_feed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.nid,
            record.title,
            record.link,
            record.summary,
            record.organization,
            record.published,
            record.source_feed,
        ),
    )
    return cursor.rowcount > 0


def mark_detail_fetched(conn: sqlite3.Connection, nid: str, recall_class: str | None = None) -> None:
    conn.execute(
        "UPDATE recalls SET detail_fetched = 1, recall_class = ? WHERE nid = ?",
        (recall_class, nid),
    )


def get_recalls_needing_detail(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Recalls that have been stored but not yet had their detail page extracted."""
    return conn.execute("SELECT * FROM recalls WHERE detail_fetched = 0").fetchall()


def insert_recall_products(conn: sqlite3.Connection, recall_nid: str, products: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO recall_products
            (recall_nid, brand, product_name, lot_numbers, upc, affected_regions)
        VALUES (:recall_nid, :brand, :product_name, :lot_numbers, :upc, :affected_regions)
        """,
        [{**p, "recall_nid": recall_nid} for p in products],
    )


def insert_inventory_item(
    conn: sqlite3.Connection,
    product_name: str,
    brand: str,
    category: str,
    upc: str | None = None,
    lot_number: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO inventory (product_name, brand, category, upc, lot_number) VALUES (?, ?, ?, ?, ?)",
        (product_name, brand, category, upc, lot_number),
    )
    return cursor.lastrowid


def get_inventory(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM inventory ORDER BY added_at").fetchall()


def was_alert_sent(conn: sqlite3.Connection, recall_nid: str, inventory_item_id: int) -> bool:
    """True if this (recall, inventory item) pair has already produced a sent alert."""
    row = conn.execute(
        "SELECT 1 FROM sent_alerts WHERE recall_nid = ? AND inventory_item_id = ?",
        (recall_nid, inventory_item_id),
    ).fetchone()
    return row is not None


def record_sent_alert(conn: sqlite3.Connection, recall_nid: str, inventory_item_id: int, priority: str) -> bool:
    """Record that an alert was sent for this (recall, inventory item) pair.

    Returns True if this was a new record. INSERT OR IGNORE plus the table's UNIQUE constraint
    on (recall_nid, inventory_item_id) means a second attempt to record the same pair is a
    no-op rather than an error or a duplicate row — this is the actual mechanism that makes
    re-running the pipeline safe.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO sent_alerts (recall_nid, inventory_item_id, priority)
        VALUES (?, ?, ?)
        """,
        (recall_nid, inventory_item_id, priority),
    )
    return cursor.rowcount > 0


if __name__ == "__main__":
    conn = get_connection()
    print(f"Database ready at: {DB_PATH}")

    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", [t["name"] for t in tables])

    conn.close()
