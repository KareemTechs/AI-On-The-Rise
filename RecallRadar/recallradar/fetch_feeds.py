"""Fetch CFIA, health products, and consumer products RSS feeds and combine into one list.

Each of the three feeds is a filtered view of the same Government of Canada recalls system
(see DESIGN.md) — this module fetches all three and normalizes them into one common shape so
the rest of the pipeline doesn't need to know which feed a record came from.

Note: these RSS feeds only carry the ~3 most recent items per category (confirmed in DESIGN.md).
That's fine for this week's goal (a working fetch-and-combine pipeline) but means this is a
low-latency nudge, not a complete history — the bulk JSON feed is the system of record for
catching up after a gap, and is a natural Week 2 addition rather than something to fake here.
"""

from dataclasses import dataclass

import feedparser

from recallradar.config import RSS_FEEDS


@dataclass
class RecallRecord:
    """One recall notice, normalized across whichever feed it came from."""

    nid: str
    title: str
    link: str
    summary: str
    organization: str
    published: str
    source_feed: str


def fetch_feed(source_feed: str, url: str) -> list[RecallRecord]:
    """Fetch and parse a single RSS feed into a list of RecallRecord."""
    parsed = feedparser.parse(url)

    if parsed.bozo:
        print(f"Warning: {source_feed} feed may be malformed ({parsed.bozo_exception})")

    records = []
    for entry in parsed.entries:
        records.append(
            RecallRecord(
                nid=entry.get("id", ""),
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                summary=entry.get("summary", ""),
                organization=entry.get("author", source_feed),
                published=entry.get("published", ""),
                source_feed=source_feed,
            )
        )
    return records


def fetch_all_feeds() -> list[RecallRecord]:
    """Fetch every configured feed and combine into one deduplicated list.

    Deduplicates on NID within this fetch — the health products and consumer products feeds
    both draw from the same underlying system as CFIA, so it's possible (if unlikely, given
    how the feeds are filtered) for the same NID to show up twice in one run.
    """
    combined: dict[str, RecallRecord] = {}

    for source_feed, url in RSS_FEEDS.items():
        for record in fetch_feed(source_feed, url):
            if record.nid:
                combined[record.nid] = record

    return list(combined.values())


if __name__ == "__main__":
    all_records = fetch_all_feeds()

    print(f"Fetched {len(all_records)} unique recalls across {len(RSS_FEEDS)} feeds")
    print("-" * 60)

    for record in all_records:
        print(f"NID:          {record.nid}")
        print(f"Title:        {record.title}")
        print(f"Organization: {record.organization}")
        print(f"Source feed:  {record.source_feed}")
        print(f"Published:    {record.published}")
        print(f"Link:         {record.link}")
        print("-" * 60)
