#!/usr/bin/env python3
"""Layer 2 — owned capture: your branded queries in Google Search Console.

    python3 scripts/gsc_capture.py --workspace ws/ --site sc-domain:example.com
    python3 scripts/gsc_capture.py --workspace ws/ --site https://www.example.com/ --months 16
    python3 scripts/gsc_capture.py --list-sites

What this layer IS: how much of the branded demand that touches Google's
results your own site captures — impressions, clicks, position for queries
containing your brand names. What it is NOT: market share. GSC sees only your
site; competitors' capture is invisible here. The two layers stay separate on
every surface.

Side effect worth having: the per-query dump (runs/gsc-queries.json) answers
the homonym question small brands always have — is that search volume really
your brand, or a typo for something else? The queries Google actually matched
to your site settle it.

Output: <workspace>/gsc.csv  (month, brand, clicks, impressions, position)
plus a "-site-total-" row per month for context.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_auth import access_token, api_get, api_post
from sos_lib import GENERIC_BRAND, die, load_basket

API = "https://www.googleapis.com/webmasters/v3"


def month_bounds(months_back: int) -> list[tuple[str, str, str]]:
    """[(YYYY-MM, first_day, last_day)] for complete months, oldest first.

    The current month is always excluded: GSC data lags ~2 days, and a partial
    month would fake a crash at the end of every trend.
    """
    from datetime import timedelta
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(months_back):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        first = date(y, m, 1)
        nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        out.append((f"{y:04d}-{m:02d}", first.isoformat(),
                    (nxt - timedelta(days=1)).isoformat()))
    return list(reversed(out))


def main() -> None:
    ap = argparse.ArgumentParser(description="fetch branded capture from Search Console")
    ap.add_argument("--workspace", type=Path)
    ap.add_argument("--site", help="GSC property, e.g. sc-domain:example.com")
    ap.add_argument("--months", type=int, default=16, help="complete months back (max ~16)")
    ap.add_argument("--list-sites", action="store_true")
    args = ap.parse_args()

    token = access_token()
    if args.list_sites:
        sites = api_get(f"{API}/sites", token)
        for s in sites.get("siteEntry", []):
            print(f"{s['siteUrl']}  ({s['permissionLevel']})")
        return
    if not args.workspace or not args.site:
        ap.error("--workspace and --site are required (or use --list-sites)")

    basket = load_basket(args.workspace / "basket.json")
    brands = sorted({k["brand"] for k in basket["keywords"] if k["brand"] != GENERIC_BRAND})
    brand_tokens = {b: b.lower() for b in brands}

    rows: list[dict] = []
    query_dump: dict[str, list] = {}
    site_enc = args.site.replace(":", "%3A").replace("/", "%2F")
    for key, first, last in month_bounds(args.months):
        body = {"startDate": first, "endDate": last, "dimensions": ["query"],
                "rowLimit": 25000, "dataState": "final"}
        resp = api_post(f"{API}/sites/{site_enc}/searchAnalytics/query", token, body)
        data = resp.get("rows", [])
        per_brand = {b: {"clicks": 0, "impressions": 0, "pos_w": 0.0} for b in brands}
        tot = {"clicks": 0, "impressions": 0}
        matched = []
        for r in data:
            q = r["keys"][0].lower()
            tot["clicks"] += r.get("clicks", 0)
            tot["impressions"] += r.get("impressions", 0)
            for b, tokk in brand_tokens.items():
                if tokk in q:
                    per_brand[b]["clicks"] += r.get("clicks", 0)
                    per_brand[b]["impressions"] += r.get("impressions", 0)
                    per_brand[b]["pos_w"] += r.get("position", 0) * r.get("impressions", 0)
                    matched.append({"query": r["keys"][0], "brand": b,
                                    "clicks": r.get("clicks", 0),
                                    "impressions": r.get("impressions", 0)})
                    break
        for b in brands:
            p = per_brand[b]
            pos = round(p["pos_w"] / p["impressions"], 1) if p["impressions"] else ""
            rows.append({"month": key, "brand": b, "clicks": int(p["clicks"]),
                         "impressions": int(p["impressions"]), "position": pos,
                         "site": args.site})
        rows.append({"month": key, "brand": "-site-total-", "clicks": int(tot["clicks"]),
                     "impressions": int(tot["impressions"]), "position": "",
                     "site": args.site})
        query_dump[key] = sorted(matched, key=lambda x: -x["impressions"])[:50]
        print(f"{key}: {int(tot['impressions'])} impressions total, "
              f"{sum(int(per_brand[b]['impressions']) for b in brands)} branded",
              file=sys.stderr)

    out = args.workspace / "gsc.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "brand", "clicks", "impressions", "position", "site"])
        w.writeheader()
        w.writerows(rows)
    runs = args.workspace / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "gsc-queries.json").write_text(
        json.dumps({"site": args.site, "note": "top branded-matching queries per month — "
                    "the homonym check: are these really your brand?",
                    "months": query_dump}, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"{len(rows)} rows → {out}\nquery dump → {runs / 'gsc-queries.json'}")


if __name__ == "__main__":
    main()
