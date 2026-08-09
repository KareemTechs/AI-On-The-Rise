# 📡 RecallRadar

RecallRadar is an agentic product-safety monitoring system for Canadian households. It checks official Government of Canada recall feeds, compares affected products against a saved household inventory, and generates prioritized alerts when something at home may be affected.

> **Important:** RecallRadar is an educational decision-support project. It does not replace official government recall notices, manufacturer instructions, or professional medical advice.

---

## What It Is and Who It Is For

RecallRadar is designed for a Canadian parent responsible for the food, medication, and household products used by their family. Instead of manually checking multiple government recall pages, the parent saves products in a household inventory and RecallRadar checks whether any new official recall may affect something they own.

**Returns:** Confirmed recall alerts · Possible-match warnings · Match confidence and reasoning · Affected UPC/lot information · Recommended action · Official government source

---

## How It Works

RecallRadar fetches recent CFIA food, Health Canada health-product, and consumer-product recall feeds and converts them into one consistent format. It removes duplicate records, stores new recalls in SQLite, and visits each official detail page so Claude can extract affected brands, products, UPCs, lot numbers, regions, and any stated recall class. The system checks saved household products for exact identifier matches, uses fuzzy matching when product names differ, and sends only ambiguous candidates to Claude for a `same_product`, `different_product`, or `uncertain` decision. It then combines match confidence with recall severity, generates an appropriate alert, preserves the official source link, and prevents duplicate alerts.

```
Fetch feeds → normalize and deduplicate → store recalls → extract detail pages
→ match inventory → evaluate ambiguous cases → score priority → generate alerts
```

---

## Project Structure

```
recallradar/
├── app.py             # Streamlit dashboard for alerts, inventory, and pipeline controls
├── pipeline.py        # Runs the complete RecallRadar workflow in the correct order
├── fetch_feeds.py     # Fetches, normalizes, and deduplicates government RSS records
├── database.py        # Defines the SQLite schema and database operations
├── extract_detail.py  # Retrieves recall pages and extracts product details with Claude
├── matching.py        # Performs exact, fuzzy, and Claude-assisted product matching
├── alerts.py          # Builds and persists user-facing recall alerts
├── inventory.py       # Validates and stores household inventory items
├── priority.py        # Combines recall severity and match confidence into a priority
└── config.py          # Stores feed URLs, paths, request settings, and API configuration
```

---

## Dashboard

Launch the Streamlit dashboard from the repository root with `streamlit run recallradar/app.py`. The dashboard shows confirmed alerts first, separates uncertain matches, displays an all-clear state when nothing matches, shows when the pipeline last ran, lets the user add and view household inventory, and includes a button to run the full pipeline and refresh the results.

---

## How to Run It

**1. Install the dependencies**

```bash
pip install anthropic python-dotenv feedparser requests beautifulsoup4 pydantic rapidfuzz streamlit
```

**2. Add the API key**

Create a `.env` file in the repository root:

```
ANTHROPIC_API_KEY=your-key-here
```

> Never commit `.env` or an API key to GitHub.

**3. Run the dashboard**

```bash
streamlit run recallradar/app.py
```

**4. Run only the pipeline**

```bash
python -m recallradar.pipeline
```

The pipeline runs feed ingestion, detail extraction, inventory matching, priority scoring, and alert generation in order. It returns a summary:

```python
{
    "new_recalls": 0,
    "details_extracted": 0,
    "alerts_generated": 0,
    "alerts_suppressed": 0,
}
```

---

## Safety Limitations

- RecallRadar is a decision-support tool, not a guarantee that a product is safe or recalled.
- A matching product name or fuzzy score is only a possible match — the UPC, lot, size, model, and dates must still be checked against the official notice.
- Government pages can be incomplete, updated, malformed, or unusually structured, which may affect extraction quality.
- Some recall notices provide no structured UPC or lot information.
- RSS feeds contain only recent notices and should not be treated as a complete historical record.
- AI-generated extraction and matching decisions can be wrong.
- RecallRadar currently monitors Canadian recall sources only.

---

## Responsible Use

RecallRadar uses deterministic identifiers before AI and sends only ambiguous product descriptions to Claude. It preserves uncertainty rather than forcing every comparison into a yes/no answer, never intentionally invents missing identifiers or severity, suppresses confidently rejected matches, and clearly labels uncertain alerts. Every alert retains the official Government of Canada link as the source of truth. Users must compare their physical product with the official notice and follow the agency or manufacturer's instructions.
