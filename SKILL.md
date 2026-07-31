---
name: share-of-search
description: Track your brand's share of category search demand — the leading indicator of market share — from Google Keyword Planner or DataForSEO data, with first-class validation and a dark instrument dashboard. Use when the user wants share of search / share of branded search, brand demand tracking versus competitors, a monthly demand report, to build or refresh a keyword basket, or asks "how much of the category's demand do we own?"
---

# share-of-search

Every month, buyers cast votes by typing a brand name into a search box. This skill counts
them honestly: **share of search = your brand's branded search volume ÷ all branded search
volume in the category**. It is a leading indicator that correlates with market-share
movement (Les Binet, IPA) — never a measurement of market share, and every surface of this
tool says so.

## The three-layer model (say it the way the tool does)

1. **Market demand** (this skill, v1): how much branded demand exists and whose name is on
   it. Comparable across competitors because search volumes are public.
2. **Owned capture** (roadmap): your GSC impressions/clicks on that demand — never call
   this market share; GSC sees only your own site.
3. **Business yield** (roadmap): what captured demand produces in GA4.

Generic demand ("crm tools", "pipeline software") belongs to **no one** — it is tracked as
a parallel pool, never counted as a competitor.

## Workspace

User data lives in a workspace directory (default `sos-workspace/`), never in this repo:

```
sos-workspace/
├── basket.json     # the category definition — keywords tagged brand + type
├── volumes.csv     # monthly history (merge-preserving: refreshes never delete)
├── runs/           # raw provider responses, kept for auditability
└── snapshot.json   # computed output — feeds the dashboard and any report
```

## Setup (once)

Python 3.11+ stdlib only for the core. Providers:
- **keyword-planner** (free, exact): needs `~/google-ads.yaml` (developer_token,
  login_customer_id) + gcloud ADC, and `pip install google-ads`.
- **dataforseo** (paid, no Google account needed): keychain entry
  `security add-generic-password -s dataforseo-api -a <login> -w <password>`.
  Cost is printed on every call.
- **csv** (no accounts): import any export; columns are mapped with `--map`.

Dashboard: `cd app && npm install && npm run dev` (reads `app/public/snapshot.json`).

## The monthly loop

```bash
python3 scripts/fetch_volumes.py --workspace ws/ --provider keyword-planner
python3 scripts/sos_calc.py --workspace ws/ --source keyword-planner
cp ws/snapshot.json app/public/snapshot.json   # dashboard now shows the new month
```

`sos_calc` runs validation first and **refuses to produce a snapshot on errors** — never
bypass that gate by editing data files to "make it pass"; fix the underlying data. The
validation exists because a locale-blind parser once read "8 900" as 8 and inflated a
brand's share 3× on a live dashboard. Cron recipe for a monthly refresh:

```
0 7 3 * * cd $HOME/sos && python3 scripts/fetch_volumes.py --workspace ws --provider keyword-planner && python3 scripts/sos_calc.py --workspace ws --source keyword-planner && cp ws/snapshot.json app/public/snapshot.json
```

## Building a basket (the judgment step — never fully automated)

The share number is only as good as the basket. Two paths:

1. **Suggest + tag** (recommended): `scripts/basket_builder.py suggest --brands "A,B,C"
   --terms "crm,pipeline"` fetches real volumes for brand/term candidates via DataForSEO
   and writes the ones with volume. Then tag each candidate WITH the user — the
   `suggested_*` fields are guesses, not decisions. Ask especially about
   **Product Unbranded**: product names searched without their brand ("ws alert",
   "pipeline pro") — only someone who knows the products can spot these, and missing them
   understates the brands that own those products.
2. **Bring your own**: the user supplies keywords; you tag together, then
   `basket_builder.py check basket.json`.

Basket rules the loader enforces: Branded keywords carry a brand; Generic and
Product Unbranded carry `-`; no duplicates; the focus brand must have keywords.
Version the basket (`"version"` field) and bump it whenever keywords change — a share
series is only comparable within one basket version, so say so when presenting trends
that cross a version change.

## Presenting results (honesty rules)

- Lead with the focus brand's share and its **deltas** (Δ quarter, Δ year) — the trend is
  the product, the absolute number is context.
- Never call share of search "market share". Never present generic-pool share as
  something the brand "lost".
- The snapshot's `validation` block is part of the result: surface warnings, and if you
  ever see errors there, something bypassed the gate — stop and say so.
- Keyword movers explain *which queries* drive a share move — use them as the "why"
  layer, but volume-driven why, not causal claims about campaigns without evidence.
- Monthly Keyword Planner volumes are rounded/bucketed by Google; month-to-month noise of
  a few percent is normal. Quarters tell truer stories than single months.
