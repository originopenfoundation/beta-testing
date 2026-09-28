#!/usr/bin/env python3
"""Build the public Heat Map payload from aggregated Cloudflare Web Analytics data."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from validate_global_interest_heat_map import validate


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATASET = ROOT / "data" / "oof-global-interest-heat-map.json"
INTEREST_ALGORITHM_VERSION = "2.1"
GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
POPULATION_METADATA_URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"
POPULATION_VALUES_URL = "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=5000&date=2020:2025"
HOST = "originopenfoundation.org"
WINDOW_DAYS = 14
MIN_VISITS = 10.0
MIN_ACTIVE_DAYS = 2


def request_json(url: str, *, token: str | None = None, payload: dict | None = None) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "OOF-Global-Interest-Heat-Map/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def cloudflare_rows(account_id: str, site_tag: str, token: str, start: datetime, end: datetime) -> list[dict]:
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
        raise ValueError("CLOUDFLARE_ACCOUNT_ID must be a 32-character hexadecimal ID")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", site_tag):
        raise ValueError("CLOUDFLARE_WEB_ANALYTICS_SITE_TAG must be a 32-character hexadecimal ID")
    start_value = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_value = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = f'''query {{
      viewer {{
        accounts(filter: {{ accountTag: "{account_id}" }}) {{
          rows: rumPageloadEventsAdaptiveGroups(
            limit: 10000
            orderBy: [sum_visits_DESC]
            filter: {{ AND: [
              {{ datetime_geq: "{start_value}", datetime_leq: "{end_value}" }}
              {{ siteTag: "{site_tag}" }}
              {{ requestHost: "{HOST}" }}
              {{ bot: 0 }}
            ] }}
          ) {{
            sum {{ visits }}
            dimensions {{ countryName date }}
          }}
        }}
      }}
    }}'''
    result = request_json(GRAPHQL_URL, token=token, payload={"query": query, "variables": {}})
    if not isinstance(result, dict) or result.get("errors"):
        raise RuntimeError(f"Cloudflare Analytics query failed: {result.get('errors') if isinstance(result, dict) else result}")
    accounts = result.get("data", {}).get("viewer", {}).get("accounts", [])
    if not accounts:
        raise RuntimeError("Cloudflare Analytics returned no account data")
    return accounts[0].get("rows", [])


def population_data() -> tuple[dict[str, int], dict[str, str], str]:
    metadata_response = request_json(POPULATION_METADATA_URL)
    values_response = request_json(POPULATION_VALUES_URL)
    metadata = metadata_response[1] if isinstance(metadata_response, list) and len(metadata_response) > 1 else []
    values = values_response[1] if isinstance(values_response, list) and len(values_response) > 1 else []
    iso3_to_iso2: dict[str, str] = {}
    names_to_iso2: dict[str, str] = {}
    for country in metadata:
        iso2 = str(country.get("iso2Code") or "").upper()
        iso3 = str(country.get("id") or "").upper()
        region = country.get("region") or {}
        if re.fullmatch(r"[A-Z]{2}", iso2) and region.get("value") != "Aggregates":
            iso3_to_iso2[iso3] = iso2
            names_to_iso2[str(country.get("name") or "").casefold()] = iso2
    populations: dict[str, int] = {}
    years: list[int] = []
    for row in values:
        value = row.get("value")
        iso3 = str(row.get("countryiso3code") or "").upper()
        iso2 = iso3_to_iso2.get(iso3)
        if iso2 and value is not None and iso2 not in populations:
            populations[iso2] = int(value)
            years.append(int(row["date"]))
    if not populations:
        raise RuntimeError("Population source returned no usable country data")
    return populations, names_to_iso2, str(max(years))


def resolve_iso(value: str, names_to_iso2: dict[str, str]) -> str | None:
    candidate = (value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", candidate):
        iso = candidate.upper()
        return None if iso == "AQ" else iso
    iso = names_to_iso2.get(candidate.casefold())
    return None if iso == "AQ" else iso


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def classify(
    rows: list[dict], populations: dict[str, int], names_to_iso2: dict[str, str], now: datetime
) -> tuple[list[dict], dict]:
    countries: dict[str, dict] = defaultdict(lambda: {"visits": 0.0, "days": set(), "daily": defaultdict(float)})
    for row in rows:
        dimensions = row.get("dimensions") or {}
        iso = resolve_iso(str(dimensions.get("countryName") or ""), names_to_iso2)
        if not iso or iso not in populations:
            continue
        visits = float((row.get("sum") or {}).get("visits") or 0)
        if visits <= 0:
            continue
        day = str(dimensions.get("date") or "")[:10]
        countries[iso]["visits"] += visits
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            countries[iso]["days"].add(day)
            countries[iso]["daily"][day] += visits

    eligible: dict[str, dict] = {}
    for iso, metrics in countries.items():
        visits = metrics["visits"]
        active_days = len(metrics["days"])
        if visits < MIN_VISITS or active_days < MIN_ACTIVE_DAYS:
            continue
        visits_per_million = visits / max(populations[iso], 1) * 1_000_000
        reliability = min(1.0, visits / 30.0) * min(1.0, active_days / 5.0)
        metrics["normalizedScore"] = visits_per_million * reliability
        eligible[iso] = metrics

    scores = [metrics["normalizedScore"] for metrics in eligible.values()]
    high_cutoff = quantile(scores, 0.80)
    moderate_cutoff = quantile(scores, 0.45)
    public: list[dict] = []
    internal: dict[str, dict] = {}
    recent_start = (now - timedelta(days=7)).date().isoformat()
    prior_start = (now - timedelta(days=14)).date().isoformat()
    for iso, metrics in sorted(countries.items()):
        record = {
            "visits": round(metrics["visits"], 4),
            "activeDays": len(metrics["days"]),
            "population": populations.get(iso),
            "classification": "insufficient",
        }
        if iso in eligible:
            score = eligible[iso]["normalizedScore"]
            if score >= high_cutoff and metrics["visits"] >= 30 and len(metrics["days"]) >= 4:
                status = "high"
            elif score >= moderate_cutoff and metrics["visits"] >= 20 and len(metrics["days"]) >= 3:
                status = "moderate"
            else:
                status = "emerging"
            item = {"iso": iso, "status": status}
            recent = sum(value for day, value in metrics["daily"].items() if day >= recent_start)
            prior = sum(value for day, value in metrics["daily"].items() if prior_start <= day < recent_start)
            recent_days = sum(1 for day in metrics["daily"] if day >= recent_start)
            prior_days = sum(1 for day in metrics["daily"] if prior_start <= day < recent_start)
            if recent >= 8 and prior >= 8 and recent_days >= 3 and prior_days >= 3:
                ratio = recent / prior
                item["momentum"] = "rapidly-rising" if ratio >= 1.8 else "rising" if ratio >= 1.2 else "declining" if ratio <= 0.75 else "stable"
            public.append(item)
            record["classification"] = status
            record["normalizedScore"] = round(score, 8)
            record["recentVisits"] = round(recent, 4)
            record["priorVisits"] = round(prior, 4)
        internal[iso] = record
    return public, internal


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False, suffix=".tmp") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    validate(temporary)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-output", type=Path)
    args = parser.parse_args()
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    site_tag = os.environ["CLOUDFLARE_WEB_ANALYTICS_SITE_TAG"]
    token = os.environ["CLOUDFLARE_ANALYTICS_API_TOKEN"]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=WINDOW_DAYS)
    rows = cloudflare_rows(account_id, site_tag, token, start, now)
    populations, names_to_iso2, population_year = population_data()
    public_countries, internal_countries = classify(rows, populations, names_to_iso2, now)
    public_payload = {"generatedAt": now.isoformat().replace("+00:00", "Z"), "countries": public_countries}
    atomic_write(PUBLIC_DATASET, public_payload)
    if args.internal_output:
        args.internal_output.parent.mkdir(parents=True, exist_ok=True)
        args.internal_output.write_text(json.dumps({
            "generatedAt": public_payload["generatedAt"],
            "dataWindowStart": start.isoformat().replace("+00:00", "Z"),
            "dataWindowEnd": public_payload["generatedAt"],
            "algorithmVersion": INTEREST_ALGORITHM_VERSION,
            "populationVersion": f"World Bank SP.POP.TOTL {population_year}",
            "countries": internal_countries,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Published {len(public_countries)} reliable country classifications from {len(rows)} aggregate rows")


if __name__ == "__main__":
    main()
