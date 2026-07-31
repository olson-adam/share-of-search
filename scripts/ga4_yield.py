#!/usr/bin/env python3
"""Layer 3 — business yield: what captured organic demand produces, from GA4.

    python3 scripts/ga4_yield.py --workspace ws/ --property 123456789
    python3 scripts/ga4_yield.py --list-properties

What this layer IS: sessions, engaged sessions and key events from the
Organic Search channel of YOUR property, month by month — the "so what" after
demand and capture. What it is NOT: attribution. GA4 cannot see which query
drove a session (no query dimension), so this is organic-search yield as a
whole, honestly labeled — never "revenue from brand searches".

Output: <workspace>/ga4.csv (month, sessions, engaged_sessions, key_events)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_auth import access_token, api_get, api_post
from sos_lib import die

DATA_API = "https://analyticsdata.googleapis.com/v1beta"
ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"


def main() -> None:
    ap = argparse.ArgumentParser(description="fetch organic-search yield from GA4")
    ap.add_argument("--workspace", type=Path)
    ap.add_argument("--property", help="GA4 property id (digits)")
    ap.add_argument("--months", type=int, default=16)
    ap.add_argument("--list-properties", action="store_true")
    args = ap.parse_args()

    token = access_token()
    if args.list_properties:
        accounts = api_get(f"{ADMIN_API}/accountSummaries?pageSize=200", token)
        for acc in accounts.get("accountSummaries", []):
            for p in acc.get("propertySummaries", []):
                print(f"{p['property'].split('/')[1]}  {p.get('displayName', '')} "
                      f"({acc.get('displayName', '')})")
        return
    if not args.workspace or not args.property:
        ap.error("--workspace and --property are required (or use --list-properties)")

    # explicit first-of-month start — a "N*31daysAgo" approximation would land
    # mid-month and put a fake trough at the left edge of every trend
    from datetime import date
    y, mo = date.today().year, date.today().month
    for _ in range(args.months):
        mo -= 1
        if mo == 0:
            y, mo = y - 1, 12
    body = {
        "dateRanges": [{"startDate": f"{y:04d}-{mo:02d}-01", "endDate": "yesterday"}],
        "dimensions": [{"name": "yearMonth"}],
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                    {"name": "keyEvents"}],
        "dimensionFilter": {"filter": {
            "fieldName": "sessionDefaultChannelGroup",
            "stringFilter": {"value": "Organic Search"}}},
        "limit": 100,
    }
    resp = api_post(f"{DATA_API}/properties/{args.property}:runReport", token, body)
    rows_in = resp.get("rows", [])
    if not rows_in:
        die("GA4 returned no organic-search rows — check the property id and access")

    rows = []
    for r in rows_in:
        ym = r["dimensionValues"][0]["value"]  # YYYYMM
        month = f"{ym[:4]}-{ym[4:6]}"
        vals = [v["value"] for v in r["metricValues"]]
        rows.append({"month": month, "sessions": int(float(vals[0])),
                     "engaged_sessions": int(float(vals[1])),
                     "key_events": int(float(vals[2])), "property": args.property})
    rows.sort(key=lambda x: x["month"])
    # drop the partial current month for the same reason GSC does
    current = f"{date.today().year:04d}-{date.today().month:02d}"
    rows = [r for r in rows if r["month"] != current]

    out = args.workspace / "ga4.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "sessions", "engaged_sessions", "key_events", "property"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} months of organic-search yield → {out}")


if __name__ == "__main__":
    main()
