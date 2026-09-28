#!/usr/bin/env python3
"""Submit canonical OOF URLs to IndexNow when deployment secrets are available."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.indexnow.org/indexnow"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    key_location = os.environ.get("INDEXNOW_KEY_LOCATION", "").strip()
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    urls = [part.split("</loc>", 1)[0] for part in sitemap.split("<loc>")[1:]]
    if not key or not key_location:
        print("IndexNow skipped: INDEXNOW_KEY and INDEXNOW_KEY_LOCATION are not configured.")
        return 0
    payload = {
        "host": "originopenfoundation.org",
        "key": key,
        "keyLocation": key_location,
        "urlList": urls[:10000],
    }
    if args.dry_run:
        print(f"IndexNow payload ready for {len(payload['urlList'])} URLs.")
        return 0
    request = Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        print(f"IndexNow response: HTTP {response.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
