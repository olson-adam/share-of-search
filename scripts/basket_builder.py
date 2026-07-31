#!/usr/bin/env python3
"""Build and check the keyword basket — the step every SoS tool leaves manual.

    python3 scripts/basket_builder.py suggest --brands "Acme,Zenith" \
        --terms "crm,pipeline" --out candidates.json [--dfs-location 2752 --language sv]
    python3 scripts/basket_builder.py check basket.json
    python3 scripts/basket_builder.py init sos-workspace/

`suggest` generates candidate keywords (brand names alone + brand×term
combinations), fetches real volumes for them via DataForSEO search_volume
(keychain service "dataforseo-api"; cost printed to stderr), and writes the
candidates that actually have volume — ready for tagging into a basket.

It deliberately does NOT auto-build the basket: which keywords define your
category is a judgment call (a "you bring the basket" contract is documented
in the SKILL), and the Product Unbranded type — product names searched
without their brand — can only be identified by someone who knows the
products. The tool fetches evidence; you decide.

`check` validates a basket file and reports its shape.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sos_lib import DataError, die, dump_json, load_basket


def candidates_for(brands: list[str], terms: list[str]) -> list[str]:
    out: list[str] = []
    for b in brands:
        b = b.strip().lower()
        out.append(b)
        for t in terms:
            out.append(f"{b} {t.strip().lower()}")
    for t in terms:  # bare terms become Generic candidates
        out.append(t.strip().lower())
    seen, unique = set(), []
    for kw in out:
        if kw and kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def cmd_suggest(args) -> None:
    from fetch_volumes import fetch_dataforseo  # reuse the connector + keychain

    brands = [b for b in (args.brands or "").split(",") if b.strip()]
    terms = [t for t in (args.terms or "").split(",") if t.strip()]
    if not brands:
        die("--brands is required (comma-separated)")
    kws = candidates_for(brands, terms)
    if not args.yes:
        print(f"about to fetch volumes for {len(kws)} candidates via DataForSEO "
              "(PAID — roughly $0.05–0.10 per run at this size).", file=sys.stderr)
        if input("continue? [y/N] ").strip().lower() not in ("y", "yes"):
            die("aborted — nothing was billed", code=1)
    print(f"fetching volumes for {len(kws)} candidates…", file=sys.stderr)

    class A:  # minimal arg shim for the connector
        workspace = args.out.parent if args.out.parent != Path("") else Path(".")
        dfs_location = args.dfs_location
        language = args.language

    volumes = fetch_dataforseo(kws, A)
    latest: dict[str, int] = {}
    for (kw, m), v in volumes.items():
        if kw not in latest or m > latest[kw][0]:  # type: ignore[index]
            latest[kw] = (m, v)  # type: ignore[assignment]
    rows = []
    for kw in kws:
        got = latest.get(kw)
        vol = got[1] if got else 0
        if vol >= args.min_volume:
            guess_brand = next((b.strip() for b in brands
                                if kw == b.strip().lower()
                                or kw.startswith(b.strip().lower() + " ")), "-")
            rows.append({"keyword": kw, "latest_volume": vol,
                         "suggested_brand": guess_brand,
                         "suggested_type": "Branded" if guess_brand != "-" else "Generic"})
    rows.sort(key=lambda r: -r["latest_volume"])
    dump_json({"note": ("candidates with real volume — tag each into the basket "
                        "(brand, type: Branded | Generic | Product Unbranded) "
                        "or drop it; suggested_* fields are guesses, not decisions"),
               "candidates": rows}, args.out)
    dropped = len(kws) - len(rows)
    print(f"{len(rows)} candidates with volume ≥ {args.min_volume} → {args.out}"
          + (f" · {dropped} dropped (no volume)" if dropped else ""))


TEMPLATE = {
    "category": "your category, e.g. hearing protection",
    "geo": "SE",
    "language": "sv",
    "focus_brand": "YourBrand",
    "version": "1",
    "keywords": [
        {"keyword": "yourbrand", "brand": "YourBrand", "type": "Branded"},
        {"keyword": "competitor", "brand": "Competitor", "type": "Branded"},
        {"keyword": "category term", "brand": "-", "type": "Generic"},
        {"keyword": "product name searched without brand", "brand": "-",
         "type": "Product Unbranded"},
    ],
}


def cmd_init(args) -> None:
    out = args.workspace / "basket.json"
    if out.exists():
        die(f"{out} already exists — refusing to overwrite")
    dump_json(TEMPLATE, out)
    print(f"template basket → {out}\nedit it (real brands, real keywords), then: "
          f"basket_builder.py check {out}")


def cmd_check(args) -> None:
    try:
        basket = load_basket(args.basket)
    except DataError as e:
        die(str(e))
    kws = basket["keywords"]
    by_type: dict[str, int] = {}
    by_brand: dict[str, int] = {}
    for k in kws:
        by_type[k["type"]] = by_type.get(k["type"], 0) + 1
        by_brand[k["brand"]] = by_brand.get(k["brand"], 0) + 1
    print(json.dumps({
        "ok": True, "category": basket["category"], "focus_brand": basket["focus_brand"],
        "keywords": len(kws), "by_type": by_type, "by_brand": by_brand,
        "warnings": ([f"brand {b!r} has only 1 keyword — its share hangs on a single query"
                      for b, n in by_brand.items() if b != "-" and n == 1]
                     + (["no Generic keywords — generic demand cannot be tracked"]
                        if not by_type.get("Generic") else [])),
    }, indent=2, ensure_ascii=False, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser(description="build and check keyword baskets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest", help="fetch volume-backed candidates for tagging")
    s.add_argument("--brands", required=True, help="comma-separated brand names")
    s.add_argument("--terms", default="", help="comma-separated category terms")
    s.add_argument("--out", type=Path, default=Path("candidates.json"))
    s.add_argument("--min-volume", type=int, default=10)
    s.add_argument("--yes", action="store_true",
                   help="skip the paid-API confirmation prompt (for cron)")
    s.add_argument("--dfs-location", type=int, default=2752)
    s.add_argument("--language", default="sv")
    s.set_defaults(fn=cmd_suggest)
    c = sub.add_parser("check", help="validate a basket file")
    c.add_argument("basket", type=Path)
    c.set_defaults(fn=cmd_check)
    i = sub.add_parser("init", help="write a template basket.json to a workspace")
    i.add_argument("workspace", type=Path)
    i.set_defaults(fn=cmd_init)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
