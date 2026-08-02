"""GlutenGuard — Streamlit UI.

Wires a UI around the classification engine in engine.py. Supports two input methods (photo
upload and pasted text, side by side, not either/or), leads with a plain-language, color-coded
verdict, and tucks the full ingredient-by-ingredient breakdown behind an expander so the result
is scannable at a glance but the detail is one click away.
"""

import tempfile
from pathlib import Path

import streamlit as st

from engine import GlutenGuardResult, classify_ingredient_list, classify_label_image

# Plain-language labels for the primary verdict — the technical Green/Yellow/Red classification
# still drives the logic and shows up in the detail view, but it is not the headline.
VERDICT_COPY = {
    "Green": ("🟢 Likely Safe", "success"),
    "Yellow": ("🟡 Needs Verification", "warning"),
    "Red": ("🔴 Do Not Eat", "error"),
}


def render_result(result: GlutenGuardResult) -> None:
    """Render a GlutenGuardResult: verdict first, full detail behind an expander."""
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


def save_uploaded_file(uploaded_file) -> str:
    """Write a Streamlit UploadedFile to a temp path so classify_label_image can read it."""
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


st.set_page_config(page_title="GlutenGuard", page_icon="🌾")

st.title("GlutenGuard")
st.write(
    "Upload a photo of a product label, or paste the ingredient list below. GlutenGuard "
    "checks it for gluten and cross-contamination risk."
)

uploaded_file = st.file_uploader("Upload a label photo", type=["jpg", "jpeg", "png", "webp"])
if uploaded_file is not None:
    st.image(uploaded_file, caption="Uploaded label", width=300)

text_input = st.text_area("Or paste the ingredient list here")

if st.button("Check"):
    if uploaded_file is None and not text_input.strip():
        st.warning("Upload a label photo or paste an ingredient list first.")
    else:
        with st.spinner("Checking label..."):
            try:
                if uploaded_file is not None:
                    image_path = save_uploaded_file(uploaded_file)
                    result = classify_label_image(image_path)
                else:
                    result = classify_ingredient_list(text_input)
            except (ValueError, FileNotFoundError) as e:
                st.error(f"Could not check this label: {e}")
            else:
                render_result(result)

st.caption(
    "GlutenGuard is not a medical device and does not replace reading the physical package. "
    "Always verify with the manufacturer if you are uncertain."
)
