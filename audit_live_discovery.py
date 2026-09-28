#!/usr/bin/env python3
"""Check live OOF crawler access and indexability signals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "oof-live-discovery-audit.json"
CRAWLERS = ("OAI-SearchBot", "Googlebot", "Bingbot", "ClaudeBot")
RESOURCES = (
    "robots.txt",
    "sitemap.xml",
    "llms.txt",
    "data/oof-site-knowledge-graph.json",
    "data/oof-url-registry.json",
    "data/oof-url-alias-registry.json",
    "data/oof-version-registry.json",
)


def fetch(url: str, user_agent: str) -> dict:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/xml,text/plain,*/*"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(250000).decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "contentType": response.headers.get("Content-Type", ""),
                "xRobotsTag": response.headers.get("X-Robots-Tag", ""),
                "body": body,
            }
    except HTTPError as error:
        return {"status": error.code, "error": str(error), "body": "", "xRobotsTag": ""}
    except URLError as error:
        return {"status": 0, "error": str(error), "body": "", "xRobotsTag": ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://originopenfoundation.org/")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/") + "/"
    checks = []
    errors = []

    for resource in RESOURCES:
        result = fetch(urljoin(base_url, resource), "OOF-Discovery-Audit/1.0")
        checks.append({"kind": "resource", "target": resource, **{key: value for key, value in result.items() if key != "body"}})
        if result["status"] != 200:
            errors.append(f"{resource}: HTTP {result['status']}")

    samples = ("index.html", "content/v/validos-architecture.html")
    for crawler in CRAWLERS:
        for sample in samples:
            result = fetch(urljoin(base_url, sample), crawler)
            checks.append(
                {
                    "kind": "crawler",
                    "crawler": crawler,
                    "target": sample,
                    **{key: value for key, value in result.items() if key != "body"},
                }
            )
            directives = result.get("xRobotsTag", "").casefold()
            body = result.get("body", "").casefold()
            if result["status"] != 200:
                errors.append(f"{crawler} -> {sample}: HTTP {result['status']}")
            if "noindex" in directives or 'name="robots" content="noindex' in body:
                errors.append(f"{crawler} -> {sample}: restrictive indexing directive")
            if '<link rel="canonical"' not in body:
                errors.append(f"{crawler} -> {sample}: canonical link missing")

    report = {"schemaVersion": "1.0", "baseUrl": base_url, "passed": not errors, "errors": errors, "checks": checks}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Live discovery audit: {len(checks)} checks, {len(errors)} errors.")
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
