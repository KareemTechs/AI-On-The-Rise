"""The pipeline orchestrator: run every stage in order and report what happened.

Wires together the three existing stages (DESIGN.md steps 1-2, 2, and 4-7) plus the
dedup-on-send mechanism from DESIGN.md step 8, so that running this repeatedly is safe —
recalls that are already known are skipped, recalls that already have extracted detail are
skipped, and (recall, inventory item) pairs that already produced an alert are never
re-alerted, even though the underlying match would still compute the same result.

Stage order:
  1. fetch_and_store   — pull the RSS feeds, insert any new recalls (dedup on NID)
  2. extract_detail    — for recalls not yet processed, fetch the detail page and have
                          Claude extract structured product identifiers + recall_class
  3. generate_and_record_alerts — match every inventory item against every recall, and for
                          any pair that clears the alert threshold and hasn't been sent
                          before, generate the alert and record it in sent_alerts

The sent_alerts check happens BEFORE matching, not just before the final alert is emitted.
Once a recall is in the database and an inventory item is saved, both are immutable for the
rest of this pipeline's lifetime (recall_products for a given NID are only ever extracted
once; inventory items are only added, never edited by this codebase) — so re-matching a pair
that already has a recorded alert would reproduce the same result while paying for another
Claude call, if that pair happened to need one. Checking first avoids that entirely.
"""

from recallradar.alerts import build_alert
from recallradar.database import (
    get_connection,
    get_inventory,
    record_pipeline_run,
    record_sent_alert,
    was_alert_sent,
)
from recallradar.extract_detail import process_pending_details
from recallradar.fetch_and_store import fetch_and_store
from recallradar.matching import match_item_to_recall


def generate_and_record_alerts(conn) -> tuple[int, int]:
    """Match every inventory item against every recall and record any new alerts.

    Returns (alerts_generated, alerts_suppressed):
      - alerts_generated: pairs that cleared the alert threshold AND were newly recorded in
        sent_alerts this run (i.e. genuinely new alerts, not repeats).
      - alerts_suppressed: pairs that had already been sent before (caught by the sent_alerts
        check) and were skipped as a result. Pairs that simply don't qualify for an alert at
        all (no match, or Claude rejected the candidate — see priority.py) aren't counted in
        either bucket, since there's nothing to suppress: no alert was ever going to fire.
    """
    inventory = [dict(row) for row in get_inventory(conn)]
    recalls = [dict(row) for row in conn.execute("SELECT * FROM recalls").fetchall()]

    generated = 0
    suppressed = 0

    for item in inventory:
        for recall in recalls:
            if was_alert_sent(conn, recall["nid"], item["id"]):
                suppressed += 1
                continue

            products = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM recall_products WHERE recall_nid = ?", (recall["nid"],)
                ).fetchall()
            ]
            match = match_item_to_recall(item, recall, products)
            alert = build_alert(match)
            if alert is None:
                continue  # doesn't qualify for an alert at all — nothing to suppress or send

            was_new = record_sent_alert(conn, recall["nid"], item["id"], alert)
            if was_new:
                generated += 1
            else:
                # Only reachable if two pipeline runs raced on the same pair; the UNIQUE
                # constraint (checked in database.py) is the real guarantee against
                # double-sending, this branch is just keeping the counts honest if it happens.
                suppressed += 1

    conn.commit()
    return generated, suppressed


def run_pipeline() -> dict:
    """Run the full pipeline once and return a summary of what happened.

    Stages 1 and 2 (fetch_and_store, process_pending_details) each open and close their own
    connection — get_connection() runs schema creation/migration on every call, including the
    one made here for stage 3, so the sent_alerts table (and any other newly-added schema) is
    guaranteed to exist before it's needed regardless of call order.
    """
    total_fetched, new_recalls = fetch_and_store()
    details_extracted = process_pending_details()

    conn = get_connection()
    alerts_generated, alerts_suppressed = generate_and_record_alerts(conn)

    summary = {
        "new_recalls": new_recalls,
        "details_extracted": details_extracted,
        "alerts_generated": alerts_generated,
        "alerts_suppressed": alerts_suppressed,
    }
    record_pipeline_run(conn, summary)
    conn.commit()
    conn.close()

    return summary


if __name__ == "__main__":
    summary = run_pipeline()
    print()
    print("Pipeline summary")
    print("-" * 40)
    for key, value in summary.items():
        print(f"{key:20s} {value}")
