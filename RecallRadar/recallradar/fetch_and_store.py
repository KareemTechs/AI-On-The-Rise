"""Fetch all feeds and store new recalls in SQLite, deduplicated on NID.

Run this to pull the latest recalls and see which ones are actually new versus already known.
Re-running immediately after should report zero new recalls — that's the dedup working.
"""

from recallradar.database import get_connection, insert_recall
from recallradar.fetch_feeds import fetch_all_feeds


def fetch_and_store() -> tuple[int, int]:
    """Fetch every feed, store new recalls, and return (total_fetched, newly_inserted)."""
    conn = get_connection()
    records = fetch_all_feeds()

    new_count = 0
    for record in records:
        if insert_recall(conn, record):
            new_count += 1

    conn.commit()
    conn.close()

    return len(records), new_count


if __name__ == "__main__":
    total, new = fetch_and_store()
    print(f"Fetched {total} recalls, {new} newly inserted, {total - new} already known")
