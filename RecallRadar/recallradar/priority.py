"""Priority scoring: combine recall severity (recall_class) with match confidence.

Per DESIGN.md step 6, this tier is what ultimately decides whether the user gets a
notification and how urgently it's framed. Two independent signals feed it:

  - Severity, from the recall's own `recall_class` (Class 1/Type I = most severe). This is
    missing on a meaningful fraction of real recalls (confirmed in DESIGN.md and reproduced
    live in extract_detail.py — 3 of 8 recalls fetched this session had no stated class), so
    unknown severity must default to something safety-conservative, not silently "low."
  - Match confidence, from matching.py's MatchConfidence tiers — an exact UPC match is trusted
    more than a Claude "likely" judgment, which is trusted more than a Claude "uncertain" one.

The result is a PriorityTier used both to decide whether to alert at all, and to choose the
plain-language framing (the Green/Yellow/Red-style pattern already validated in GlutenGuard).
"""

from enum import Enum

from recallradar.matching import MatchConfidence


class Severity(str, Enum):
    HIGH = "high"  # Class 1 / Type I — most severe
    MEDIUM = "medium"  # Class 2 / Type II
    LOW = "low"  # Class 3 / Type III
    UNKNOWN = "unknown"  # not stated on the recall page


class PriorityTier(str, Enum):
    URGENT = "urgent"  # notify immediately, strongest framing
    STANDARD = "standard"  # notify, normal framing
    LOW_CONFIDENCE = "low_confidence"  # notify, but flag the uncertainty explicitly
    SUPPRESSED = "suppressed"  # do not notify (confidence too weak, or ruled out, to act on)


# recall_class strings are extracted verbatim by extract_detail.py's Claude call, so this maps
# the exact phrasings that show up on real recall pages (confirmed live: "Class 1", "Type II",
# etc.) to a severity tier.
_CLASS_TO_SEVERITY = {
    "class 1": Severity.HIGH,
    "type i": Severity.HIGH,
    "class 2": Severity.MEDIUM,
    "type ii": Severity.MEDIUM,
    "class 3": Severity.LOW,
    "type iii": Severity.LOW,
}


def classify_severity(recall_class: str | None) -> Severity:
    if not recall_class:
        return Severity.UNKNOWN
    return _CLASS_TO_SEVERITY.get(recall_class.strip().lower(), Severity.UNKNOWN)


# Priority table: severity -> tier, applied only once a confidence tier has already been
# determined to warrant scoring at all (see score_priority below).
#
# Reasoning for the shape of this table, per DESIGN.md step 6:
#   - Unknown severity is treated as at least STANDARD, never SUPPRESSED — defaulting missing
#     safety data to "safe to ignore" is the wrong direction to default. A confident match on a
#     recall of unknown severity is still real evidence something the user owns was recalled.
_PRIORITY_TABLE: dict[Severity, PriorityTier] = {
    Severity.HIGH: PriorityTier.URGENT,
    Severity.MEDIUM: PriorityTier.STANDARD,
    Severity.LOW: PriorityTier.STANDARD,
    Severity.UNKNOWN: PriorityTier.STANDARD,
}

# Confidence tiers that never produce an alert, regardless of severity:
#   - NO_MATCH: nothing was found to prioritize.
#   - CLAUDE_REJECTED: Claude looked at a fuzzy candidate and concluded, with real reason,
#     that it's a *different* product (e.g. Tylenol vs. Advil — see matching.py's
#     ClaudeMatchVerdict). That's a confident negative, not doubt, and is deliberately handled
#     differently from CLAUDE_UNCERTAIN below — alerting on a rejected match would be a false
#     positive that erodes the user's trust in every future alert.
_SUPPRESSED_CONFIDENCE = {MatchConfidence.NO_MATCH, MatchConfidence.CLAUDE_REJECTED}


def score_priority(recall_class: str | None, confidence: MatchConfidence) -> PriorityTier:
    """Combine recall severity and match confidence into one priority tier."""
    if confidence in _SUPPRESSED_CONFIDENCE:
        return PriorityTier.SUPPRESSED

    if confidence == MatchConfidence.CLAUDE_UNCERTAIN:
        # Claude genuinely couldn't tell either way — always LOW_CONFIDENCE regardless of
        # severity, surfaced with the uncertainty stated explicitly rather than hidden or
        # presented as a firm alert. Mirrors GlutenGuard's principle of never asserting more
        # confidence than the evidence supports.
        return PriorityTier.LOW_CONFIDENCE

    severity = classify_severity(recall_class)
    return _PRIORITY_TABLE[severity]


if __name__ == "__main__":
    test_cases = [
        ("Class 1", MatchConfidence.EXACT_ID),
        ("Type II", MatchConfidence.FUZZY_AUTO),
        (None, MatchConfidence.CLAUDE_CONFIRMED),
        ("Class 3", MatchConfidence.CLAUDE_UNCERTAIN),
        ("Class 2", MatchConfidence.CLAUDE_REJECTED),
        ("Class 1", MatchConfidence.NO_MATCH),
    ]

    for recall_class, confidence in test_cases:
        severity = classify_severity(recall_class)
        tier = score_priority(recall_class, confidence)
        print(f"recall_class={recall_class!r:10s} confidence={confidence.value:18s} "
              f"-> severity={severity.value:8s} priority={tier.value}")
