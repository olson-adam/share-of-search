#!/bin/bash
# share-of-search smoke suite — the gates that keep the numbers honest.
# Usage: bash evals/run.sh [python]   (default: python3). No network needed.
set -u
PY="${1:-python3}"
cd "$(dirname "$0")/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
check() { if [ "$2" = "0" ]; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; fail=$((fail+1)); fi; }

# 1. demo regenerates byte-identically and the snapshot reproduces
$PY examples/make_demo.py >/dev/null 2>&1
cp -r examples/demo-workspace "$TMP/ws"
$PY examples/make_demo.py >/dev/null 2>&1
diff -r examples/demo-workspace "$TMP/ws" >/dev/null 2>&1
check "demo: regeneration is byte-identical" $?
$PY scripts/sos_calc.py --workspace "$TMP/ws" --source demo >/dev/null 2>&1
$PY - <<PYEOF
import json
s = json.load(open("$TMP/ws/snapshot.json"))
assert {b["name"]: b["share"] for b in s["brands"]} == \
    {"Zenith": 47.8, "Apex": 30.9, "Acme": 13.1, "Nimbus": 8.2}, "demo shares drifted"
assert s["focus"]["rank"] == 3 and s["focus"]["gap_up"] == 17.8
assert s["focus"]["lead_over_2"] is None, "lead_over_2 only for rank 1"
assert abs(sum(b["share"] for b in s["brands"]) - 100.0) < 0.21, "shares must sum to ~100"
assert "capture" in s and s["capture"]["site"] == "sc-domain:acme.example"
assert "your site only" in s["capture"]["note"], "capture must carry its honesty note"
assert "yield" in s and "query dimension" in s["yield"]["note"]
PYEOF
check "calc: demo snapshot reproduces exact shares" $?

# 2. determinism: two runs, byte-identical snapshots
$PY scripts/sos_calc.py --workspace "$TMP/ws" --out "$TMP/a.json" --source x >/dev/null 2>&1
$PY scripts/sos_calc.py --workspace "$TMP/ws" --out "$TMP/b.json" --source x >/dev/null 2>&1
cmp -s "$TMP/a.json" "$TMP/b.json"
check "calc: byte-identical across runs" $?

# 3. THE locale bug as a fixture: "8 900" with NBSP must parse as 8900, never 8
$PY - <<PYEOF
import sys; sys.path.insert(0, "scripts")
from sos_lib import parse_volume, DataError
assert parse_volume("8 900") == 8900, "NBSP thousands separator mangled"
assert parse_volume("8 900") == 8900
assert parse_volume("1'234") == 1234
try:
    parse_volume("8,9"); raise SystemExit("ambiguous decimal accepted")
except DataError:
    pass
try:
    parse_volume("n/a"); raise SystemExit("garbage accepted")
except DataError:
    pass
PYEOF
check "locale: the 8 900→8 bug can never return" $?

# 4. validation: month gap is an error, orphan keyword is an error
cp -r "$TMP/ws" "$TMP/gap"
$PY - <<PYEOF
import csv
rows = [r for r in csv.DictReader(open("$TMP/gap/volumes.csv"))]
rows = [r for r in rows if r["month"] != "2025-09"]  # tear a hole in history
w = csv.DictWriter(open("$TMP/gap/volumes.csv", "w", newline=""), fieldnames=["keyword","month","volume"])
w.writeheader(); w.writerows(rows)
PYEOF
$PY scripts/validate.py --workspace "$TMP/gap" >/dev/null 2>&1; [ $? -eq 2 ]
check "validate: month gap stops the pipeline" $?
cp -r "$TMP/ws" "$TMP/orph"
echo "mystery keyword,2026-07,500" >> "$TMP/orph/volumes.csv"
$PY scripts/validate.py --workspace "$TMP/orph" >/dev/null 2>&1; [ $? -eq 2 ]
check "validate: orphan keyword (not in basket) stops the pipeline" $?

# 5. calc refuses to produce a snapshot on validation errors
$PY scripts/sos_calc.py --workspace "$TMP/gap" --out "$TMP/never.json" >/dev/null 2>&1
[ $? -ne 0 ] && [ ! -f "$TMP/never.json" ]
check "calc: no snapshot when validation fails" $?

# 6. basket rules: type/brand consistency + duplicates rejected
$PY - <<PYEOF
import sys, json; sys.path.insert(0, "scripts")
from pathlib import Path
from sos_lib import load_basket, DataError
b = json.load(open("$TMP/ws/basket.json"))
b["keywords"][0]["type"] = "Generic"  # branded keyword mislabeled as Generic
Path("$TMP/bad1.json").write_text(json.dumps(b))
try:
    load_basket(Path("$TMP/bad1.json")); raise SystemExit("mislabel accepted")
except DataError: pass
b = json.load(open("$TMP/ws/basket.json"))
b["keywords"].append(dict(b["keywords"][0]))
Path("$TMP/bad2.json").write_text(json.dumps(b))
try:
    load_basket(Path("$TMP/bad2.json")); raise SystemExit("duplicate accepted")
except DataError: pass
PYEOF
check "basket: mislabels and duplicates rejected" $?

# 7. csv provider: Swedish-column import with locale volumes round-trips
mkdir -p "$TMP/se"
cp "$TMP/ws/basket.json" "$TMP/se/"
$PY - <<PYEOF
import csv
rows = list(csv.DictReader(open("$TMP/ws/volumes.csv")))
with open("$TMP/se/export.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Sökord", "Månad", "Sökvolym"])
    for r in rows:
        v = int(r["volume"])
        pretty = f"{v:,}".replace(",", " ")  # Swedish NBSP thousands
        w.writerow([r["keyword"], r["month"], pretty])
PYEOF
$PY scripts/fetch_volumes.py --workspace "$TMP/se" --provider csv --file "$TMP/se/export.csv" \
  --map "keyword=Sökord" --map "month=Månad" --map "volume=Sökvolym" >/dev/null 2>&1
cmp -s <(sort "$TMP/se/volumes.csv") <(sort "$TMP/ws/volumes.csv")
check "csv provider: locale export round-trips exactly" $?

# 8. merge preserves history: re-import of a subset must not delete old months
cp -r "$TMP/ws" "$TMP/merge"
$PY - <<PYEOF
import csv
rows = [r for r in csv.DictReader(open("$TMP/merge/volumes.csv")) if r["month"] >= "2026-06"]
with open("$TMP/merge/partial.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["keyword","month","volume"]); w.writeheader(); w.writerows(rows)
PYEOF
$PY scripts/fetch_volumes.py --workspace "$TMP/merge" --provider csv --file "$TMP/merge/partial.csv" >/dev/null 2>&1
$PY - <<PYEOF
import sys; sys.path.insert(0, "scripts")
from pathlib import Path
from sos_lib import load_volumes
v = load_volumes(Path("$TMP/merge/volumes.csv"))
months = sorted({m for (_, m) in v})
assert months[0] == "2025-02" and months[-1] == "2026-07", f"history lost: {months[0]}..{months[-1]}"
PYEOF
check "merge: partial refresh never deletes history" $?

# 9. serve --export produces a single self-contained HTML
$PY scripts/serve.py --export "$TMP/report.html" >/dev/null 2>&1
$PY - <<PYEOF
h = open("$TMP/report.html").read()
assert "window.__SNAPSHOT__" in h, "snapshot not embedded"
assert "<style>" in h and '<script type="module">' in h, "assets not inlined"
assert 'src="/assets' not in h and 'href="/assets' not in h, "external asset refs remain"
PYEOF
check "export: single-file report, everything embedded" $?

# 10. outlier guard catches DOWNWARD mangling (the 8 900→8 shape)
cp -r "$TMP/ws" "$TMP/mangle"
$PY - <<PYEOF
import csv
rows = list(csv.DictReader(open("$TMP/mangle/volumes.csv")))
for r in rows:
    if r["keyword"] == "zenith" and r["month"] == "2026-06":
        r["volume"] = "8"  # a real value mangled down to single digits
w = csv.DictWriter(open("$TMP/mangle/volumes.csv", "w", newline=""), fieldnames=["keyword","month","volume"])
w.writeheader(); w.writerows(rows)
PYEOF
$PY scripts/validate.py --workspace "$TMP/mangle" 2>/dev/null | grep -q "outlier jump for 'zenith'"
check "validate: downward-mangled volume flagged as outlier" $?

# 11. rank-1 semantics: leader gets lead_over_2, never gap_up
mkdir -p "$TMP/leader"
$PY - <<PYEOF
import json
b = json.load(open("$TMP/ws/basket.json"))
b["focus_brand"] = "Zenith"
open("$TMP/leader/basket.json", "w").write(json.dumps(b))
PYEOF
cp "$TMP/ws/volumes.csv" "$TMP/leader/"
$PY scripts/sos_calc.py --workspace "$TMP/leader" --source demo >/dev/null 2>&1
$PY - <<PYEOF
import json
s = json.load(open("$TMP/leader/snapshot.json"))
f = s["focus"]
assert f["rank"] == 1 and f["gap_up"] is None, "rank 1 must have no gap_up"
assert f["lead_over_2"] == 16.9, f"lead_over_2 wrong: {f['lead_over_2']}"
PYEOF
check "calc: rank-1 gets lead_over_2, gap_up is null" $?

# 12. export refuses to emit a file with external refs (tampered dist)
cp -r app/dist "$TMP/dist-tampered"
$PY - <<PYEOF
import re
p = "$TMP/dist-tampered/index.html"
h = open(p).read()
open(p, "w").write(h + '\n<script type="module" src="/assets/extra-notinlined.js"></script>')
PYEOF
SOS_DIST="$TMP/dist-tampered" $PY scripts/serve.py --export "$TMP/tampered.html" >/dev/null 2>&1
[ $? -ne 0 ]
check "export: tampered dist with un-inlinable ref is refused" $?

# 13. malformed ga4.csv degrades to a warning; snapshot still written
cp -r "$TMP/ws" "$TMP/badyield"
printf 'property,month,sessions,engaged_sessions,key_events\n123,not-a-month,10,5,1\n' > "$TMP/badyield/ga4.csv"
$PY scripts/sos_calc.py --workspace "$TMP/badyield" --source demo >/dev/null 2>&1
$PY - <<PYEOF
import json
s = json.load(open("$TMP/badyield/snapshot.json"))
assert "yield" not in s, "malformed yield layer must be skipped"
assert any("yield layer" in w for w in s["validation"]["warnings"]), "skip must be surfaced"
assert s["focus"]["share"] == 13.1, "market layer must survive"
PYEOF
check "calc: malformed ga4.csv degrades, market layer survives" $?

# 14. basket check CLI works and flags single-keyword brands
$PY - <<PYEOF
import json
b = json.load(open("$TMP/ws/basket.json"))
b["keywords"] = [k for k in b["keywords"] if k["keyword"] != "apex crm"]
open("$TMP/thin.json", "w").write(json.dumps(b))
PYEOF
$PY scripts/basket_builder.py check "$TMP/thin.json" 2>/dev/null | grep -q "only 1 keyword"
check "basket check: single-keyword brand flagged" $?

echo; echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
