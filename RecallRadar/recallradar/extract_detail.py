"""Fetch each new recall's detail page and use Claude to extract structured product identifiers.

The detail pages present affected-product data very differently by category (see DESIGN.md):
food recalls have a Brand/Product/Size/UPC/Codes table, drug recalls have a differently-shaped
table with Lot Number, medical device recalls use Lot or serial number/Model, and many consumer
product recalls have no table at all — just a prose paragraph. Writing a separate HTML parser
per category would mean hand-coding around every schema variation the government happens to use
today, and silently breaking whenever they change a heading. Instead: pull the page's visible
text (which already contains whatever structure exists, table or prose) and let Claude extract
what's actually there via a structured output schema. When a recall genuinely has no lot number
or UPC, the schema allows that field to come back empty rather than forcing a guess.
"""

from typing import Literal, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from recallradar.config import MODEL, REQUEST_HEADERS, client
from recallradar.database import get_connection, get_recalls_needing_detail, insert_recall_products, mark_detail_fetched


class AffectedProduct(BaseModel):
    """One affected product variant extracted from a recall's detail page."""

    brand: Optional[str] = Field(default=None, description="Brand name, if stated")
    product_name: str = Field(description="The specific product name or variant")
    lot_numbers: Optional[str] = Field(
        default=None,
        description="Lot numbers, serial numbers, or best-before/expiry codes, if any were "
        "listed for this product. Comma-separate if there are multiple.",
    )
    upc: Optional[str] = Field(default=None, description="UPC/barcode, if stated")


class RecallDetailExtraction(BaseModel):
    """Structured extraction from one recall's detail page."""

    affected_products: list[AffectedProduct] = Field(
        description="Every distinct affected product variant listed on the page. If the page "
        "only describes the product in prose with no table of variants, return a single item "
        "built from that description."
    )
    affected_regions: str = Field(
        description="Where the product was distributed (e.g. a province, 'National', or "
        "'Not stated' if the page doesn't say)"
    )
    has_structured_identifiers: bool = Field(
        description="True if the page provided real lot numbers or UPCs for the affected "
        "products; False if this recall only has a prose description with no such identifiers"
    )
    recall_class: Optional[str] = Field(
        default=None,
        description="The page's stated severity, exactly as written — e.g. 'Class 1', "
        "'Class 2', 'Class 3', 'Type I', 'Type II', 'Type III'. Null if the page does not "
        "state one (this happens on a meaningful fraction of real recalls — do not guess).",
    )


EXTRACTION_SYSTEM_PROMPT = """You are extracting structured product data from a Government of \
Canada recall notice page. The page text below may contain a table of affected products (with \
columns like Brand, Product, Size, UPC, Codes, or Lot Number) or, for some consumer product \
recalls, only a prose description with no table at all.

Extract every distinct affected product variant with whatever identifiers are actually present \
on the page. Do not invent a UPC or lot number that isn't there — leave those fields empty if \
the page doesn't provide them. Set has_structured_identifiers to false if the page gives no \
real lot numbers or UPCs, even if you can still describe the product from prose.

Also extract the page's stated "Recall class" field (e.g. Class 1/2/3 or Type I/II/III) if \
present. Many pages do not state one — leave recall_class null rather than inferring a \
severity from the description."""


def fetch_detail_page_text(url: str) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main") or soup

    return main.get_text(separator="\n", strip=True)


def extract_recall_detail(url: str) -> RecallDetailExtraction:
    page_text = fetch_detail_page_text(url)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Recall page content:\n\n{page_text}"}],
        output_format=RecallDetailExtraction,
    )

    return response.parsed_output


def process_pending_details() -> int:
    """Fetch detail pages for every recall not yet processed, extract, and store. Returns count."""
    conn = get_connection()
    pending = get_recalls_needing_detail(conn)

    for recall in pending:
        print(f"Extracting: {recall['title']}")
        try:
            extraction = extract_recall_detail(recall["link"])
        except Exception as e:
            print(f"  Failed to extract {recall['nid']}: {e}")
            continue

        products = [
            {
                "brand": p.brand,
                "product_name": p.product_name,
                "lot_numbers": p.lot_numbers,
                "upc": p.upc,
                "affected_regions": extraction.affected_regions,
            }
            for p in extraction.affected_products
        ]
        insert_recall_products(conn, recall["nid"], products)
        mark_detail_fetched(conn, recall["nid"], extraction.recall_class)
        conn.commit()

        structured = "yes" if extraction.has_structured_identifiers else "no"
        print(f"  {len(products)} product(s) extracted, structured identifiers: {structured}")

    conn.close()
    return len(pending)


if __name__ == "__main__":
    count = process_pending_details()
    print(f"\nProcessed {count} recall(s) needing detail extraction")
