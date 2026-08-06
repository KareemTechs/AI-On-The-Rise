# Demo: match two slightly different product name strings with rapidfuzz.

from rapidfuzz import fuzz

EXAMPLE_PAIRS = [
    (
        "Coaticook White Cheddar Cheese Curds",
        "Coaticook cheddar curds - white",
        "same product, different word order/phrasing (should match)",
    ),
    (
        "Hershey Kisses Creamy Milk Chocolate",
        "Hersheys Kisses Milk Chocolate",
        "same product, minor spelling/wording difference (should match)",
    ),
    (
        "Tylenol Extra Strength Caplets",
        "Advil Extra Strength Tablets",
        "different products, similar sentence structure (should NOT match)",
    ),
]


if __name__ == "__main__":
    for recall_name, inventory_name, note in EXAMPLE_PAIRS:
        ratio = fuzz.ratio(recall_name, inventory_name)
        token_sort = fuzz.token_sort_ratio(recall_name, inventory_name)
        weighted = fuzz.WRatio(recall_name, inventory_name)

        print(f"Recall product:    {recall_name}")
        print(f"Inventory product: {inventory_name}")
        print(f"Note:              {note}")
        print(f"  ratio (char-level):        {ratio:5.1f}")
        print(f"  token_sort_ratio:          {token_sort:5.1f}")
        print(f"  WRatio (weighted overall): {weighted:5.1f}")
        print("-" * 60)
