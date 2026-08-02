"""GlutenGuard classification engine.

Given either a pasted ingredient list or a photo of a product label, classifies the product
as Green, Yellow, or Red for celiac disease safety, with an ingredient-by-ingredient
explanation, cross-contamination notes, and a mandatory reminder to verify the physical
package before eating.

This module is the single source of truth for the classification logic — the Streamlit app
(app.py) imports directly from here rather than duplicating the prompt, schema, or API calls.
"""

import base64
from pathlib import Path
from textwrap import dedent
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from anthropic import Anthropic

# Reads ANTHROPIC_API_KEY from a .env file (or the environment). load_dotenv() searches the
# current working directory and its parents, so this works whether the app is launched from
# this folder or the project root.
load_dotenv()

client = Anthropic()
model = "claude-sonnet-4-6"


class IngredientFinding(BaseModel):
    """Gluten-status verdict for a single ingredient or listed term."""

    ingredient: str = Field(description="The ingredient or term as it appears on the label")
    gluten_status: Literal["contains_gluten", "gluten_free", "uncertain"]
    reasoning: str = Field(description="One sentence explaining the verdict for this ingredient")


class GlutenGuardResult(BaseModel):
    """Structured GlutenGuard classification for one product label."""

    classification: Literal["Green", "Yellow", "Red"]
    summary: str = Field(description="One to two sentence plain-language explanation")
    ingredient_analysis: list[IngredientFinding]
    cross_contamination_warning: Optional[str] = Field(
        default=None,
        description="Any 'may contain', shared-facility, or shared-equipment language found "
        "on the label, or null if none is present",
    )
    reasons_for_classification: list[str] = Field(
        description="Bulleted list of the specific reasons driving the classification"
    )
    mandatory_reminder: str = Field(
        description="Reminder to verify the package before consuming"
    )


SYSTEM_PROMPT = dedent("""
    You are GlutenGuard, an assistant that helps people with celiac disease decide whether a
    packaged food is safe to eat, based on the ingredient list and any allergen or warning
    statements from the product label.

    You will be given the raw text of a product's ingredient list, and possibly accompanying
    allergen or warning statements (e.g. "Contains: Wheat", "May contain traces of gluten",
    "Manufactured in a facility that also processes wheat").

    Classify the product into exactly one of three categories:

    - Green: No gluten-containing ingredients and no gluten/wheat warnings of any kind. You are
      confident, based on the label alone, that the product is gluten-free.
    - Yellow: The label is ambiguous, incomplete, or contains an ingredient of uncertain gluten
      status (e.g. "natural flavors", "modified food starch" without a named source, "malt"
      without specifying the source, "dextrin"), OR the label includes a "may contain",
      shared-facility, or shared-equipment warning.
    - Red: The ingredient list contains an explicit gluten-containing ingredient (wheat,
      barley, rye, malt from barley, brewer's yeast, etc.) or an explicit "Contains: Wheat" /
      gluten allergen statement.

    CRITICAL SAFETY RULE — be conservative:
    - If you are not certain an ingredient is gluten-free, classify as Yellow. Never output
      Green unless every single ingredient is unambiguously gluten-free AND there is no
      cross-contamination warning.
    - Treat any ingredient name you do not recognize as uncertain, not as safe.
    - When genuinely uncertain, prefer Yellow over Red as well — only classify Red when there
      is direct, explicit evidence of gluten content in the ingredients or warnings. Do not
      guess your way to Red on a hunch.

    For every ingredient (or ambiguous term) in the list, provide a gluten-status verdict and a
    short reason. Quote or summarize any cross-contamination warning found on the label. List
    the specific reasons driving the overall classification. Always include a reminder that the
    user must still verify the package, manufacturer information, and certified gluten-free
    status before consuming — this assessment is not a substitute for that.
""").strip()

MANDATORY_REMINDER = (
    "This is not a substitute for checking the package yourself. Before eating, verify the "
    "ingredient list and allergen statement on the physical package (formulations change), "
    "check the manufacturer's gluten-free info if you're unsure, and look for a certified "
    "gluten-free label. This tool cannot detect all cross-contamination risks."
)

IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def classify_ingredient_list(ingredient_text: str) -> GlutenGuardResult:
    """Classify a raw ingredient list as Green/Yellow/Red for celiac disease safety.

    Args:
        ingredient_text: Raw ingredient list, optionally including allergen/warning
            statements, as plain text.

    Returns:
        A GlutenGuardResult with the classification and a full explanation.
    """
    if not ingredient_text or not ingredient_text.strip():
        raise ValueError("ingredient_text must be non-empty")

    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Ingredient list and label text:\n\n{ingredient_text.strip()}",
            }
        ],
        output_format=GlutenGuardResult,
    )

    result = response.parsed_output
    result.mandatory_reminder = MANDATORY_REMINDER
    return result


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def classify_label_image(image_path: str) -> GlutenGuardResult:
    """Classify a photo of a product label as Green/Yellow/Red for celiac disease safety.

    Args:
        image_path: Path to a JPEG, PNG, GIF, or WEBP photo of the ingredient list / label.

    Returns:
        A GlutenGuardResult with the classification and a full explanation.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(
            f"Unsupported image type '{path.suffix}'. Supported: "
            f"{', '.join(sorted(IMAGE_MEDIA_TYPES))}"
        )

    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": encode_image(image_path),
                        },
                    },
                    {
                        "type": "text",
                        "text": "Ingredient list and label text from this image:",
                    },
                ],
            }
        ],
        output_format=GlutenGuardResult,
    )

    result = response.parsed_output
    result.mandatory_reminder = MANDATORY_REMINDER
    return result
