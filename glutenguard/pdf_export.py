"""Export a GlutenGuardResult as a one-page PDF.

Uses fpdf2 — pure Python, no system dependencies (unlike weasyprint, which needs Cairo/Pango
installed) and no dual-license baggage (unlike reportlab). Output is plain text sections, not
a styled document — this is a portable record of one scan someone might keep or hand to
someone else, not a polished report.
"""

from datetime import datetime, timezone

from fpdf import FPDF

from engine import GlutenGuardResult

_CLASSIFICATION_LABEL = {
    "Green": "LIKELY SAFE",
    "Yellow": "NEEDS VERIFICATION",
    "Red": "DO NOT EAT",
}


def _line(pdf: FPDF, height: float, text: str) -> None:
    """multi_cell wrapper that always resets the cursor to the left margin afterward.

    fpdf2's multi_cell leaves the cursor at the end of the last line (not a fresh line) when
    the text is short enough to fit on one line without wrapping — the next multi_cell call
    then has almost no horizontal space left and raises FPDFException. Every call in this
    module goes through here instead of calling multi_cell directly, so that failure mode is
    structurally impossible rather than something to remember to guard case-by-case.
    """
    pdf.multi_cell(0, height, _ascii_safe(text), new_x="LMARGIN", new_y="NEXT")


def build_scan_pdf(result: GlutenGuardResult, scanned_at: str | None = None) -> bytes:
    """Render a GlutenGuardResult to PDF bytes, suitable for st.download_button."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "GlutenGuard Scan Result", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    timestamp = scanned_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 6, f"Scanned: {timestamp}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    _line(pdf, 7, result.product_name)
    pdf.ln(1)

    pdf.set_font("Helvetica", "B", 14)
    label = _CLASSIFICATION_LABEL.get(result.classification, result.classification.upper())
    pdf.cell(0, 8, _ascii_safe(f"{result.classification.upper()} - {label}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    _line(pdf, 6, result.summary)
    pdf.ln(4)

    _section(pdf, "Ingredient-by-ingredient")
    for finding in result.ingredient_analysis:
        pdf.set_font("Helvetica", "B", 10)
        _line(pdf, 5, f"{finding.ingredient} ({finding.gluten_status})")
        pdf.set_font("Helvetica", "", 10)
        _line(pdf, 5, finding.reasoning)
        pdf.ln(1)
    pdf.ln(3)

    _section(pdf, "Cross-contamination")
    pdf.set_font("Helvetica", "", 10)
    _line(pdf, 5, result.cross_contamination_warning or "None noted on label.")
    pdf.ln(3)

    _section(pdf, "Why this classification")
    pdf.set_font("Helvetica", "", 10)
    for reason in result.reasons_for_classification:
        _line(pdf, 5, f"- {reason}")
    pdf.ln(3)

    pdf.set_font("Helvetica", "I", 9)
    _line(pdf, 5, result.mandatory_reminder)

    return bytes(pdf.output())


def _section(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")


# Core Helvetica in fpdf2 only supports latin-1. Claude's output (and any literal text in this
# module) can include common typographic characters outside that range — map the frequent ones
# to a plain-ASCII equivalent so they render as sensible punctuation instead of "?", then fall
# back to "?" only for genuinely unmappable characters (rare, but shouldn't crash the export).
_UNICODE_REPLACEMENTS = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‘": "'",  # left single quote
    "’": "'",  # right single quote
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "…": "...",  # ellipsis
    " ": " ",  # non-breaking space
}


def _ascii_safe(text: str) -> str:
    for unicode_char, ascii_equivalent in _UNICODE_REPLACEMENTS.items():
        text = text.replace(unicode_char, ascii_equivalent)
    return text.encode("latin-1", errors="replace").decode("latin-1")
