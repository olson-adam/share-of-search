#!/usr/bin/env python3
"""Compute the share-of-search snapshot from a validated workspace.

    python3 scripts/sos_calc.py --workspace sos-workspace/ --out snapshot.json

The model, stated once and computed the same way everywhere:

- share of search  = a brand's branded volume / ALL branded volume, per month.
  Shares sum to 100% across brands. This is the market-shape number.
- generic demand   = volume where brand is "-" (nobody owns it). Reported as a
  parallel share of total category search — never as a competitor.
- Validation runs first and is embedded in the snapshot; on validation errors
  no snapshot is produced.

Deterministic: same basket + volumes → byte-identical snapshot. "As of" comes
from the data, never from the clock.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sos_lib import (DataError, GENERIC_BRAND, die, dump_json, load_basket,
                     load_volumes, month_key, month_label)
from validate import validate


def r1(x: float) -> float:
    return round(x + 1e-9, 1)


def compute(basket: dict, volumes: dict[tuple[str, str], int]) -> dict:
    kws = {k["keyword"].strip().lower(): k for k in basket["keywords"]}
    months = sorted({m for (_, m) in volumes})
    all_brands = sorted({k["brand"] for k in basket["keywords"] if k["brand"] != GENERIC_BRAND})
    # a brand with zero volume in every month is a data gap, not a competitor —
    # counting it would silently inflate the rank denominator
    brand_totals = {b: 0 for b in all_brands}
    for (k, _), v in volumes.items():
        if k in kws and kws[k]["brand"] != GENERIC_BRAND:
            brand_totals[kws[k]["brand"]] = brand_totals.get(kws[k]["brand"], 0) + v
    brands = [b for b in all_brands if brand_totals.get(b, 0) > 0]
    brands_without_data = [b for b in all_brands if brand_totals.get(b, 0) == 0]
    if basket["focus_brand"] in brands_without_data:
        raise SystemExit(f"error: focus brand {basket['focus_brand']!r} has no volume data")

    per_brand: dict[str, list[int]] = {b: [] for b in brands}
    generic: list[int] = []
    totals: list[int] = []
    branded_totals: list[int] = []
    for m in months:
        month_rows = [(k, v) for (k, mm), v in volumes.items() if mm == m and k in kws]
        by_brand: dict[str, int] = {b: 0 for b in brands}
        gen = 0
        for k, v in month_rows:
            b = kws[k]["brand"]
            if b == GENERIC_BRAND:
                gen += v
            else:
                by_brand[b] += v
        branded = sum(by_brand.values())
        for b in brands:
            per_brand[b].append(by_brand[b])
        generic.append(gen)
        branded_totals.append(branded)
        totals.append(branded + gen)

    shares = {b: [r1(100 * per_brand[b][i] / branded_totals[i]) if branded_totals[i] else 0.0
                  for i in range(len(months))] for b in brands}

    def delta(series: list[float], k: int) -> float | None:
        return r1(series[-1] - series[-1 - k]) if len(series) > k else None

    focus = basket["focus_brand"]
    ranked = sorted(brands, key=lambda b: -shares[b][-1])
    rank = ranked.index(focus) + 1
    # gap_up: distance to the brand directly above you (positive, null for #1);
    # lead_over_2: the leader's margin over #2 (null unless you ARE #1)
    gap_up = r1(shares[ranked[rank - 2]][-1] - shares[focus][-1]) if rank > 1 else None
    lead_over_2 = (r1(shares[ranked[0]][-1] - shares[ranked[1]][-1])
                   if rank == 1 and len(ranked) > 1 else None)

    # product-unbranded demand: unowned like Generic, but it names a product —
    # broken out so the type actually changes what you can see
    pu_kws = {k for k, meta in kws.items() if meta["type"] == "Product Unbranded"}
    product_unbranded = [sum(v for (k, mm), v in volumes.items()
                             if mm == m and k in pu_kws) for m in months]

    # keyword movers: YoY volume change per keyword (needs 13+ months)
    movers = []
    movers_note = None
    if len(months) < 13:
        movers_note = (f"needs 13+ months of history for year-over-year moves "
                       f"(have {len(months)})")
    if len(months) >= 13:
        m_now, m_then = months[-1], months[-13]
        for kw, meta in kws.items():
            v_now = volumes.get((kw, m_now))
            v_then = volumes.get((kw, m_then))
            if v_now is not None and v_then and v_then >= 30:
                movers.append({"keyword": kw, "type": meta["type"],
                               "brand": meta["brand"],
                               "delta_y_pct": round(100 * (v_now - v_then) / v_then)})
        movers.sort(key=lambda x: (-abs(x["delta_y_pct"]), x["keyword"]))
        movers = movers[:8]

    return {
        "category": basket["category"],
        "geo": basket["geo"],
        "language": basket["language"],
        "focus_brand": focus,
        "as_of": month_label(months[-1]),
        "months": [month_label(m) for m in months],
        "shares": shares,
        "volumes_by_brand": per_brand,
        "generic_volume": generic,
        "branded_volume_total": branded_totals,
        "category_volume_total": totals,
        "generic_share_of_total": [r1(100 * generic[i] / totals[i]) if totals[i] else 0.0
                                   for i in range(len(months))],
        "focus": {
            "share": shares[focus][-1],
            "delta_quarter": delta(shares[focus], 3),
            "delta_year": delta(shares[focus], 12),
            "rank": rank,
            "of": len(brands),
            "gap_up": gap_up,
            "lead_over_2": lead_over_2,
            "volume": per_brand[focus][-1],
        },
        "brands_without_data": brands_without_data,
        "product_unbranded_volume": product_unbranded,
        "brands": [{
            "name": b,
            "share": shares[b][-1],
            "delta_quarter": delta(shares[b], 3),
            "delta_year": delta(shares[b], 12),
            "volume": per_brand[b][-1],
            "is_focus": b == focus,
        } for b in ranked],
        "movers": movers,
        "movers_note": movers_note,
        "basket": {"keywords": len(kws),
                   "version": basket.get("version", "unversioned")},
    }


def load_capture(path: Path) -> dict | None:
    """Optional layer 2: gsc.csv → capture block (your site only, never the market)."""
    import csv as csv_mod
    if not path.exists():
        return None
    rows = list(csv_mod.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        return None
    months = sorted({r["month"] for r in rows})
    brands = sorted({r["brand"] for r in rows if r["brand"] != "-site-total-"})
    for r in rows:
        month_key(r["month"])  # malformed months must not survive into labels
    def series(brand: str, field: str) -> list:
        by_month = {r["month"]: r for r in rows if r["brand"] == brand}
        out = []
        for m in months:
            r = by_month.get(m)
            v = r[field] if r and r[field] != "" else 0
            out.append(float(v) if field == "position" else int(float(v or 0)))
        return out
    total_imp = series("-site-total-", "impressions")
    branded_imp = [sum(series(b, "impressions")[i] for b in brands) for i in range(len(months))]
    return {
        "site": rows[0].get("site", ""),
        "months": [month_label(m) for m in months],
        "brands": {b: {"clicks": series(b, "clicks"),
                       "impressions": series(b, "impressions"),
                       "position": series(b, "position")} for b in brands},
        "site_total": {"clicks": series("-site-total-", "clicks"),
                       "impressions": total_imp},
        "branded_share_of_site_impressions": [
            r1(100 * branded_imp[i] / total_imp[i]) if total_imp[i] else 0.0
            for i in range(len(months))],
        "note": "your site only — GSC cannot see competitors; never present as market share",
    }


def load_yield(path: Path) -> dict | None:
    """Optional layer 3: ga4.csv → yield block (organic search as a whole)."""
    import csv as csv_mod
    if not path.exists():
        return None
    rows = sorted(csv_mod.DictReader(path.open(encoding="utf-8-sig")),
                  key=lambda r: r["month"])
    if not rows:
        return None
    for r in rows:
        month_key(r["month"])
    return {
        "property": rows[0].get("property", ""),
        "months": [month_label(r["month"]) for r in rows],
        "sessions": [int(float(r["sessions"])) for r in rows],
        "engaged_sessions": [int(float(r["engaged_sessions"])) for r in rows],
        "key_events": [int(float(r["key_events"])) for r in rows],
        "note": ("organic-search yield as a whole — GA4 has no query dimension, "
                 "so this is never 'revenue from brand searches'"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="compute the share-of-search snapshot")
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--out", type=Path, help="default: <workspace>/snapshot.json")
    ap.add_argument("--source", default="unspecified",
                    help="data source note for the report, e.g. keyword-planner")
    args = ap.parse_args()
    basket_path = args.workspace / "basket.json"
    volumes_path = args.workspace / "volumes.csv"
    out = args.out or args.workspace / "snapshot.json"

    validation = validate(basket_path, volumes_path)
    if validation["errors"]:
        for e in validation["errors"]:
            print(f"validation error: {e}", file=sys.stderr)
        die("validation failed — no snapshot produced (fix the data, don't bypass the gate)")
    for w in validation["warnings"]:
        print(f"validation warning: {w}", file=sys.stderr)

    basket = load_basket(basket_path)
    volumes = load_volumes(volumes_path)
    snapshot = compute(basket, volumes)
    snapshot["validation"] = validation
    snapshot["source"] = args.source
    # optional layers degrade to a warning — a malformed gsc/ga4 file must never
    # take the market-demand snapshot down with it
    try:
        capture = load_capture(args.workspace / "gsc.csv")
        if capture:
            snapshot["capture"] = capture
    except (DataError, ValueError, KeyError, IndexError) as e:
        msg = f"capture layer (gsc.csv) skipped: {e}"
        print(f"warning: {msg}", file=sys.stderr)
        snapshot["validation"]["warnings"].append(msg)
    try:
        yld = load_yield(args.workspace / "ga4.csv")
        if yld:
            snapshot["yield"] = yld
    except (DataError, ValueError, KeyError, IndexError) as e:
        msg = f"yield layer (ga4.csv) skipped: {e}"
        print(f"warning: {msg}", file=sys.stderr)
        snapshot["validation"]["warnings"].append(msg)
    dump_json(snapshot, out)
    f = snapshot["focus"]
    dq = "n/a" if f["delta_quarter"] is None else f["delta_quarter"]
    dy = "n/a" if f["delta_year"] is None else f["delta_year"]
    print(f"{snapshot['focus_brand']}: {f['share']}% of category demand "
          f"(rank {f['rank']}/{f['of']}, Δq {dq}, Δy {dy}) → {out}")


if __name__ == "__main__":
    main()
