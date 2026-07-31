#!/usr/bin/env python3
"""Generate the fictional Nordvik demo workspace (basket + 18 months of volumes).

Deterministic: every value is derived from the target share series below, so
regenerating always yields byte-identical files, and running sos_calc on the
result reproduces the exact numbers shown in the app and README.

    python3 examples/make_demo.py
    python3 scripts/sos_calc.py --workspace examples/demo-workspace --source keyword-planner
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sos_lib import dump_json, save_volumes

MONTHS = [f"2025-{m:02d}" for m in range(2, 13)] + [f"2026-{m:02d}" for m in range(1, 8)]

# target share-of-branded series (percent) — the story: Nordvik is the only riser
SHARES = {
    "Brantevik": [49.2,49.0,49.1,48.8,48.9,48.6,48.7,48.4,48.5,48.3,48.4,48.2,48.3,48.2,48.1,48.2,47.9,47.8],
    "Fjellvik":  [31.8,31.7,31.6,31.7,31.5,31.6,31.5,31.4,31.5,31.4,31.3,31.4,31.3,31.4,31.3,31.2,31.0,30.9],
    "Nordvik":   [9.6,9.9,9.8,10.2,10.1,10.5,10.8,10.7,11.1,11.4,11.7,12.0,11.9,12.3,12.6,12.9,13.0,13.1],
    "Sundby":    [9.4,9.4,9.5,9.3,9.5,9.3,9.0,9.5,8.9,8.9,8.6,8.4,8.5,8.1,8.0,7.7,8.1,8.2],
}
BRANDED_TOTAL = [14800 + round(2100 * i / 17) for i in range(18)]   # 14.8k → 16.9k
GENERIC_TOTAL = [9200 + round(1300 * i / 17) for i in range(18)]    # 9.2k → 10.5k

# each brand's volume is split across a few keywords, like a real basket
BRAND_KEYWORDS = {
    "Brantevik": [("brantevik", 0.62), ("brantevik crm", 0.24), ("brantevik login", 0.14)],
    "Fjellvik":  [("fjellvik", 0.68), ("fjellvik crm", 0.32)],
    "Nordvik":   [("nordvik", 0.58), ("nordvik crm", 0.27), ("nordvik pricing", 0.15)],
    "Sundby":    [("sundby crm", 0.71), ("sundby pipeline", 0.29)],
}
GENERIC_KEYWORDS = [("crm for smb", 0.34), ("pipeline tool", 0.26),
                    ("crm sverige", 0.23), ("pipeline pro", 0.17)]
PRODUCT_UNBRANDED = {"pipeline pro"}  # a product name searched without its brand

# keyword-level trend shaping (relative drift over 18 months, multiplicative)
DRIFT = {"nordvik crm": 1.55, "nordvik pricing": 1.30, "brantevik login": 0.94,
         "pipeline pro": 1.20}


def spread(total: int, parts: list[tuple[str, float]], t: float) -> dict[str, int]:
    """Split total over keywords; DRIFT shifts weight linearly across time."""
    weights = {}
    for kw, w in parts:
        d = DRIFT.get(kw, 1.0)
        weights[kw] = w * (1 + (d - 1) * t)
    scale = total / sum(weights.values())
    out = {kw: int(round(w * scale)) for kw, w in weights.items()}
    first = parts[0][0]
    out[first] += total - sum(out.values())  # exact-sum correction
    return out


def main() -> None:
    ws = ROOT / "examples" / "demo-workspace"
    keywords = []
    for brand, parts in BRAND_KEYWORDS.items():
        for kw, _ in parts:
            keywords.append({"keyword": kw, "brand": brand, "type": "Branded"})
    for kw, _ in GENERIC_KEYWORDS:
        keywords.append({"keyword": kw, "brand": "-",
                         "type": "Product Unbranded" if kw in PRODUCT_UNBRANDED else "Generic"})
    basket = {
        "category": "Nordic CRM tools",
        "geo": "SE",
        "language": "sv",
        "focus_brand": "Nordvik",
        "version": "v4",
        "note": "Fictional demo category — every brand and number is invented.",
        "keywords": sorted(keywords, key=lambda k: k["keyword"]),
    }
    dump_json(basket, ws / "basket.json")

    volumes: dict[tuple[str, str], int] = {}
    for i, month in enumerate(MONTHS):
        t = i / (len(MONTHS) - 1)
        for brand, parts in BRAND_KEYWORDS.items():
            brand_total = int(round(SHARES[brand][i] / 100 * BRANDED_TOTAL[i]))
            for kw, v in spread(brand_total, parts, t).items():
                volumes[(kw, month)] = v
        for kw, v in spread(GENERIC_TOTAL[i], GENERIC_KEYWORDS, t).items():
            volumes[(kw, month)] = v
    save_volumes(ws / "volumes.csv", volumes)

    # layer 2 demo — Nordvik's own GSC: branded capture rising with the share story
    import csv
    with (ws / "gsc.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "brand", "clicks", "impressions",
                                          "position", "site"])
        w.writeheader()
        site = "sc-domain:nordvik.example"
        for i, month in enumerate(MONTHS[2:], 2):  # GSC window: 16 months
            ndv_imp = 2600 + round(2400 * (i - 2) / 15)
            rows = [
                ("Nordvik", round(ndv_imp * 0.34), ndv_imp, 1.2),
                ("Brantevik", 6 + i, 160 + 6 * i, 8.4),      # comparison queries
                ("Fjellvik", 3, 70 + 3 * i, 9.1),
                ("Sundby", 1, 30, 11.0),
                ("-site-total-", round((ndv_imp + 5200 + 90 * i) * 0.12),
                 ndv_imp + 5200 + 90 * i, ""),
            ]
            for brand, clicks, imp, pos in rows:
                w.writerow({"month": month, "brand": brand, "clicks": clicks,
                            "impressions": imp, "position": pos, "site": site})

    # layer 3 demo — GA4 organic-search yield
    with (ws / "ga4.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "sessions", "engaged_sessions",
                                          "key_events", "property"])
        w.writeheader()
        for i, month in enumerate(MONTHS[2:], 2):
            sessions = 3200 + round(2200 * (i - 2) / 15)
            w.writerow({"month": month, "sessions": sessions,
                        "engaged_sessions": round(sessions * 0.61),
                        "key_events": round(sessions * 0.031),
                        "property": "000000000"})

    print(f"demo workspace → {ws} ({len(basket['keywords'])} keywords, {len(MONTHS)} months, "
          f"+ gsc.csv/ga4.csv demo layers)")


if __name__ == "__main__":
    main()
