"""Simple add/list interface for a household's saved products.

Per DESIGN.md, inventory input is category-aware in the full design (DIN lookup for
medications, Open Food Facts for food, manual entry for household items) — but every one of
those paths ends at the same place: a product_name + brand + category saved to the inventory
table. This week builds that shared core (add and list), which the category-specific lookups
from the design doc will sit in front of later without changing the storage shape.
"""

from recallradar.database import get_connection, get_inventory, insert_inventory_item

VALID_CATEGORIES = {"food", "medication", "household"}


def add_item(
    product_name: str,
    brand: str,
    category: str,
    upc: str | None = None,
    lot_number: str | None = None,
) -> int:
    """Add a product to the household inventory. Returns the new item's row id.

    upc and lot_number are optional — most users won't have a lot number on hand at add-time,
    but when they do (or when a barcode lookup succeeds, per the category-aware lookups in
    DESIGN.md) it enables exact matching instead of relying on fuzzy name matching alone.
    """
    if not product_name or not product_name.strip():
        raise ValueError("product_name must be non-empty")

    category = category.strip().lower()
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}, got {category!r}")

    conn = get_connection()
    item_id = insert_inventory_item(
        conn,
        product_name.strip(),
        brand.strip() if brand else None,
        category,
        upc.strip() if upc else None,
        lot_number.strip() if lot_number else None,
    )
    conn.commit()
    conn.close()
    return item_id


def list_items():
    conn = get_connection()
    items = get_inventory(conn)
    conn.close()
    return items


def print_inventory():
    items = list_items()
    if not items:
        print("No items saved yet.")
        return

    print(f"{'ID':4s} {'Category':11s} {'Brand':20s} Product")
    print("-" * 70)
    for item in items:
        brand = item["brand"] or "-"
        print(f"{item['id']:<4d} {item['category']:11s} {brand:20s} {item['product_name']}")


if __name__ == "__main__":
    # A few sample items reflecting the three MVP categories from DESIGN.md.
    add_item("White Cheddar Cheese Curds", "Coaticook", "food")
    add_item("Extra Strength Caplets", "Tylenol", "medication")
    add_item("Automatic Toilet Bowl Cleaner", "Ultra Big Blue", "household")

    print_inventory()
