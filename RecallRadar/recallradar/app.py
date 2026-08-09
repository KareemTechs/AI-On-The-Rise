"""RecallRadar — Streamlit dashboard.

Answers the one question the user actually has: "Is anything in my home affected by a
recall?" Everything on this page exists in service of that — the alerts panel leads, split
into confirmed matches (top) and uncertain matches (below) per DESIGN.md's priority tiers, an
"all clear" state when there's nothing to report, a visible timestamp for when the pipeline
last checked, and inventory management underneath so the user can add what they own.

This dashboard is a thin UI layer over the pipeline and database modules already built —
it reads sent_alerts directly rather than re-running the matching engine on every page load
(see database.py's docstring on why sent_alerts stores full alert content), and the "Run
pipeline check" button is the only thing that triggers new fetching/matching/Claude calls.

Deliberately out of scope this week (see DESIGN.md and the Week 3 brief): editing/deleting
inventory items, notification preferences, alert history beyond "all sent alerts", and
barcode/DIN/Open Food Facts lookups for adding items — those are later-week polish. This week
answers the one question; it doesn't yet manage the household's full relationship with its
inventory.
"""

import sys
from pathlib import Path

# Streamlit runs this file directly (`streamlit run recallradar/app.py`), which puts this
# file's own directory on sys.path rather than the project root — so `import recallradar.x`
# fails from inside the recallradar package itself unless the parent directory is added
# explicitly. Every other module in this package is only ever imported (never run this way),
# so this path fix lives here and nowhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from recallradar.database import get_connection, get_inventory, get_last_pipeline_run, get_sent_alerts
from recallradar.inventory import VALID_CATEGORIES, add_item
from recallradar.pipeline import run_pipeline

# Priority tiers that represent a confirmed match (URGENT and STANDARD both come from exact-ID,
# fuzzy-auto, or Claude-confirmed matches — see priority.py's table) versus an uncertain one
# (LOW_CONFIDENCE, which only ever comes from Claude genuinely being unable to tell — see
# matching.py's ClaudeMatchVerdict.UNCERTAIN). SUPPRESSED never reaches sent_alerts at all.
_CONFIRMED_TIERS = {"urgent", "standard"}
_UNCERTAIN_TIERS = {"low_confidence"}

# Confidence labels are keyed on match_confidence (matching.py's MatchConfidence), not on
# priority. priority conflates severity with match confidence — an exact UPC hit and a fuzzy
# 90+ name match can land on the same priority tier despite being very different kinds of
# evidence, so priority alone can't distinguish them. This previously mislabeled every
# confirmed-tier alert as "Confirmed match" regardless of which evidence produced it, which is
# a real safety issue for a recall-alert tool: a fuzzy name match and an exact UPC hit warrant
# different levels of user trust and different follow-up action (verify the label vs. just act).
_CONFIDENCE_LABEL = {
    "exact_id": "Confirmed match",
    "claude_confirmed": "Likely match — verify identifiers",
    "fuzzy_auto": "Strong name match — verify identifiers",
    "claude_uncertain": "Possible match — unconfirmed",
}

_ALERT_RENDERER = {
    "urgent": st.error,
    "standard": st.warning,
    "low_confidence": st.info,
}


def render_alert(alert_row: dict) -> None:
    """Render one stored sent_alerts row as a self-contained alert card."""
    renderer = _ALERT_RENDERER.get(alert_row["priority"], st.info)

    with st.container(border=True):
        renderer(alert_row["headline"])
        st.markdown(f"**{alert_row['product_line']}**")
        st.write(alert_row["risk_line"])
        st.caption(f"Confidence: {_CONFIDENCE_LABEL.get(alert_row['match_confidence'], 'Unknown')}")
        st.write(alert_row["identifiers_line"])
        st.write(alert_row["action_line"])
        st.caption(alert_row["match_reasoning"])
        st.markdown(f"[View official recall notice]({alert_row['source_line'].split(': ', 1)[-1]})")


def render_alerts_panel() -> None:
    st.subheader("Recall alerts")

    conn = get_connection()
    all_alerts = [dict(row) for row in get_sent_alerts(conn)]
    conn.close()

    confirmed = [a for a in all_alerts if a["priority"] in _CONFIRMED_TIERS]
    uncertain = [a for a in all_alerts if a["priority"] in _UNCERTAIN_TIERS]

    if not confirmed and not uncertain:
        st.success("✅ All clear — nothing in your saved inventory matches a known recall.")
        return

    if confirmed:
        # Urgent first within the confirmed group — matches priority.py's severity ordering.
        confirmed.sort(key=lambda a: 0 if a["priority"] == "urgent" else 1)
        st.markdown("#### Confirmed matches")
        for alert_row in confirmed:
            render_alert(alert_row)

    if uncertain:
        st.markdown("#### Possible matches (unconfirmed)")
        st.caption(
            "Claude reviewed these and could not confirm they're the same product you own — "
            "double check against the recall notice before acting."
        )
        for alert_row in uncertain:
            render_alert(alert_row)


def render_last_checked() -> None:
    conn = get_connection()
    last_run = get_last_pipeline_run(conn)
    conn.close()

    if last_run is None:
        st.caption("Last checked: never — click \"Run pipeline check\" below to check now.")
    else:
        st.caption(f"Last checked: {last_run['ran_at']} UTC")


def render_run_pipeline_button() -> None:
    if st.button("🔄 Run pipeline check", type="primary"):
        with st.spinner("Checking government recall feeds and matching against your inventory..."):
            summary = run_pipeline()

        st.toast(
            f"Checked {summary['new_recalls']} new recall(s), "
            f"generated {summary['alerts_generated']} new alert(s).",
            icon="✅",
        )
        st.rerun()


def render_add_item_form() -> None:
    st.subheader("Add an item to your inventory")

    with st.form("add_item_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            product_name = st.text_input("Product name*")
            brand = st.text_input("Brand")
        with col2:
            category = st.selectbox("Category*", sorted(VALID_CATEGORIES))
            upc = st.text_input("UPC (optional)", help="If you have it, enables exact-match alerts.")

        submitted = st.form_submit_button("Add item")

        if submitted:
            try:
                add_item(product_name, brand, category, upc=upc or None)
            except ValueError as e:
                st.error(str(e))
            else:
                st.success(f"Added {product_name} to your inventory.")
                st.rerun()


def render_inventory_list() -> None:
    st.subheader("Your saved inventory")

    conn = get_connection()
    items = [dict(row) for row in get_inventory(conn)]
    conn.close()

    if not items:
        st.caption("No items saved yet — add one above.")
        return

    for category in sorted(VALID_CATEGORIES):
        category_items = [i for i in items if i["category"] == category]
        if not category_items:
            continue

        st.markdown(f"**{category.capitalize()}** ({len(category_items)})")
        for item in category_items:
            brand = item["brand"] or "—"
            upc_note = f" · UPC {item['upc']}" if item["upc"] else ""
            st.markdown(f"- {brand} — {item['product_name']}{upc_note}")


def main() -> None:
    st.set_page_config(page_title="RecallRadar", page_icon="📡", layout="centered")

    st.title("📡 RecallRadar")
    st.write("Is anything in your home affected by a recall?")
    render_last_checked()
    render_run_pipeline_button()

    st.divider()
    render_alerts_panel()

    st.divider()
    render_add_item_form()

    st.divider()
    render_inventory_list()


if __name__ == "__main__":
    main()
