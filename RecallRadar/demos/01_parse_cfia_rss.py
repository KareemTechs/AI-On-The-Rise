# Demo: parse the CFIA recalls RSS feed with feedparser.

import feedparser

CFIA_FEED_URL = "https://recalls-rappels.canada.ca/en/feed/cfia-alerts-recalls"

def fetch_cfia_recalls():
    feed = feedparser.parse(CFIA_FEED_URL)

    if feed.bozo:
        # bozo is feedparser's flag for "this XML was malformed"
        # even though feedparser will still hand back whatever it could parse.
        print(f"Warning: feed may be malformed ({feed.bozo_exception})")

    return feed


feed = fetch_cfia_recalls()

print(f"Feed title: {feed.feed.get('title')}")
print(f"Entries returned: {len(feed.entries)}")
print("-" * 60)

for entry in feed.entries[:2]:
    print(f"NID:        {entry.get('id')}")
    print(f"Title:      {entry.get('title')}")
    print(f"Published:  {entry.get('published')}")
    print(f"Link:       {entry.get('link')}")
    print(f"Summary:    {entry.get('summary')}")
    print("-" * 60)
