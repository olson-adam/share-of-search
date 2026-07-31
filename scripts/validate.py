#!/usr/bin/env python3
"""Validate a share-of-search workspace before any number is computed.

    python3 scripts/validate.py --workspace sos-workspace/
    python3 scripts/validate.py --basket basket.json --volumes volumes.csv

Validation is a first-class feature of this tool, not a convenience: the bug
that motivated it (a locale-blind parser reading "8 900" as 8) inflated a
brand's reported share 3x on a live dashboard before anyone noticed. Every
report renders the validation verdict; a report without one is not trusted.

Exit codes: 0 = clean · 1 = warnings only · 2 = errors (calc must not run).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sos_lib import DataError, GENERIC_BRAND, load_basket, load_volumes, month_range


def validate(basket_path: Path, volumes_path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict = {}

    try:
        basket = load_basket(basket_path)
    except (DataError, OSError, json.JSONDecodeError) as e:
        return {"errors": [f"basket: {e}"], "warnings": [], "stats": {}}
    try:
        volumes = load_volumes(volumes_path)
    except DataError as e:
        return {"errors": [f"volumes: {e}"], "warnings": [], "stats": {}}
    except OSError as e:
        return {"errors": [f"volumes: {e}"], "warnings": [], "stats": {}}

    kws = {k["keyword"].strip().lower(): k for k in basket["keywords"]}
    months = sorted({m for (_, m) in volumes})
    stats["keywords_in_basket"] = len(kws)
    stats["months"] = len(months)
    stats["rows"] = len(volumes)

    if not months:
        return {"errors": ["volumes: no data rows"], "warnings": [], "stats": stats}
    stats["first_month"], stats["last_month"] = months[0], months[-1]

    # 1. month continuity — a silent gap shifts every delta that follows it
    expected = month_range(months[0], months[-1])
    gaps = [m for m in expected if m not in set(months)]
    if gaps:
        errors.append(f"month gap(s) in history: {', '.join(gaps)}")

    # 2. every volume row must belong to a basket keyword (and warn the reverse)
    vol_kws = {kw for (kw, _) in volumes}
    orphans = sorted(vol_kws - set(kws))
    if orphans:
        errors.append(f"{len(orphans)} keyword(s) in volumes but not in basket: "
                      + ", ".join(orphans[:5]) + ("…" if len(orphans) > 5 else ""))
    unfetched = sorted(set(kws) - vol_kws)
    if unfetched:
        warnings.append(f"{len(unfetched)} basket keyword(s) have no volume data yet: "
                        + ", ".join(unfetched[:5]) + ("…" if len(unfetched) > 5 else ""))

    # 3. per-keyword coverage — a keyword missing single months skews its brand
    covered = expected if not gaps else months
    incomplete = []
    for kw in sorted(vol_kws & set(kws)):
        have = {m for (k, m) in volumes if k == kw}
        miss = [m for m in covered if m not in have]
        if miss:
            incomplete.append(f"{kw} (missing {len(miss)})")
    if incomplete:
        warnings.append("keywords with partial month coverage: "
                        + ", ".join(incomplete[:5]) + ("…" if len(incomplete) > 5 else ""))

    # 4. outlier jumps — >8x month-over-month is nearly always a data problem
    for kw in sorted(vol_kws & set(kws)):
        series = sorted(((m, v) for (k, m), v in volumes.items() if k == kw))
        for (m0, v0), (m1, v1) in zip(series, series[1:]):
            if v0 >= 50 and v1 >= 50 and max(v0, v1) / max(1, min(v0, v1)) > 8:
                warnings.append(f"outlier jump for {kw!r}: {v0} ({m0}) → {v1} ({m1})")

    # 5. branded demand must exist — otherwise share-of-branded is undefined
    last = months[-1]
    branded_last = sum(v for (k, m), v in volumes.items()
                       if m == last and k in kws and kws[k]["brand"] != GENERIC_BRAND)
    if branded_last == 0:
        errors.append(f"no branded volume in latest month {last}")

    return {"errors": errors, "warnings": warnings, "stats": stats}


def main() -> None:
    ap = argparse.ArgumentParser(description="validate basket + volumes before calculation")
    ap.add_argument("--workspace", type=Path, help="dir containing basket.json + volumes.csv")
    ap.add_argument("--basket", type=Path)
    ap.add_argument("--volumes", type=Path)
    args = ap.parse_args()
    basket = args.basket or (args.workspace / "basket.json" if args.workspace else None)
    volumes = args.volumes or (args.workspace / "volumes.csv" if args.workspace else None)
    if not basket or not volumes:
        ap.error("give --workspace or both --basket and --volumes")

    result = validate(basket, volumes)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"]:
        sys.exit(2)
    sys.exit(1 if result["warnings"] else 0)


if __name__ == "__main__":
    main()
