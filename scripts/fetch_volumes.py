#!/usr/bin/env python3
"""Fetch monthly search volumes for every basket keyword, into the workspace.

    python3 scripts/fetch_volumes.py --workspace ws/ --provider keyword-planner
    python3 scripts/fetch_volumes.py --workspace ws/ --provider dataforseo
    python3 scripts/fetch_volumes.py --workspace ws/ --provider csv --file export.csv \
        --map keyword=Sökord --map month=Månad --map volume=Sökvolym

Providers, honestly compared:

  keyword-planner  Google Ads Keyword Planner via API. Free, exact source of
                   truth for Google volumes, but requires a Google Ads account
                   with API access (developer token + OAuth). ~4 years of
                   monthly history per call.
  dataforseo       Paid fallback with no Google requirements: DataForSEO's
                   search_volume endpoint (same underlying Keyword Planner
                   data). Needs an API login in the macOS keychain under
                   service "dataforseo-api" (login as account, password as
                   API password). Cost per call is printed to stderr.
  csv              Import any export you already have. Bring your own columns
                   via --map; volumes are parsed locale-safely (a Swedish
                   "8 900" imports as 8900, never as 8).

All providers merge into <workspace>/volumes.csv preserving existing history
(fresh values win on overlap, older months are never deleted), and dump the
raw provider response to <workspace>/runs/ for auditability.
"""
from __future__ import annotations

import argparse
import base64
import csv as csv_mod
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sos_lib import (DataError, die, load_basket, load_volumes, merge_volumes,
                     month_key, parse_volume, save_volumes)

# ---------- provider: csv ----------

def fetch_csv(keywords: list[str], args) -> dict[tuple[str, str], int]:
    if not args.file:
        die("--provider csv requires --file")
    if not Path(args.file).is_file():
        die(f"csv file not found: {args.file}")
    mapping = {"keyword": "keyword", "month": "month", "volume": "volume"}
    for m in args.map or []:
        if "=" not in m:
            die(f"--map must be ours=theirs, got {m!r}")
        ours, theirs = m.split("=", 1)
        if ours not in mapping:
            die(f"--map key must be one of {list(mapping)}, got {ours!r}")
        mapping[ours] = theirs
    wanted = {k.lower() for k in keywords}
    out: dict[tuple[str, str], int] = {}
    skipped = 0
    with open(args.file, newline="", encoding="utf-8-sig") as f:
        reader = csv_mod.DictReader(f)
        for col in mapping.values():
            if col not in (reader.fieldnames or []):
                die(f"csv missing column {col!r} (has {reader.fieldnames})")
        for i, row in enumerate(reader, 2):
            kw = row[mapping["keyword"]].strip().lower()
            if kw not in wanted:
                skipped += 1
                continue
            m = month_key(row[mapping["month"]])
            v = parse_volume(row[mapping["volume"]], context=f"(row {i})")
            if (kw, m) in out and out[(kw, m)] != v:
                raise DataError(f"conflicting duplicate rows for {kw!r} {m}: "
                                f"{out[(kw, m)]} vs {v} (row {i})")
            out[(kw, m)] = v
    if skipped:
        print(f"csv: skipped {skipped} rows for keywords outside the basket", file=sys.stderr)
    return out


# ---------- provider: dataforseo ----------

def _keychain(service: str) -> tuple[str, str]:
    def read(flag: str) -> str:
        r = subprocess.run(["security", "find-generic-password", "-s", service, flag],
                           capture_output=True, text=True)
        if r.returncode != 0:
            die(f"no keychain entry for service {service!r} — add one with: "
                f"security add-generic-password -s {service} -a <login> -w <password>")
        return r.stdout.strip()
    # -w prints the password; account name comes from the entry metadata
    pw = read("-w")
    meta = subprocess.run(["security", "find-generic-password", "-s", service],
                          capture_output=True, text=True).stdout
    acct = ""
    for line in meta.splitlines():
        if '"acct"' in line and "=" in line:
            acct = line.split("=", 1)[1].strip().strip('"')
    if not acct:
        die(f"keychain entry {service!r} has no account (login) set")
    return acct, pw


def fetch_dataforseo(keywords: list[str], args) -> dict[tuple[str, str], int]:
    login, password = _keychain("dataforseo-api")
    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    payload = [{
        "keywords": keywords,
        "location_code": args.dfs_location,
        "language_code": args.language,
        "include_serp_info": False,
    }]
    req = urllib.request.Request(
        "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    cost = body.get("cost")
    print(f"dataforseo cost: ${cost}", file=sys.stderr)
    out: dict[tuple[str, str], int] = {}
    raw_items = []
    for task in body.get("tasks") or []:
        if task.get("status_code") != 20000:
            die(f"dataforseo task failed: {task.get('status_message')}")
        for item in task.get("result") or []:
            raw_items.append(item)
            kw = item["keyword"].strip().lower()
            for ms in item.get("monthly_searches") or []:
                if ms.get("search_volume") is None:
                    continue  # null = no data — must surface as a coverage gap, not a fake 0
                m = f"{ms['year']:04d}-{ms['month']:02d}"
                out[(kw, m)] = int(ms["search_volume"])
    _dump_raw(args.workspace, "dataforseo", raw_items)
    return out


# ---------- provider: keyword-planner ----------

def fetch_keyword_planner(keywords: list[str], args) -> dict[tuple[str, str], int]:
    try:
        from google.ads.googleads.client import GoogleAdsClient  # type: ignore
    except ImportError:
        die("google-ads library not installed — pip install google-ads, "
            "or use --provider dataforseo / csv")
    import yaml  # ships with google-ads

    ads_yaml = Path.home() / "google-ads.yaml"
    adc = Path.home() / ".config/gcloud/application_default_credentials.json"
    if not ads_yaml.exists() or not adc.exists():
        die("keyword-planner needs ~/google-ads.yaml (developer_token, login_customer_id) "
            "and gcloud ADC (run: gcloud auth application-default login)")
    conf = yaml.safe_load(ads_yaml.read_text())
    creds = json.loads(adc.read_text())
    customer_id = str(args.customer_id or conf.get("login_customer_id", "")).replace("-", "")
    if not customer_id:
        die("no customer id — pass --customer-id or set login_customer_id in ~/google-ads.yaml")
    client = GoogleAdsClient.load_from_dict({
        "developer_token": conf["developer_token"],
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "login_customer_id": customer_id,
        "use_proto_plus": True,
    })
    svc = client.get_service("KeywordPlanIdeaService")
    request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.keywords.extend(keywords)
    request.geo_target_constants.append(f"geoTargetConstants/{args.geo_target}")
    request.language = f"languageConstants/{args.language_constant}"
    request.keyword_plan_network = (
        client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH)
    response = svc.generate_keyword_historical_metrics(request=request)

    month_by_name = {n: i + 1 for i, n in enumerate(
        ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
         "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"])}
    out: dict[tuple[str, str], int] = {}
    raw_items = []
    for result in response.results:
        kw = result.text.strip().lower()
        for mv in result.keyword_metrics.monthly_search_volumes:
            # HARD-WON: MonthOfYearEnum is integer-offset (JANUARY=2 … DECEMBER=13),
            # so int(mv.month) silently shifts every month by one. Convert via the
            # enum NAME — the only reading that cannot drift.
            month_num = month_by_name[mv.month.name]
            m = f"{mv.year:04d}-{month_num:02d}"
            out[(kw, m)] = int(mv.monthly_searches or 0)
            raw_items.append({"keyword": kw, "month": m, "month_name": mv.month.name,
                              "volume": int(mv.monthly_searches or 0)})
    _dump_raw(args.workspace, "keyword-planner", raw_items)
    return out


def _dump_raw(workspace: Path, provider: str, items: list) -> None:
    runs = workspace / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamps = set()
    for i in items:
        if not isinstance(i, dict):
            continue
        if "month" in i:
            stamps.add(i["month"])
        for ms in i.get("monthly_searches") or []:
            stamps.add(f"{ms['year']:04d}-{ms['month']:02d}")
    stamp = max(stamps) if stamps else "run"
    path = runs / f"{provider}-{stamp}.json"
    path.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8")
    print(f"raw response → {path}", file=sys.stderr)


PROVIDERS = {"csv": fetch_csv, "dataforseo": fetch_dataforseo,
             "keyword-planner": fetch_keyword_planner}


def main() -> None:
    ap = argparse.ArgumentParser(description="fetch monthly volumes into the workspace")
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    ap.add_argument("--file", type=Path, help="csv provider: the export to import")
    ap.add_argument("--map", action="append", metavar="ours=theirs",
                    help="csv provider: column mapping (keyword=…, month=…, volume=…)")
    ap.add_argument("--dfs-location", type=int, default=2752,
                    help="dataforseo location_code (default 2752 = Sweden)")
    ap.add_argument("--language", default="sv", help="dataforseo language_code")
    ap.add_argument("--customer-id", default="",
                    help="keyword-planner: Google Ads customer id (default: "
                         "login_customer_id from ~/google-ads.yaml)")
    ap.add_argument("--geo-target", default="2752",
                    help="keyword-planner geoTargetConstant id (default 2752 = Sweden)")
    ap.add_argument("--language-constant", default="1015",
                    help="keyword-planner languageConstant id (default 1015 = Swedish)")
    args = ap.parse_args()

    try:
        basket = load_basket(args.workspace / "basket.json")
    except DataError as e:
        die(str(e))
    if (args.provider in ("dataforseo", "keyword-planner")
            and str(basket.get("geo", "")).upper() != "SE"
            and args.dfs_location == 2752 and args.geo_target == "2752"):
        die(f"basket geo is {basket.get('geo')!r} but the provider location flags are at "
            "their Sweden defaults — pass --dfs-location/--language (dataforseo) or "
            "--geo-target/--language-constant (keyword-planner) for your market")
    keywords = sorted({k["keyword"].strip().lower() for k in basket["keywords"]})
    try:
        fresh = PROVIDERS[args.provider](keywords, args)
    except DataError as e:
        die(str(e))
    if not fresh:
        die("provider returned no data")

    store = args.workspace / "volumes.csv"
    existing = load_volumes(store)
    merged = merge_volumes(existing, fresh)
    save_volumes(store, merged)
    fresh_months = sorted({m for (_, m) in fresh})
    print(f"{len(fresh)} datapoints fetched ({fresh_months[0]} … {fresh_months[-1]}), "
          f"store now {len(merged)} rows → {store}")


if __name__ == "__main__":
    main()
