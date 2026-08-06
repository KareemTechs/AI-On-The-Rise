# RecallRadar — Design Document

## What this is

RecallRadar watches Canadian government recall data (food, medications, medical devices,
consumer products) and alerts a household when something they own has been recalled — without
them having to check a government website themselves.

**User**: a Canadian parent responsible for buying food, medication, and household products for
their family. They save what their household regularly uses; RecallRadar tells them when one of
those items is recalled, why, and what to do.

**Scope for the MVP**: Canada only. Food, drugs, medical devices, and consumer products.
Vehicles (Transport Canada) are excluded — different risk profile, different user, and the
largest single category in the data, so cutting it keeps the matching problem focused on
products a parent actually keeps in their home.

This document is deliberately implementation-adjacent but not implementation itself — every
section below has already been checked against the real, live data sources. Nothing here is
speculative about what the government feeds contain; where the data has a gap, that gap is
named as a gap, not designed around optimistically.

---

## Data sources (confirmed live)

Canada does not run separate CFIA and Health Canada recall systems. As of the Recalls and
Safety Alerts Management System (RSAMS) modernization, CFIA, Health Canada, Transport Canada,
and Environment and Climate Change Canada all publish into **one** system at
`recalls-rappels.canada.ca`, distinguished by an `Organization` field. "CFIA feed" and "Health
Canada feed" are filters on the same underlying data, not two integrations.

### Bulk feed (primary source)

- `https://recalls-rappels.canada.ca/sites/default/files/opendata-donneesouvertes/HCRSAMOpenData.json`
  (CSV twin also available)
- No key, no auth. Verified live: 33,883 records, ~15 MB, served with proper `ETag` /
  `Last-Modified` headers.
- Fields: `NID, Title, URL, Organization, Product, Issue, "What you should do", Category,
  "Recall class", "Last updated", Archived`.
- Relevant `Organization` values: `CFIA` (food), `Consumer product safety`, `Medical devices`,
  `Drugs and health products`. (`TC` = vehicles, excluded from scope.)
- Realistic volume excluding vehicles: roughly 40–50 new or updated records per month across
  all four in-scope organizations combined. This is a small, pollable dataset — not a firehose.

**Why bulk feed over RSS as the primary source:** the RSS feeds
(e.g. `https://recalls-rappels.canada.ca/en/feed/cfia-alerts-recalls`, confirmed live, valid
RSS 2.0) only return the ~3 most recent items per category. That's fine as a fast
"did-anything-just-happen" signal, but it cannot be relied on for completeness — if the poller
misses one run, an item can roll off the RSS feed before it's ever seen. The bulk feed is the
system of record; RSS is a nice-to-have low-latency nudge on top of it, not a replacement.

### Per-recall detail pages (secondary source, fetched selectively)

The bulk feed's `Product` field is free text with no structured identifiers — no UPC, no lot
number. Those live only on each recall's individual detail page
(`https://recalls-rappels.canada.ca/en/alert-recall/<slug>`), inside an HTML table. Confirmed
live, and confirmed **the table schema is not consistent across categories**:

| Category | Table columns (verified) |
|---|---|
| Food (CFIA) | `Brand \| Product \| Size \| UPC \| Codes` |
| Drugs | `Brand \| Product Name \| Market Authorization \| Dosage Form \| Strength \| Lot Number` |
| Medical devices | `Affected products \| Lot or serial number \| Model or catalogue number` |
| Consumer products | Often **no table at all** — just prose (e.g. "This recall involves Ultra Big Blue Automatic Toilet Bowl Cleaner (255 g / 9 oz)"), no UPC, no lot code |

**Design consequence:** detail-page fetching is per-category-aware, not one generic parser.
Food and drug recalls get precise, structured matching (UPC/lot). Medical device recalls get
serial/model matching. Consumer product recalls frequently degrade to brand + product-name
matching only, because that's all the source data provides — no amount of clever parsing
invents a UPC that was never published. The system should say "no structured identifier
available for this recall" rather than pretend otherwise.

Detail pages are only fetched for *new or updated* NIDs, not on every poll — at ~40–50/month
that's a handful of extra requests per week, not meaningful scraping load.

### Reference/lookup sources for building inventory

Different product categories use fundamentally different identification systems in Canada, so
inventory lookup is category-aware rather than one barcode API for everything:

- **Medications** → Health Canada's own Drug Product Database (DPD) REST API,
  `https://health-products.canada.ca/api/drug/drugproduct/`. Free, official, no key. Verified
  live: supports lookup by DIN (Drug Identification Number) and by brand-name search (e.g.
  searching "tylenol" returns every registered Tylenol product with its DIN). Canadian drugs
  are identified by DIN, not UPC — this is the *correct* identifier for this category, not a
  workaround.
- **Food** → Open Food Facts (`world.openfoodfacts.org`), free, keyless, worldwide. Verified
  live: works well for major brands (a Nutella UPC returned full product name, brand,
  categories, allergens). It's crowdsourced, so coverage is uneven — the actual Coaticook cheese
  UPC from a real current recall returned "product not found." Barcode lookup is the fast path
  when it hits; typed brand + product name is the fallback, and it will be needed often.
- **Household/consumer products** → no free, trustworthy barcode source was found. A live test
  of UPCitemdb's keyless tier returned completely mismatched data for a real barcode (asked for
  a bike pump, got a cat grooming kit). This category is manual entry only for the MVP — brand
  + product name + category, typed by the user.

### Notifications

Email via Resend (`resend.com`). Free tier: 3,000 emails/month, 100/day cap, official Python
SDK, and — confirmed — sending works out of the box from a sandbox address
(`onboarding@resend.dev`) with no domain ownership required to start. Good fit for an MVP that
shouldn't need you to buy and verify a domain before the first alert can be sent.

### Infra

Local Python script + SQLite, run on a schedule (cron or equivalent). No hosting cost, fastest
to build and demo, easy to explain end-to-end in an interview. The tradeoff, stated plainly: it
only runs when triggered, so it's not "always on" unless the machine running it is. That's an
acceptable tradeoff for an MVP/portfolio project and can be revisited later without changing the
data model.

---

## The core agentic loop, step by step, with reasoning

### 1. Scheduled check for new/updated recalls

Poll the bulk JSON feed on a schedule (e.g. daily). Use the `ETag`/`Last-Modified` response
headers to skip reprocessing when the file hasn't changed since the last run — cheap and
reliable, confirmed the server sends both headers correctly. Optionally poll the relevant RSS
feeds more frequently as a low-latency signal, but always reconcile against the bulk feed so
nothing is missed if an item rolls off the RSS window.

**Why this design:** the bulk feed is complete and stable; RSS is fast but lossy. Using both,
with the bulk feed as ground truth, gets low latency without sacrificing completeness.

### 2. Collect, standardize, and store

For each record from the bulk feed, store the fields as-is (`NID` as primary key), and only
fetch + parse the detail-page product table for records that are **new** (`NID` not seen before)
or **updated** (`Last updated` changed since last stored). Store parsed product-level identifiers
(UPC, lot number, brand, size) in a separate table linked by `NID`, since not every recall will
have them, and the schema of what's available differs by category (see table above).

**Why separate tables:** a recall and its affected-product list are a one-to-many relationship
(one recall, up to dozens of UPCs/sizes/lots), and roughly a third of consumer-product recalls
have *zero* structured products — forcing that into flat columns on the recall row would mean a
lot of nullable, category-specific columns that don't apply to most rows.

### 3. Detect and merge duplicate notices

This is real, necessary work, not a formality. Confirmed live: when a recall is updated or
expanded, the government publishes it as a **brand-new `NID`** — e.g. "Update: Great White North
Growers Inc. recalls..." and "Expanded recall: U Kids We Love Cozy 2-piece Pajamas Sets..." are
separate records from their originals, with **no field linking them back**. Every NID in the
current 33,883-record dump is unique — there is no in-place revision to detect via a simple key
lookup.

Practical approach: when a new record's title contains a pattern like `Update:` or `Expanded
recall:`, extract the core product/brand phrase and fuzzy-match it (see step 5's matching logic)
against recent existing recalls in the same category. Above a high-confidence threshold, link
the new record to the original as a revision rather than treating it as an unrelated recall —
this prevents alerting a user twice for what is, from their perspective, the same recall.

**Why this can't be a simple string-equals check:** government recall titles are not
standardized enough for exact matching to be reliable, and the "Update:"/"Expanded recall:"
prefix pattern itself isn't universal — some updates are titled differently. This step will
have false negatives (missed links) more often than false positives, which is the safer failure
direction for a safety app: worst case is a rare duplicate alert, not a missed one.

### 4. Compare recall against each user's saved inventory

Match on whatever identifiers are actually available for that recall's category:

- **Food/drugs with UPC or lot data**: exact match on UPC first (cheap, unambiguous). If no UPC
  match, fall back to brand + product-name fuzzy match.
- **Medical devices**: match on serial/model/lot number if the user recorded one, else brand +
  product name.
- **Consumer products without any structured table**: brand + product-name fuzzy match only —
  there is nothing more precise to match against, and pretending otherwise would be dishonest
  about what the source data contains.

Confirmed live with `rapidfuzz` (see `demos/03_fuzzy_match.py`): genuine near-matches
("Coaticook White Cheddar Cheese Curds" vs. "Coaticook cheddar curds - white") score in the
60–90 range depending on the scoring function, and — critically — **so do some clearly unrelated
products** ("Tylenol Extra Strength Caplets" vs. "Advil Extra Strength Tablets" scored 75.9 on
`WRatio`, nearly the same range as genuine matches). This is the concrete evidence behind step 5:
a fuzzy score alone is not sufficient to trigger a safety alert. It's a candidate filter — "is
this worth a closer look" — not a verdict.

### 5. Claude examines uncertain matches and explains its reasoning

For matches that clear a low bar (candidate threshold) but don't clear a high bar (auto-confirm
threshold), send the recall's full text (title, product, issue, category) and the user's saved
item to Claude, and ask for a structured judgment: is this likely the same product, and why.
This mirrors the same pattern already proven out in GlutenGuard — structured output via
`output_format`, conservative-by-default reasoning, and a plain explanation a non-technical user
can read.

**Why this step exists and isn't optional:** the Tylenol/Advil example above is not a contrived
edge case — it's representative of exactly the kind of near-miss that plain string similarity
cannot resolve, because both are "[Brand] [Descriptor] [Form]" in the same shape. A model that
can read "Tylenol" and "Advil" and know they are different active ingredients closes a gap that
no amount of string-distance tuning can.

### 6. Assign priority from severity and match confidence

The data already carries a severity signal — `Recall class`, which is `Class 1/2/3` for food and
consumer products, `Type I/II/III` for drugs and medical devices (Class 1 / Type I being most
severe). Confirmed live that this field is present but **not always populated** — roughly a
third of CFIA/consumer-product records have it blank or `'--'`. Priority scoring needs a defined
fallback for missing severity (e.g. treat unknown severity as medium, not low, since defaulting
low on missing safety data is the wrong direction to default).

Combine `Recall class`/`Type` with the match confidence from steps 4–5 (exact ID match >
Claude-confirmed likely match > Claude-uncertain match) to produce a priority tier. This tier is
what determines whether the user gets a notification and how it's framed — the Green/Yellow/Red
style plain-language pattern already validated in GlutenGuard is the right shape here too.

### 7. Notify the user

If the match/priority passes the alert threshold, send a concise email: product name, the
specific risk, affected identifiers (UPC/lot if available, otherwise "no lot number provided by
the manufacturer — check your product against the description below"), recommended action, and
a link to the official government recall page as the source of truth. Never paraphrase away the
official link — the user should always be able to verify against the primary source.

### 8. Record the result so alerts don't repeat

Store the (user, recall NID, outcome) tuple — matched or not, notified or not, and why — so a
recall that was already evaluated for a user isn't re-evaluated and re-sent on the next poll.
This also gives an audit trail: if a user asks "why did I get this alert" or "why didn't I get
an alert for X," the stored reasoning (including Claude's explanation from step 5, when
applicable) answers it directly instead of requiring a re-run.

---

## Known gaps and honest limitations (for the MVP)

- **No structured product data for most consumer-product recalls.** This isn't a bug to fix
  later — it's a property of the source data. The system should be transparent about this in
  the UI ("no lot number was provided for this recall") rather than silently degrading.
- **Deduplication will have false negatives.** An "Update:"/"Expanded recall:" record that
  doesn't fuzzy-match its original closely enough will be treated as a new recall, meaning a
  user could get two alerts for what is really one event. Rare, and the safer failure mode for a
  safety app, but real.
- **RSS feeds only carry the last ~3 items per category** — confirmed, not assumed. They're a
  latency optimization on top of the bulk feed, never the sole source of truth.
- **Household product barcode lookup has no reliable free source.** Manual entry is the
  answer for this category in the MVP, not a stopgap being deferred — a paid barcode API is a
  cost/product decision to revisit later, not a technical blocker now.
- **`Recall class`/`Type` is missing on a meaningful fraction of records** (roughly a third for
  food/consumer products). Priority scoring must have an explicit, safety-conservative default
  for "unknown severity," not silently treat missing data as low priority.
- **Local script + SQLite is not always-on.** Fine for an MVP/demo; a production version would
  need a real scheduler and possibly a hosted database, which is a deliberately deferred
  decision, not an oversight.

---

## What's proven, not assumed

Everything above the "Known gaps" section reflects data actually pulled and tested live during
design, not read from documentation and assumed to work:

- Bulk JSON feed: pulled the real 15 MB file, confirmed field names, confirmed 33,883 unique
  NIDs, confirmed `ETag`/`Last-Modified` headers.
- CFIA RSS feed: pulled the real feed, confirmed valid RSS 2.0, confirmed `guid` values match the
  bulk feed's `NID`.
- Per-recall detail pages: fetched real pages across four categories, confirmed table structure
  for food/drugs/medical devices, confirmed the *absence* of a table for a real consumer-product
  recall.
- Health Canada DPD API: live DIN lookup and live brand-name search both returned real data.
- Open Food Facts: live UPC lookup succeeded for a major brand, live UPC lookup returned "not
  found" for a real regional recall product — both outcomes are informative and are reflected
  above.
- UPCitemdb free tier: live lookup returned mismatched junk data, which is why it's excluded.
- rapidfuzz scoring: real product-name pairs scored and compared, including the Tylenol/Advil
  near-miss that motivates step 5.
- Resend: confirmed sandbox sending address requires no domain ownership to start.

See `demos/` in this folder for the three runnable proofs referenced above (RSS parsing, SQLite
table + insert, and rapidfuzz scoring).
