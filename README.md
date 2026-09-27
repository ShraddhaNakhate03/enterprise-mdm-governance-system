# Master Data Governance & Harmonization System

A self-directed project simulating an enterprise master data intake pipeline across **Customer, Vendor, Product, and Pricing** domains — built to practice, and demonstrate, the core mechanics of a real MDM (Master Data Management) program: standardization, fuzzy deduplication, golden-record creation, pricing-exception auditing, SOP documentation, and stakeholder reporting.

All data in this repo is **synthetic** (generated with [Faker](https://faker.readthedocs.io/)), intentionally seeded with realistic messiness — typos, format drift, missing fields, and duplicate entries — so the cleansing and matching logic has real problems to solve.

## Why this project exists

Most portfolio "data cleaning" projects stop at removing exact-duplicate rows. Real master data work is harder than that: duplicates don't match exactly, natural keys don't always exist, and the right blocking/matching strategy is different for every domain. This project was built to practice — and be able to explain — those decisions concretely.

## Results at a glance

| Domain | Raw Records | Duplicate Clusters Found | Completeness Before → After | Natural Key Available? |
|---|---:|---:|---|---|
| Customer | 6,150 | 549 | 87.2% → 90.4% | No — name-based fuzzy match only |
| Vendor | 3,630 | 232 | 90.1% → 92.3% | **Yes** — Tax ID |
| Product | 4,130 | 139 | 96.6% → 96.5% (flat) | No — new SKU on every re-entry |
| Pricing | 4,280 | — (exception audit, not dedup) | 4 exception types isolated (see below) | N/A |

**Pricing exception audit** (SQL, window functions + policy reference table):

| Exception Type | Rows Flagged |
|---|---:|
| Duplicate SKU pricing (conflicting list price) | 274 |
| Unauthorized discount (exceeds category policy) | 160 |
| Invalid price (zero / negative / missing) | 60 |
| NetPrice calculation mismatch | 80 |

## The honest part: why the numbers aren't uniform

The completeness lift is **not** the same across domains, and that's the most interesting part of the project, not a flaw to gloss over:

- **Vendor** improved the most because Tax ID is a genuine natural key — blocking on it directly, then falling back to a name+state key for mis-keyed IDs, gave high-confidence matches.
- **Customer** has no reliable natural key, so matching relies on multi-pass blocking (last name + postal, first name + postal, email-root) unioned together. The first single-key pass only caught 268 of ~1,150 injected duplicates; adding two more blocking passes raised that to 549. Recall is still not 100%, and a production system would add a phonetic blocking pass (Soundex/Metaphone) and a manual-review queue for medium-confidence (70–84%) scores to close the gap.
- **Product** completeness barely moved (96.6% → 96.5%) because duplicate product rows were rarely missing fields to begin with — the problem there is redundant rows, not incomplete ones. This is a useful reminder that **deduplication and completeness are two different problems**; solving one doesn't automatically move the other.

## Repository structure

```
├── python/          Synthetic data generators + fuzzy dedup / golden-record logic (rapidfuzz + union-find)
├── sql/             Standardization & cleansing scripts, pricing exception audit (SQLite, ANSI-portable)
├── excel/           Raw domain workbooks (ready for Power Query) + formatted dedup/audit result workbooks
├── data/            Raw and golden (post-dedup) CSVs per domain, plus match audit logs
├── docs/            SOP & Data Dictionary (Word doc) covering all 4 domains
└── dashboard/       Weekly Master Data Health Scorecard (Excel with native charts + PowerPoint deck)
```

## Methodology

1. **Generate** — synthetic "core" records per domain, then programmatically inject near-duplicates (typos, swapped fields, reformatted phone numbers, inconsistent legal suffixes) and standalone incomplete records.
2. **Cleanse** — SQL standardization: trim whitespace, normalize casing, unify phone/postal/country formats, flag validation failures into an audit table (`sql/`).
3. **Block & Match** — group records into candidate buckets by a domain-appropriate key (see table above), then score name/text similarity with `rapidfuzz` (token-sort ratio, threshold 85). Matches are clustered with a union-find structure (`python/`).
4. **Survive** — build one golden record per cluster using documented survivorship rules (most-recent value wins, longest non-blank name wins, ties broken by lowest source ID) — see `docs/` for the full rule set.
5. **Audit** — for Pricing, a separate rule-based audit (not dedup) isolates duplicate-SKU pricing conflicts, policy-violating discounts, invalid prices, and net-price calculation errors.
6. **Report** — a weekly scorecard (Excel + PowerPoint) tracks defect rate, completeness, remediation turnaround, and exception backlog over a simulated 10-week program ramp.

## Tools used

Python (pandas, rapidfuzz, Faker) · SQL (SQLite, ANSI-portable syntax) · Excel (Power Query patterns, native charts) · PowerPoint (stakeholder reporting)

## Reproducing this locally

```bash
pip install pandas rapidfuzz faker openpyxl

# Generate synthetic raw data
python python/generate_customer_data.py
python python/generate_vendor_data.py
python python/generate_product_data.py
python python/generate_pricing_data.py

# Run cleansing (loads CSV into SQLite, applies sql/*.sql)
# Run dedup / golden record + pricing audit
python python/02_fuzzy_dedup_golden_record.py
python python/04_vendor_product_pipeline.py
```

## What I'd do next

- Add a phonetic (Soundex/Metaphone) blocking pass to raise Customer-domain match recall
- Route medium-confidence matches (70–84%) to a manual review queue instead of a hard auto/no-merge split
- Extend the pricing policy table to support vendor-specific contract overrides, not just category ceilings
