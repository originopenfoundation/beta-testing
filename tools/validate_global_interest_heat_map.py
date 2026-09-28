#!/usr/bin/env python3
"""Validate the public OOF Global Interest Heat Map payload."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data" / "oof-global-interest-heat-map.json"
STATUSES = {"high", "moderate", "emerging"}
MOMENTUM = {"rapidly-rising", "rising", "stable", "declining"}
FORBIDDEN_KEYS = {
    "visitors", "visitorCount", "sessions", "sessionCount", "population",
    "rawEngagement", "normalizedScore", "score", "reliabilityScore",
    "analyticsId", "deviceId", "userId", "ip", "ipAddress"
}


def validate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"generatedAt", "countries"}:
        raise ValueError("Public payload must contain only generatedAt and countries")
    generated_at = payload["generatedAt"]
    if not isinstance(generated_at, str):
        raise ValueError("generatedAt must be an ISO-8601 string")
    datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    countries = payload["countries"]
    if not isinstance(countries, list):
        raise ValueError("countries must be an array")
    seen: set[str] = set()
    for index, country in enumerate(countries):
        if not isinstance(country, dict):
            raise ValueError(f"countries[{index}] must be an object")
        extras = set(country) - {"iso", "status", "momentum"}
        forbidden = set(country) & FORBIDDEN_KEYS
        if extras or forbidden:
            raise ValueError(f"countries[{index}] exposes unsupported fields: {sorted(extras | forbidden)}")
        iso = country.get("iso")
        if not isinstance(iso, str) or not re.fullmatch(r"[A-Z]{2}", iso):
            raise ValueError(f"countries[{index}].iso must be an ISO alpha-2 code")
        if iso in seen:
            raise ValueError(f"Duplicate country code: {iso}")
        if iso == "AQ":
            raise ValueError("Antarctica must not be published in the interest heat map")
        seen.add(iso)
        if country.get("status") not in STATUSES:
            raise ValueError(f"Invalid public status for {iso}")
        if "momentum" in country and country["momentum"] not in MOMENTUM:
            raise ValueError(f"Invalid momentum for {iso}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    payload = validate(args.path)
    print(f"Global Interest Heat Map dataset valid: {len(payload['countries'])} classified countries")


if __name__ == "__main__":
    main()
