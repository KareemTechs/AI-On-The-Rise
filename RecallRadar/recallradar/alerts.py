"""Alert generation: turn a scored match into a concise notification.

Per DESIGN.md step 7, an alert has five required parts: the product, the specific risk,
affected identifiers (or an honest statement that none were provided), the recommended
action, and a link to the official government page as the source of truth. The official link
is never paraphrased away — the user should always be able to verify against the primary
source themselves.

This module builds the alert content; it does not send anything (email delivery via Resend is
a separate, later concern per DESIGN.md's Notifications section) — this is deliberately just
the "what would we tell the user" step, kept independent of the "how do we deliver it" step.
"""

from dataclasses import dataclass

from recallradar.matching import MatchConfidence, MatchResult
from recallradar.priority import PriorityTier, score_priority

# Only these tiers produce a user-facing alert at all — SUPPRESSED (no real match) never
# reaches this module in normal use, but the guard is here so alert generation can't be
# accidentally called on a non-match and produce a nonsensical notification.
_ALERTABLE_TIERS = {PriorityTier.URGENT, PriorityTier.STANDARD, PriorityTier.LOW_CONFIDENCE}

_TIER_HEADLINE = {
    PriorityTier.URGENT: "\U0001F534 Urgent recall alert",
    PriorityTier.STANDARD: "\U0001F7E1 Recall alert",
    PriorityTier.LOW_CONFIDENCE: "⚠️  Possible recall match (unconfirmed)",
}


@dataclass
class Alert:
    priority: PriorityTier
    match_confidence: MatchConfidence
    headline: str
    product_line: str
    risk_line: str
    identifiers_line: str
    action_line: str
    source_line: str
    match_reasoning: str

    def as_text(self) -> str:
        """Render as a plain-text notification body (what an email/console alert would show)."""
        lines = [
            self.headline,
            "",
            self.product_line,
            self.risk_line,
            self.identifiers_line,
            self.action_line,
            "",
            self.match_reasoning,
            "",
            self.source_line,
        ]
        return "\n".join(lines)


def _identifiers_line(matched_product: dict | None) -> str:
    if matched_product is None:
        return "Affected identifiers: not applicable — this recall was matched by name only."

    upc = matched_product.get("upc")
    lots = matched_product.get("lot_numbers")

    if not upc and not lots:
        return (
            "Affected identifiers: none were provided on the official recall notice for this "
            "product — check the product description below against what you have."
        )

    parts = []
    if upc:
        parts.append(f"UPC {upc}")
    if lots:
        parts.append(f"lot/code {lots}")
    return "Affected identifiers: " + "; ".join(parts)


def build_alert(match: MatchResult) -> Alert | None:
    """Build a user-facing Alert from a scored MatchResult, or None if it shouldn't alert.

    `match.recall` is expected to carry the fields stored on the recalls table (title, link,
    organization, recall_class, summary); `match.matched_product` (if present) carries whatever
    was extracted onto recall_products (brand, product_name, upc, lot_numbers).
    """
    priority = score_priority(match.recall.get("recall_class"), match.confidence)
    if priority not in _ALERTABLE_TIERS:
        return None

    inv = match.inventory_item
    recall = match.recall
    product = match.matched_product

    product_display = product.get("product_name") if product else recall["title"]
    brand_display = (product.get("brand") if product else None) or inv.get("brand") or ""
    product_line = f"Product: {brand_display} {product_display}".strip()

    risk_line = f"Risk: {recall['title']}"

    action_line = (
        "Recommended action: Do not consume, use, or distribute this product. Check the "
        "official recall notice for full instructions from the manufacturer/agency."
    )

    source_line = f"Official source: {recall['link']}"

    return Alert(
        priority=priority,
        match_confidence=match.confidence,
        headline=_TIER_HEADLINE[priority],
        product_line=product_line,
        risk_line=risk_line,
        identifiers_line=_identifiers_line(product),
        action_line=action_line,
        source_line=source_line,
        match_reasoning=f"Why you're seeing this: {match.reasoning}",
    )


if __name__ == "__main__":
    from recallradar.database import get_connection
    from recallradar.matching import match_item_to_recall

    conn = get_connection()
    inventory = [dict(row) for row in conn.execute("SELECT * FROM inventory").fetchall()]
    recalls = [dict(row) for row in conn.execute("SELECT * FROM recalls").fetchall()]

    alerts_built = 0
    for inv in inventory:
        for recall in recalls:
            products = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM recall_products WHERE recall_nid = ?", (recall["nid"],)
                ).fetchall()
            ]
            result = match_item_to_recall(inv, recall, products)
            alert = build_alert(result)
            if alert:
                alerts_built += 1
                print(alert.as_text())
                print("=" * 70)

    conn.close()
    print(f"\n{alerts_built} alert(s) generated")
