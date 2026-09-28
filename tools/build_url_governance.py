#!/usr/bin/env python3
"""Build non-destructive URL, alias-candidate, and version registries for OOF."""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from pathlib import Path

import build_ai_compatibility as ai


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGISTRY_PATH = DATA / "oof-url-registry.json"
ALIAS_PATH = DATA / "oof-url-alias-registry.json"
VERSION_PATH = DATA / "oof-version-registry.json"
AUDIT_PATH = DATA / "oof-url-governance-audit.json"


def clean_markup(value: str) -> str:
    return ai.clean_text(re.sub(r"<[^>]+>", " ", value))


def explicit_field(source: str, name: str) -> str | None:
    patterns = (
        rf"<(?:b|strong)>\s*{re.escape(name)}\s*:\s*</(?:b|strong)>\s*(.*?)(?=<br\s*/?>|</p>|</a>|</div>)",
        rf"<(?:b|strong)>\s*{re.escape(name)}\s*:\s*</(?:b|strong)>\s*</?[^>]*>?(.*?)(?=<br\s*/?>|</p>|</a>|</div>)",
    )
    for pattern in patterns:
        match = re.search(pattern, source, re.I | re.S)
        if match:
            value = clean_markup(match.group(1))
            if value:
                return value
    return None


def first_heading(source: str, fallback: str) -> str:
    match = re.search(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", source, re.I | re.S)
    return clean_markup(match.group(1)) if match else fallback


def legacy_path_risks(relative: str) -> list[str]:
    path = relative.removesuffix(".html")
    risks = []
    if any(character.isupper() for character in path):
        risks.append("uppercase")
    if any(ord(character) > 127 for character in path):
        risks.append("nonAscii")
    if " " in path:
        risks.append("spaces")
    if re.search(r"[™®&()]", path):
        risks.append("specialCharacters")
    if re.search(r"(?:^|[-_/])v?\d+(?:[-.]\d+)+(?:$|[-_/])", path, re.I):
        risks.append("versionLikePath")
    return risks


def normalized_entity_name(value: str) -> str:
    value = html.unescape(value).casefold()
    value = re.sub(r"[™®©]", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def main() -> None:
    paths = ai.public_pages()
    all_records = ai.inspect_pages(paths)
    records = [record for record in all_records if ai.alias_target(record["relative"]) is None]
    resources = []
    versions = []
    title_groups: dict[str, list[dict]] = defaultdict(list)

    for record in records:
        source = record["source"]
        relative = record["relative"]
        title = record["title"]
        display_name = first_heading(source, title)
        version = explicit_field(source, "Version")
        status = explicit_field(source, "Status")
        publication_date = explicit_field(source, "Publication Date")
        superseded_by = explicit_field(source, "Superseded By")
        resource = {
            "path": relative,
            "canonicalUrl": record["canonical"],
            "storedCanonicalPath": relative,
            "displayName": display_name,
            "entityId": record["fields"].get("OriginID") or record["canonical"] + "#webpage",
            "governanceAction": "KEEP+OPTIMIZE",
            "legacyPathRisks": legacy_path_risks(relative),
        }
        resources.append(resource)
        title_groups[normalized_entity_name(display_name)].append(resource)

        if version:
            version_record = {
                "resourcePath": relative,
                "canonicalUrl": record["canonical"],
                "resourceName": display_name,
                "resourceIdentifier": resource["entityId"],
                "version": version,
                "status": status or "",
                "authorityState": "superseded" if status and "superseded" in status.casefold() else "current",
            }
            for key, value in (
                ("publicationDate", publication_date),
                ("architecture", record["fields"].get("Architecture")),
                ("parentStandard", record["fields"].get("Parent Standard")),
                ("supersededBy", superseded_by),
            ):
                if value:
                    version_record[key] = value
            versions.append(version_record)

    migration_candidates = []
    for normalized_name, group in sorted(title_groups.items()):
        if normalized_name and len(group) > 1:
            migration_candidates.append(
                {
                    "normalizedEntityName": normalized_name,
                    "paths": [item["path"] for item in group],
                    "classification": "REVIEW",
                    "reason": "Multiple existing pages expose the same normalized display name; no migration is activated.",
                }
            )

    url_registry = {
        "schemaVersion": "1.0",
        "policy": "Existing public URLs are preserved by default.",
        "defaultAction": "KEEP+OPTIMIZE",
        "resources": resources,
    }
    preserved_aliases = []
    for record in all_records:
        target = ai.alias_target(record["relative"])
        if target:
            preserved_aliases.append(
                {
                    "sourcePath": record["relative"],
                    "sourceUrl": ai.canonical_url(record["relative"]),
                    "canonicalPath": target,
                    "canonicalUrl": ai.canonical_url(target),
                    "resolution": "canonical+noindex",
                    "status": "active",
                }
            )
    alias_registry = {
        "schemaVersion": "1.0",
        "policy": "Only verified historical URLs may become aliases.",
        "aliases": preserved_aliases,
        "migrationCandidates": migration_candidates,
    }
    version_registry = {
        "schemaVersion": "1.0",
        "policy": "Only version data explicitly present in published source pages is recorded.",
        "resources": versions,
    }
    audit = {
        "schemaVersion": "1.0",
        "summary": {
            "publicUrls": len(resources),
            "preservedUrls": len(all_records),
            "activatedAliases": len(preserved_aliases),
            "migrationCandidates": len(migration_candidates),
            "explicitVersionRecords": len(versions),
            "legacyUrlsWithRisks": sum(bool(item["legacyPathRisks"]) for item in resources),
            "renamedUrls": 0,
        },
        "decision": "KEEP+OPTIMIZE",
        "migrationCandidates": migration_candidates,
    }

    DATA.mkdir(parents=True, exist_ok=True)
    for path, payload in (
        (REGISTRY_PATH, url_registry),
        (ALIAS_PATH, alias_registry),
        (VERSION_PATH, version_registry),
        (AUDIT_PATH, audit),
    ):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"URL governance built: {len(resources)} canonical URLs, {len(all_records)} preserved files, "
        f"{len(versions)} explicit version records, "
        f"{len(migration_candidates)} migration candidates, {len(preserved_aliases)} activated aliases."
    )


if __name__ == "__main__":
    main()
