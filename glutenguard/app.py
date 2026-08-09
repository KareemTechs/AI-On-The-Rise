"""GlutenGuard — Streamlit UI.

Wires a UI around the classification engine in engine.py. Supports two input methods (photo
upload and pasted text, side by side, not either/or), leads with a plain-language, color-coded
verdict, and tucks the full ingredient-by-ingredient breakdown behind an expander so the result
is scannable at a glance but the detail is one click away.

The latest result is kept in st.session_state (not a local variable) because Streamlit reruns
this whole script on every interaction — clicking "Download PDF" or expanding history would
otherwise wipe out the just-computed result before the download button had anything to offer.
"""

import tempfile
from pathlib import Path

import streamlit as st

from database import clear_history, get_connection, get_scan_history, load_scan_result, save_scan
from engine import GlutenGuardResult, classify_ingredient_list, classify_label_image
from pdf_export import build_scan_pdf

# Plain-language labels for the primary verdict — the technical Green/Yellow/Red classification
# still drives the logic and shows up in the detail view, but it is not the headline.
VERDICT_COPY = {
    "Green": ("🟢 Likely Safe", "success"),
    "Yellow": ("🟡 Needs Verification", "warning"),
    "Red": ("🔴 Do Not Eat", "error"),
}

CLASSIFICATION_ICON = {"Green": "🟢", "Yellow": "🟡", "Red": "🔴"}

# Dark mode here is a CSS override layered on top of Streamlit's own theme, not a native theme
# switch — Streamlit only reads .streamlit/config.toml at process start, it has no supported
# runtime theme API. This toggle is honestly cosmetic (as scoped), so a CSS injection that
# covers the main content area is the right amount of engineering for it.
DARK_CSS = """
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    .stTextArea textarea, .stTextInput input { background-color: #262730; color: #fafafa; }
    .stMarkdown, .stCaption, p, span, label { color: #fafafa !important; }
</style>
"""


def render_result(result: GlutenGuardResult) -> None:
    """Render a GlutenGuardResult: detected product, then verdict, then detail behind an expander."""
    st.caption(f"Analyzing: {result.product_name}")

    label, style = VERDICT_COPY.get(result.classification, ("❓ Unknown", "warning"))
    display = getattr(st, style)
    display(label)
    st.write(result.summary)

    with st.expander("See full ingredient breakdown"):
        st.subheader("Ingredient-by-ingredient")
        for finding in result.ingredient_analysis:
            st.markdown(f"- **{finding.ingredient}** ({finding.gluten_status}) — {finding.reasoning}")

        st.subheader("Cross-contamination")
        st.write(result.cross_contamination_warning or "None noted on label.")

        st.subheader("Why this classification")
        for reason in result.reasons_for_classification:
            st.markdown(f"- {reason}")

        st.caption(f"⚠️ {result.mandatory_reminder}")

    st.download_button(
        "📄 Download PDF",
        data=build_scan_pdf(result),
        file_name=f"glutenguard_{result.product_name[:40].strip().replace(' ', '_')}.pdf",
        mime="application/pdf",
    )


def save_uploaded_file(uploaded_file) -> str:
    """Write a Streamlit UploadedFile to a temp path so classify_label_image can read it."""
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


# Three known-good examples spanning the tool's range, so a first-time user with nothing to
# paste can still see what it does in one click. Same ingredient lists already validated in
# earlier testing (see GlutenGuard.ipynb's smoke tests) — reused here rather than inventing
# new ones, so the "example" behavior is backed by cases already confirmed to classify as
# expected.
EXAMPLE_LABELS = {
    "🟢 Green example": (
        "Ingredients: Rice, Water, Salt.\n"
        "No allergen statement present. Not manufactured in a shared facility."
    ),
    "🟡 Yellow example": (
        "Ingredients: Corn Starch, Natural Flavors, Modified Food Starch, Salt, Spices.\n"
        "Manufactured in a facility that also processes wheat."
    ),
    "🔴 Red example": (
        "Ingredients: Enriched Wheat Flour (Wheat Flour, Niacin, Reduced Iron, Thiamine\n"
        "Mononitrate, Riboflavin, Folic Acid), Sugar, Vegetable Oil, Salt.\n"
        "Allergen statement: Contains Wheat."
    ),
}


def _load_example(text: str) -> None:
    # Setting session_state in a button's on_click callback, before the widget below is
    # instantiated on rerun, is the supported way to programmatically populate a text_area in
    # Streamlit — assigning to it directly after creation raises an exception.
    st.session_state["ingredient_text_input"] = text


st.set_page_config(page_title="GlutenGuard", page_icon="🌾")

if st.session_state.get("dark_mode"):
    st.markdown(DARK_CSS, unsafe_allow_html=True)

top_left, top_right = st.columns([4, 1])
with top_left:
    st.title("GlutenGuard")
with top_right:
    st.toggle("🌙 Dark", key="dark_mode")

st.write(
    "Upload a photo of a product label, or paste the ingredient list below. GlutenGuard "
    "checks it for gluten and cross-contamination risk."
)

uploaded_file = st.file_uploader("Upload a label photo", type=["jpg", "jpeg", "png", "webp"])
if uploaded_file is not None:
    st.image(uploaded_file, caption="Uploaded label", width=300)

st.caption("New here? Try an example:")
example_cols = st.columns(len(EXAMPLE_LABELS))
for col, (label, text) in zip(example_cols, EXAMPLE_LABELS.items()):
    col.button(label, on_click=_load_example, args=(text,), use_container_width=True)

text_input = st.text_area("Or paste the ingredient list here", key="ingredient_text_input")

if st.button("Check"):
    if uploaded_file is None and not text_input.strip():
        st.warning("Upload a label photo or paste an ingredient list first.")
        st.session_state.pop("last_result", None)
    else:
        with st.spinner("Analyzing ingredients for gluten..."):
            try:
                if uploaded_file is not None:
                    image_path = save_uploaded_file(uploaded_file)
                    result = classify_label_image(image_path)
                    input_type = "photo"
                else:
                    result = classify_ingredient_list(text_input)
                    input_type = "text"
            except (ValueError, FileNotFoundError) as e:
                st.error(f"Could not check this label: {e}")
                st.session_state.pop("last_result", None)
            else:
                conn = get_connection()
                save_scan(conn, result, input_type)
                conn.close()
                st.session_state["last_result"] = result

if "last_result" in st.session_state:
    render_result(st.session_state["last_result"])

st.divider()

with st.expander("🕘 Scan history"):
    conn = get_connection()
    history = get_scan_history(conn)

    if not history:
        st.caption("No scans yet — check a label above to start building history.")
    else:
        if st.button("Clear history"):
            clear_history(conn)
            st.rerun()

        for row in history:
            icon = CLASSIFICATION_ICON.get(row["classification"], "❓")
            with st.container(border=True):
                st.markdown(f"{icon} **{row['product_name']}** — {row['scanned_at']}")
                st.caption(row["summary"])
                if st.button("View full result", key=f"view_{row['id']}"):
                    st.session_state["last_result"] = load_scan_result(row)
                    st.rerun()

    conn.close()

st.caption(
    "GlutenGuard is not a medical device and does not replace reading the physical package. "
    "Always verify with the manufacturer if you are uncertain."
)
