#!/usr/bin/env python3
"""Validate generated VALIDOS relationships and their static HTML targets."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "oof-relationship-registry.json"
START = "<!-- OOF GOVERNED LINKS START -->"
END = "<!-- OOF GOVERNED LINKS END -->"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    architecture = registry["architecture"]
    standards = architecture["standards"]
    ids = {standard["id"] for standard in standards}

    if len(standards) != 10:
        fail(errors, f"Expected 10 standards, found {len(standards)}")

    for standard in standards:
        if len(standard["modules"]) != 5:
            fail(errors, f'{standard["id"]}: expected 5 modules, found {len(standard["modules"])}')
        if not 3 <= len(standard["compatibleStandards"]) <= 5:
            fail(errors, f'{standard["id"]}: compatibility count must be 3-5')
        for target in standard["compatibleStandards"]:
            if target not in ids:
                fail(errors, f'{standard["id"]}: unknown compatibility target {target}')
            if target == standard["id"]:
                fail(errors, f'{standard["id"]}: self compatibility link')

    registry_urls: list[str] = []
    registry_urls.extend(resource["url"] for resource in architecture["resources"])
    registry_urls.extend(interface["url"] for interface in architecture["crossArchitectureInterfaces"])
    for standard in standards:
        registry_urls.extend([standard["url"], standard["about"]["url"]])
        registry_urls.extend(module["url"] for module in standard["modules"])
    for url in registry_urls:
        if not (ROOT / unquote(url)).is_file():
            fail(errors, f"Missing registry target: {url}")

    validos_pages = sorted((ROOT / "content" / "v").glob("validos-*.html"))
    if len(validos_pages) != 75:
        fail(errors, f"Expected 75 VALIDOS pages, found {len(validos_pages)}")
    generated_count = 0
    for path in validos_pages:
        text = path.read_text(encoding="utf-8")
        if 'type="application/json" href="../../data/oof-relationship-registry.json"' not in text:
            fail(errors, f"Missing registry discovery link: {path.relative_to(ROOT)}")
        match = re.search(re.escape(START) + r"(.*?)" + re.escape(END), text, flags=re.S)
        if not match:
            continue
        generated_count += 1
        parser = LinkParser()
        parser.feed(match.group(1))
        if len(parser.hrefs) != len(set(parser.hrefs)):
            fail(errors, f"Duplicate generated link: {path.relative_to(ROOT)}")
        for href in parser.hrefs:
            target = (path.parent / unquote(href.split("#", 1)[0])).resolve()
            if target == path.resolve():
                fail(errors, f"Generated self-link: {path.relative_to(ROOT)}")
            if not target.is_file():
                fail(errors, f"Broken generated link: {path.relative_to(ROOT)} -> {href}")
    if generated_count != 72:
        fail(errors, f"Expected generated sections on 72 pages, found {generated_count}")

    search_entries = json.loads((ROOT / "search-index.json").read_text(encoding="utf-8"))
    search_urls = {entry["url"] for entry in search_entries}
    for path in validos_pages:
        url = path.relative_to(ROOT).as_posix()
        if url not in search_urls:
            fail(errors, f"Missing search entry: {url}")

    if errors:
        print("VALIDOS governed-link validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALIDOS governed-link validation passed: 75 pages, 10 standards, 50 modules, 0 broken generated links.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
