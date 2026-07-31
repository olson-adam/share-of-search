"""Shared core for share-of-search: parsing, schemas, deterministic IO.

Two hard-won lessons are encoded here and must not be optimized away:

1. Locale-safe volume parsing. Swedish-locale exports write 8 900 with a
   non-breaking space; a naive int() (or JS parseInt) silently truncates it
   to 8. In production that inflated the smallest brand's share 3x before
   anyone noticed. parse_volume strips every known thousands separator and
   REFUSES ambiguous values instead of guessing.

2. Determinism. Same inputs must produce byte-identical outputs: keys are
   sorted, floats rounded at fixed precision, and nothing derives from the
   clock — "as of" always comes from the data itself.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

BASKET_TYPES = ("Branded", "Generic", "Product Unbranded")
GENERIC_BRAND = "-"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# every separator seen in the wild: space, NBSP, narrow NBSP, thin space,
# apostrophes, dots and commas used as thousands marks
_SEPARATORS = "    '’.,"
_CLEAN_RE = re.compile("[" + re.escape(_SEPARATORS) + "]")


class DataError(ValueError):
    """Input data that must stop the pipeline (never silently corrected)."""


def parse_volume(raw: str | int | float, *, context: str = "") -> int:
    if isinstance(raw, (int, float)):
        if raw < 0:
            raise DataError(f"negative volume {raw!r} {context}")
        return int(raw)
    s = str(raw).strip()
    if not s:
        raise DataError(f"empty volume {context}")
    cleaned = _CLEAN_RE.sub("", s)
    if not cleaned.isdigit():
        raise DataError(f"unparseable volume {raw!r} {context}")
    # a separator-stripped value must be consistent with a thousands-grouped
    # reading of the original; "8 900" -> 8900 is fine, "8,9" -> 89 is not
    if re.search(r"[.,]\d{1,2}$", s):
        raise DataError(f"ambiguous decimal-looking volume {raw!r} {context}")
    return int(cleaned)


def month_key(m: str) -> str:
    m = m.strip()
    if not MONTH_RE.match(m):
        raise DataError(f"month must be YYYY-MM, got {m!r}")
    return m


def month_range(a: str, b: str) -> list[str]:
    """Inclusive list of months from a to b."""
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    out = []
    while (ya, ma) <= (yb, mb):
        out.append(f"{ya:04d}-{ma:02d}")
        ma += 1
        if ma == 13:
            ya, ma = ya + 1, 1
    return out


def month_label(m: str) -> str:
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{names[int(m[5:7]) - 1]} {m[2:4]}"


# ---------- basket ----------

def load_basket(path: Path) -> dict:
    basket = json.loads(path.read_text(encoding="utf-8"))
    for field in ("category", "geo", "language", "focus_brand", "keywords"):
        if field not in basket:
            raise DataError(f"basket missing field {field!r}")
    seen = set()
    for kw in basket["keywords"]:
        for field in ("keyword", "brand", "type"):
            if field not in kw:
                raise DataError(f"basket keyword missing field {field!r}: {kw}")
        if kw["type"] not in BASKET_TYPES:
            raise DataError(f"unknown keyword type {kw['type']!r} for {kw['keyword']!r} "
                            f"(allowed: {', '.join(BASKET_TYPES)})")
        if (kw["type"] == "Branded") == (kw["brand"] == GENERIC_BRAND):
            raise DataError(f"{kw['keyword']!r}: Branded keywords must carry a brand; "
                            "Generic and Product Unbranded must carry '-'")
        key = kw["keyword"].strip().lower()
        if key in seen:
            raise DataError(f"duplicate keyword in basket: {kw['keyword']!r}")
        seen.add(key)
    if basket["focus_brand"] not in {k["brand"] for k in basket["keywords"]}:
        raise DataError(f"focus_brand {basket['focus_brand']!r} has no keywords in basket")
    return basket


# ---------- volumes store (merge-preserving history) ----------

VOLUME_FIELDS = ["keyword", "month", "volume"]


def load_volumes(path: Path) -> dict[tuple[str, str], int]:
    """{(keyword_lower, YYYY-MM): volume}"""
    out: dict[tuple[str, str], int] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in VOLUME_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise DataError(f"volumes file missing columns {missing} (has {reader.fieldnames})")
        for i, row in enumerate(reader, 2):
            kw = row["keyword"].strip().lower()
            m = month_key(row["month"])
            v = parse_volume(row["volume"], context=f"(row {i}: {kw} {m})")
            key = (kw, m)
            if key in out and out[key] != v:
                raise DataError(f"conflicting duplicate row for {kw!r} {m}: "
                                f"{out[key]} vs {v}")
            out[key] = v
    return out


def save_volumes(path: Path, volumes: dict[tuple[str, str], int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(VOLUME_FIELDS)
        for (kw, m), v in sorted(volumes.items()):
            w.writerow([kw, m, v])


def merge_volumes(existing: dict[tuple[str, str], int],
                  fresh: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """Fresh wins on overlap; older history is preserved. Never deletes."""
    out = dict(existing)
    out.update(fresh)
    return out


# ---------- deterministic output ----------

def dump_json(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)
