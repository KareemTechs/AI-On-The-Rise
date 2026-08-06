"""Shared configuration: RSS feed URLs, file paths, and the Anthropic client."""

from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# .env lives at the AI-On-The-Rise project root (one level up from RecallRadar/), which is
# where every other project in this repo keeps its shared API key. load_dotenv() walks up
# from the current working directory to find it, so this works regardless of where a script
# is launched from.
load_dotenv()

client = Anthropic()
MODEL = "claude-opus-4-8"

# The three feeds this week's fetcher combines. Each maps to an Organization value in the
# government's bulk open-data feed (see DESIGN.md) — these RSS feeds are filtered views of
# the same underlying system, not separate integrations.
RSS_FEEDS = {
    "CFIA": "https://recalls-rappels.canada.ca/en/feed/cfia-alerts-recalls",
    "Health products": "https://recalls-rappels.canada.ca/en/feed/health-products-alerts-recalls",
    "Consumer products": "https://recalls-rappels.canada.ca/en/feed/consumer-products-alerts-recalls",
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "recallradar.db"

# A polite, identifiable User-Agent for fetching government pages directly (not through an
# API) — good practice for any script that isn't a browser.
REQUEST_HEADERS = {"User-Agent": "RecallRadar/0.1 (personal project; contact via GitHub)"}
