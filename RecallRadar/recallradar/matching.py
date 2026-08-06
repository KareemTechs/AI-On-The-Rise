"""The matching engine: decide whether a recalled product is likely something a user owns.

This is the core of the agentic loop described in DESIGN.md steps 4-6. Matching happens in
tiers, cheapest and most certain first:

  1. Exact matching  — NID/UPC/lot number. Free, unambiguous, no judgment calls.
  2. Fuzzy matching   — rapidfuzz on brand + product name, three-tier thresholds.
  3. Claude evaluation — only for the fuzzy scores landing in the genuinely uncertain middle
     band, where a plain string score can't be trusted (see DESIGN.md's Tylenol/Advil example).
  4. Priority scoring — combine recall_class severity with match confidence into one tier.

Every MatchResult carries a `confidence` tier and a `reasoning` string, so a downstream alert
(or an audit answering "why did/didn't I get notified about X") always has an explanation to
point to — this is what DESIGN.md step 8 calls "the stored reasoning."
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from recallradar.config import MODEL, client

# Three-tier fuzzy thresholds, calibrated against real product-name pairs (see
# demos/03_fuzzy_match.py and DESIGN.md step 4): genuine near-matches
# ("Coaticook White Cheddar Cheese Curds" vs "Coaticook cheddar curds - white") score in the
# 60-90 range on WRatio, but so do some clearly unrelated products in the same shape
# ("Tylenol Extra Strength Caplets" vs "Advil Extra Strength Tablets" scored ~76). That overlap
# is exactly why the middle band exists and gets escalated to Claude rather than auto-decided
# either way.
FUZZY_REJECT_BELOW = 60.0  # below this: not worth considering a candidate at all
FUZZY_AUTO_MATCH_ABOVE = 90.0  # above this: confident enough to auto-confirm without Claude


class MatchConfidence(str, Enum):
    """How sure we are that a recall and an inventory item are the same product.

    Ordered from strongest to weakest evidence — used both for display and for priority
    scoring (see PriorityTier below), where exact-ID matches always outrank a Claude judgment
    call, and a Claude "likely" always outranks a Claude "uncertain."
    """

    EXACT_ID = "exact_id"  # NID, UPC, or lot number matched exactly
    CLAUDE_CONFIRMED = "claude_confirmed"  # fuzzy candidate, Claude judged likely the same
    CLAUDE_UNCERTAIN = "claude_uncertain"  # fuzzy candidate, Claude genuinely couldn't tell
    CLAUDE_REJECTED = "claude_rejected"  # fuzzy candidate, Claude judged likely different
    FUZZY_AUTO = "fuzzy_auto"  # fuzzy score above the auto-match threshold, no Claude needed
    NO_MATCH = "no_match"


@dataclass
class MatchResult:
    inventory_item: dict
    recall: dict
    matched_product: Optional[dict]  # the specific recall_products row that matched, if any
    confidence: MatchConfidence
    fuzzy_score: Optional[float]
    reasoning: str


class ClaudeMatchVerdict(str, Enum):
    """Claude's three-way judgment on a fuzzy candidate — deliberately not a boolean.

    A boolean collapses two very different situations into one "False": Claude confidently
    believes these are different products (e.g. Tylenol vs. Advil — same shape, different
    brand), versus Claude genuinely can't tell either way. Those need different outcomes: a
    confident rejection should produce no alert at all (alerting on it would be a false
    positive that erodes trust), while genuine uncertainty should still reach the user as a
    clearly-flagged low-confidence notice, because a missed real match is worse than an extra
    "you may want to check" message.
    """

    SAME_PRODUCT = "same_product"
    DIFFERENT_PRODUCT = "different_product"
    UNCERTAIN = "uncertain"


class ClaudeMatchJudgment(BaseModel):
    """Claude's structured judgment on an uncertain fuzzy match."""

    verdict: ClaudeMatchVerdict = Field(
        description="same_product only if you have real reason to believe this is genuinely "
        "the same product the user owns — not just a plausible-sounding coincidence. "
        "different_product if you have real reason to believe these are two distinct products "
        "(e.g. different brands, different formulations) even though the text is superficially "
        "similar. uncertain if you genuinely cannot tell either way from the information given."
    )
    reasoning: str = Field(
        description="One or two plain-language sentences a non-technical user could read, "
        "explaining why this is, isn't, or might be the same product."
    )


CLAUDE_MATCH_SYSTEM_PROMPT = """You are helping decide whether a government product recall \
refers to the same product a household has listed in their saved inventory. You will be given \
the recall's product description and the user's saved item description. These strings often \
differ in wording, ordering, or capitalization even when they refer to the same product — but \
they can also look superficially similar while being genuinely different products (e.g. two \
different brands' painkillers with the same dosage-form wording). Judge based on whether the \
brand and product identity are actually the same, not just whether the sentences look alike.

Use "different_product" when you have real reason to believe these are distinct products, not \
just "uncertain" — this matters because a confident rejection is treated differently from \
genuine uncertainty downstream. Reserve "uncertain" for cases where you truly cannot tell \
either way from the information given."""


def _exact_match(inventory_item: dict, recall: dict, products: list[dict]) -> Optional[MatchResult]:
    """Check for an exact UPC or lot-number match between an inventory item and a recall.

    NID matching isn't meaningful here — a user's inventory item never carries a recall NID
    (that's the recall's own identifier, not a product identifier the user would know). NID
    matching belongs in deduplication (DESIGN.md step 3, linking an "Update:" record back to
    its original), not in inventory matching.
    """
    inv_upc = (inventory_item.get("upc") or "").strip()
    inv_lot = (inventory_item.get("lot_number") or "").strip()

    for product in products:
        product_upc = (product["upc"] or "").strip()
        if inv_upc and product_upc and inv_upc == product_upc:
            return MatchResult(
                inventory_item=inventory_item,
                recall=recall,
                matched_product=product,
                confidence=MatchConfidence.EXACT_ID,
                fuzzy_score=None,
                reasoning=f"Exact UPC match ({inv_upc}).",
            )

        product_lots = (product["lot_numbers"] or "")
        if inv_lot and inv_lot in product_lots:
            return MatchResult(
                inventory_item=inventory_item,
                recall=recall,
                matched_product=product,
                confidence=MatchConfidence.EXACT_ID,
                fuzzy_score=None,
                reasoning=f"Exact lot number match ({inv_lot}).",
            )

    return None


def _fuzzy_score(inventory_item: dict, product: dict) -> float:
    inv_str = f"{inventory_item.get('brand') or ''} {inventory_item['product_name']}".strip()
    product_str = f"{product['brand'] or ''} {product['product_name']}".strip()
    return fuzz.WRatio(inv_str, product_str)


def _best_fuzzy_candidate(inventory_item: dict, products: list[dict]) -> Optional[tuple[dict, float]]:
    """The single highest-scoring recall product for this inventory item, if any clear the floor."""
    scored = [(p, _fuzzy_score(inventory_item, p)) for p in products]
    scored = [(p, s) for p, s in scored if s >= FUZZY_REJECT_BELOW]
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[1])


def _ask_claude_to_judge(inventory_item: dict, recall: dict, product: dict) -> ClaudeMatchJudgment:
    inv_desc = f"{inventory_item.get('brand') or '(no brand given)'} — {inventory_item['product_name']}"
    recall_desc = (
        f"Recall title: {recall['title']}\n"
        f"Recall product: {product['brand'] or ''} {product['product_name']}\n"
        f"Recall category/organization: {recall['organization']}"
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=CLAUDE_MATCH_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"User's saved inventory item:\n{inv_desc}\n\n{recall_desc}",
            }
        ],
        output_format=ClaudeMatchJudgment,
    )
    return response.parsed_output


def match_item_to_recall(inventory_item: dict, recall: dict, products: list[dict]) -> MatchResult:
    """Run the full tiered match for one (inventory item, recall) pair.

    `products` is the list of recall_products rows belonging to this recall. If empty (a
    consumer-product recall with no structured table — see DESIGN.md), matching falls back to
    the recall's own title/summary rather than silently reporting no match at all, since a
    plain-text-only recall can still concern a saved item.
    """
    if products:
        exact = _exact_match(inventory_item, recall, products)
        if exact:
            return exact

        candidate = _best_fuzzy_candidate(inventory_item, products)
    else:
        # No structured products for this recall — fuzzy-match against the recall's own title
        # as a last resort, since that's all the source data provides for this category.
        pseudo_product = {"brand": None, "product_name": recall["title"]}
        score = _fuzzy_score(inventory_item, pseudo_product)
        candidate = (pseudo_product, score) if score >= FUZZY_REJECT_BELOW else None

    if candidate is None:
        return MatchResult(
            inventory_item=inventory_item,
            recall=recall,
            matched_product=None,
            confidence=MatchConfidence.NO_MATCH,
            fuzzy_score=None,
            reasoning="No candidate cleared the minimum similarity threshold.",
        )

    product, score = candidate

    if score >= FUZZY_AUTO_MATCH_ABOVE:
        return MatchResult(
            inventory_item=inventory_item,
            recall=recall,
            matched_product=product,
            confidence=MatchConfidence.FUZZY_AUTO,
            fuzzy_score=score,
            reasoning=f"Product names are a very close match (similarity {score:.0f}/100).",
        )

    # Middle band: score is a real candidate but not confident enough to auto-decide either
    # way (see the Tylenol/Advil example in DESIGN.md) — escalate to Claude.
    judgment = _ask_claude_to_judge(inventory_item, recall, product)
    confidence = {
        ClaudeMatchVerdict.SAME_PRODUCT: MatchConfidence.CLAUDE_CONFIRMED,
        ClaudeMatchVerdict.DIFFERENT_PRODUCT: MatchConfidence.CLAUDE_REJECTED,
        ClaudeMatchVerdict.UNCERTAIN: MatchConfidence.CLAUDE_UNCERTAIN,
    }[judgment.verdict]
    return MatchResult(
        inventory_item=inventory_item,
        recall=recall,
        matched_product=product,
        confidence=confidence,
        fuzzy_score=score,
        reasoning=judgment.reasoning,
    )


if __name__ == "__main__":
    from recallradar.database import get_connection

    conn = get_connection()
    inventory = [dict(row) for row in conn.execute("SELECT * FROM inventory").fetchall()]
    recalls = [dict(row) for row in conn.execute("SELECT * FROM recalls").fetchall()]

    for inv in inventory:
        print(f"=== Inventory item: {inv['brand']} {inv['product_name']} ===")
        for recall in recalls:
            products = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM recall_products WHERE recall_nid = ?", (recall["nid"],)
                ).fetchall()
            ]
            result = match_item_to_recall(inv, recall, products)
            if result.confidence != MatchConfidence.NO_MATCH:
                print(f"  [{result.confidence.value}] {recall['title'][:60]}")
                print(f"    score={result.fuzzy_score}  reasoning: {result.reasoning}")
        print()

    conn.close()
