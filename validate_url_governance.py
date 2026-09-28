#!/usr/bin/env python3
"""Validate OOF URL stability, canonical agreement, aliases, and version identity."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_ai_compatibility as ai
import build_url_governance as governance


ROOT = Path(__file__).resolve().parents[1]


def new_html_paths() -> set[str]:
    commands = (
        ["git", "-c", "core.autocrlf=false", "diff", "HEAD", "--name-only", "--diff-filter=A", "--", "*.html"],
        ["git", "-c", "core.autocrlf=false", "ls-files", "--others", "--exclude-standard", "--", "*.html"],
    )
    paths = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
        paths.update(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())
    return paths


def deleted_html_paths() -> set[str]:
    commands = [["git", "-c", "core.autocrlf=false", "diff", "HEAD", "--name-only", "--diff-filter=D", "--", "*.html"]]
    if os.environ.get("GITHUB_ACTIONS"):
        commands.append(
            ["git", "-c", "core.autocrlf=false", "diff", "HEAD^", "HEAD", "--name-only", "--diff-filter=D", "--", "*.html"]
        )
    paths = set()
    for command in commands:
        try:
            output = subprocess.check_output(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
        paths.update(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())
    return paths


def new_path_is_safe(path: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9/_-]*\.html", path)) and "//" not in path and "_" not in path


def main() -> int:
    errors = []
    pages = ai.public_pages()
    page_paths = {ai.relative_url(path) for path in pages}
    canonical_page_paths = {path for path in page_paths if ai.alias_target(path) is None}
    registry = json.loads(governance.REGISTRY_PATH.read_text(encoding="utf-8"))
    aliases = json.loads(governance.ALIAS_PATH.read_text(encoding="utf-8"))
    versions = json.loads(governance.VERSION_PATH.read_text(encoding="utf-8"))
    resources = registry.get("resources", [])
    registry_paths = {item.get("path") for item in resources}

    if registry_paths != canonical_page_paths:
        errors.append("URL registry and public HTML page sets differ")
    if len(registry_paths) != len(resources):
        errors.append("URL registry contains duplicate paths")
    canonical_urls = {item.get("canonicalUrl") for item in resources}
    if len(canonical_urls) != len(resources):
        errors.append("URL registry contains duplicate canonical URLs")
    for item in resources:
        if item.get("storedCanonicalPath") != item.get("path"):
            errors.append(f"Stored canonical path drift: {item.get('path')}")
        if item.get("governanceAction") != "KEEP+OPTIMIZE":
            errors.append(f"Unapproved URL governance action: {item.get('path')}")
        if item.get("canonicalUrl") != ai.canonical_url(item.get("path")):
            errors.append(f"Canonical URL does not match preserved path: {item.get('path')}")

    sitemap_root = ET.parse(ROOT / "sitemap.xml").getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = {element.text for element in sitemap_root.findall("sm:url/sm:loc", ns)}
    if sitemap_urls != canonical_urls:
        errors.append("Sitemap and URL registry canonical sets differ")

    alias_sources = set()
    alias_targets = set()
    for item in aliases.get("aliases", []):
        source = item.get("sourcePath", "")
        target = item.get("canonicalPath", "")
        if source in alias_sources:
            errors.append(f"Duplicate alias source: {source}")
        alias_sources.add(source)
        alias_targets.add(target)
        if source == target:
            errors.append(f"Self-referencing alias: {source}")
        if target not in canonical_page_paths:
            errors.append(f"Alias target is not canonical public content: {target}")
        if source not in page_paths:
            errors.append(f"Preserved alias source is missing: {source}")
        elif item.get("resolution") != "canonical+noindex":
            errors.append(f"Alias lacks canonical+noindex resolution: {source}")
        else:
            alias_source = (ROOT / source).read_text(encoding="utf-8")
            if 'content="noindex, follow"' not in alias_source:
                errors.append(f"Alias source is indexable: {source}")
            expected = ai.canonical_url(target)
            if f'<link rel="canonical" href="{expected}"' not in alias_source:
                errors.append(f"Alias canonical target differs: {source}")
    if alias_sources & alias_targets:
        errors.append("Alias registry contains a redirect chain")

    for path in sorted(deleted_html_paths()):
        if path not in alias_sources:
            errors.append(f"Deleted or renamed public URL lacks an approved 301 alias mapping: {path}")

    for path in sorted(new_html_paths()):
        if not new_path_is_safe(path):
            errors.append(f"New URL violates lowercase ASCII hyphen rules: {path}")

    version_paths = set()
    for item in versions.get("resources", []):
        path = item.get("resourcePath")
        if path in version_paths:
            errors.append(f"Duplicate current version record: {path}")
        version_paths.add(path)
        if path not in canonical_page_paths:
            errors.append(f"Version record points to missing page: {path}")
        if not item.get("version"):
            errors.append(f"Version record lacks explicit version identity: {path}")
        elif path in canonical_page_paths:
            explicit_version = governance.explicit_field((ROOT / path).read_text(encoding="utf-8"), "Version")
            if explicit_version != item.get("version"):
                errors.append(f"Version registry differs from published source metadata: {path}")
        if item.get("authorityState") not in {"current", "superseded"}:
            errors.append(f"Invalid authority state: {path}")

    explicit_version_paths = {
        ai.relative_url(path)
        for path in pages
        if ai.alias_target(ai.relative_url(path)) is None
        if governance.explicit_field(path.read_text(encoding="utf-8"), "Version")
    }
    if explicit_version_paths != version_paths:
        errors.append("Version registry does not exactly match pages with explicit version metadata")

    if errors:
        print("URL governance validation failed:")
        for error in errors[:100]:
            print(f"- {error}")
        return 1
    print(
        f"URL governance validation passed: {len(resources)} URLs preserved, canonical/sitemap agreement, "
        f"{len(version_paths)} explicit version identities, no alias chains, and safe new-URL enforcement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
