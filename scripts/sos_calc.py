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
from sos_lib import (GENERIC_BRAND, die, dump_json, load_basket, load_volumes,
                     month_label)
from validate import validate


def r1(x: float) -> float:
    return round(x + 1e-9, 1)


def compute(basket: dict, volumes: dict[tuple[str, str], int]) -> dict:
    kws = {k["keyword"].strip().lower(): k for k in basket["keywords"]}
    months = sorted({m for (_, m) in volumes})
    brands = sorted({k["brand"] for k in basket["keywords"] if k["brand"] != GENERIC_BRAND})

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
    gap_to_2 = (r1(shares[ranked[1]][-1] - shares[focus][-1])
                if rank > 2 else (r1(shares[ranked[1]][-1] - shares[ranked[0]][-1])
                                  if len(ranked) > 1 else None))

    # keyword movers: YoY volume change per keyword (needs 13+ months)
    movers = []
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
            "gap_to_2": gap_to_2,
            "volume": per_brand[focus][-1],
        },
        "brands": [{
            "name": b,
            "share": shares[b][-1],
            "delta_quarter": delta(shares[b], 3),
            "delta_year": delta(shares[b], 12),
            "volume": per_brand[b][-1],
            "is_focus": b == focus,
        } for b in ranked],
        "movers": movers,
        "basket": {"keywords": len(kws),
                   "version": basket.get("version", "unversioned")},
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
    dump_json(snapshot, out)
    f = snapshot["focus"]
    print(f"{snapshot['focus_brand']}: {f['share']}% of category demand "
          f"(rank {f['rank']}/{f['of']}, Δq {f['delta_quarter']}, Δy {f['delta_year']}) "
          f"→ {out}")


if __name__ == "__main__":
    main()
