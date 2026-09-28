#!/usr/bin/env python3
"""Build the public architecture registry from the canonical Architecture Index."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "oof-structured-architecture-index.html"
HEADER_PATH = ROOT / "header.html"
REGISTRY_PATH = ROOT / "data" / "oof-architecture-registry.json"
APPROVED_PATH = ROOT / "data" / "oof-architecture-map-approved.json"
DEVELOPMENT_PATH = ROOT / "data" / "oof-architecture-map-development.json"
AUDIT_PATH = ROOT / "data" / "oof-architecture-map-audit.json"

TAG_RE = re.compile(r"<[^>]+>")
HEADING_RE = re.compile(r"<h[12][^>]*>(.*?)</h[12]>", re.I | re.S)
LINK_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
ARCH_RE = re.compile(
    r"^(?P<acronym>[A-Z][A-Z0-9-]{1,20})[®™]?\s*[—-]\s*(?P<name>.+?Architecture)(?:\s*\(\d+\))?$"
)


def clean(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", value)).split())


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def parse_index() -> list[dict]:
    source = INDEX_PATH.read_text(encoding="utf-8")
    headings = list(HEADING_RE.finditer(source))
    architectures: list[dict] = []
    for position, match in enumerate(headings):
        label = clean(match.group(1))
        parsed = ARCH_RE.match(label)
        if not parsed or label.startswith("OOF® Architecture Standards Index"):
            continue
        end = headings[position + 1].start() if position + 1 < len(headings) else len(source)
        block = source[match.end() : end]
        standards = [
            {"name": clean(text), "url": html.unescape(href)}
            for href, text in LINK_RE.findall(block)
            if clean(text)
        ]
        architectures.append(
            {
                "id": parsed.group("acronym").lower(),
                "acronym": parsed.group("acronym"),
                "acronymLabel": label.split(" ", 1)[0],
                "displayName": label.rsplit(" (", 1)[0],
                "name": parsed.group("name"),
                "status": "completed",
                "source": INDEX_PATH.name,
                "standards": standards,
                "standardCount": len(standards),
                "pages": [],
            }
        )
    return architectures


def parse_navigation(architectures: list[dict]) -> None:
    source = HEADER_PATH.read_text(encoding="utf-8")
    links = [
        {"url": html.unescape(href), "label": clean(text)}
        for href, text in LINK_RE.findall(source)
    ]
    for architecture in architectures:
        acronym = architecture["acronym"]
        candidates = [link for link in links if acronym in link["label"]]
        seen = set()
        ordered = []
        for link in candidates:
            key = link["url"].split("#", 1)[0].casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(link)
        architecture["pages"] = ordered
        about = next((item for item in ordered if item["label"].startswith("About ")), None)
        architecture["primaryPage"] = (about or (ordered[0] if ordered else None))


def validate(architectures: list[dict]) -> list[str]:
    errors = []
    ids = [item["id"] for item in architectures]
    if len(ids) != len(set(ids)):
        errors.append("Architecture Index contains duplicate architecture acronyms.")
    for architecture in architectures:
        if not architecture["standards"]:
            errors.append(f"{architecture['acronym']} has no indexed Parent Standards.")
        for page in architecture["pages"]:
            target = ROOT / page["url"].split("#", 1)[0]
            if not target.exists():
                errors.append(f"{architecture['acronym']} navigation target is missing: {page['url']}")
    return errors


def approve(acronym: str) -> None:
    approved = read_json(APPROVED_PATH, {"approved": []})
    value = acronym.upper()
    if value not in approved["approved"]:
        approved["approved"].append(value)
        approved["approved"].sort()
        APPROVED_PATH.write_text(json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", metavar="ACRONYM", help="Approve a completed architecture for public map display")
    args = parser.parse_args()
    if args.approve:
        approve(args.approve)

    architectures = parse_index()
    parse_navigation(architectures)
    approved = set(read_json(APPROVED_PATH, {"approved": []})["approved"])
    development = read_json(DEVELOPMENT_PATH, {"architectures": []})["architectures"]
    completed_ids = {item["acronym"] for item in architectures}
    public_architectures = [item for item in architectures if item["acronym"] in approved]
    pending = [item["acronym"] for item in architectures if item["acronym"] not in approved]
    blue = [item for item in development if item["acronym"] not in completed_ids]
    upgrades = [item["acronym"] for item in development if item["acronym"] in completed_ids]
    errors = validate(architectures)

    REGISTRY_PATH.write_text(
        json.dumps(
            {
                "schemaVersion": "2.0",
                "sourceOfTruth": INDEX_PATH.name,
                "architectures": public_architectures,
                "developmentArchitectures": blue,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    AUDIT_PATH.write_text(
        json.dumps(
            {
                "completedDetected": len(architectures),
                "completedPublished": len(public_architectures),
                "developmentPublished": len(blue),
                "pendingApproval": pending,
                "blueToGreenCandidates": upgrades,
                "errors": errors,
                "status": "pass" if not errors else "review-required",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Architecture registry: {len(public_architectures)} published, "
        f"{len(blue)} in development, {len(pending)} pending approval, {len(errors)} errors."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
