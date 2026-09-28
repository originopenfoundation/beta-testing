#!/usr/bin/env python3
"""Audit OOF crawlability, internal links, hierarchy, and citation metadata."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections import Counter, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "oof-discovery-audit.json"
PUBLIC_EXCLUDES = {"exports", ".tmp", "tmp"}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href.strip())


def public_pages() -> list[Path]:
    return sorted(
        (
            path
            for path in ROOT.rglob("*.html")
            if ".git" not in path.parts
            and not (path.relative_to(ROOT).parts and path.relative_to(ROOT).parts[0] in PUBLIC_EXCLUDES)
            and "</head>" in path.read_text(encoding="utf-8").lower()
            and not re.search(
                r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex',
                path.read_text(encoding="utf-8"),
                re.I,
            )
        ),
        key=lambda path: path.relative_to(ROOT).as_posix().casefold(),
    )


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def resolve_link(source: str, href: str, shared_navigation: bool = False) -> str | None:
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc and parsed.netloc.casefold() not in {"originopenfoundation.org", "www.originopenfoundation.org"}:
        return None
    path = unquote(parsed.path.replace("\\", "/"))
    if not path:
        return "index.html"
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    if path.startswith("../") or path.startswith("./"):
        base = Path(source).parent
        candidate = (base / path).as_posix()
        parts: list[str] = []
        for part in candidate.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        return "/".join(parts)
    if shared_navigation or "/" in path:
        return posixpath.normpath(path)
    return (Path(source).parent / path).as_posix()


def parse_links(path: Path) -> list[str]:
    parser = LinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail when internal links are broken.")
    args = parser.parse_args()

    pages = public_pages()
    page_names = {relative(path) for path in pages}
    all_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and not (path.relative_to(ROOT).parts and path.relative_to(ROOT).parts[0] in PUBLIC_EXCLUDES)
    }
    casefold_files = {name.casefold(): name for name in all_files}
    shared_links = []
    for shared in (ROOT / "header.html", ROOT / "footer.html"):
        if shared.is_file():
            shared_links.extend(parse_links(shared))

    graph: dict[str, set[str]] = {name: set() for name in page_names}
    broken: list[dict] = []
    case_mismatches: list[dict] = []
    heading_counts = Counter()
    stable_id_pages = 0
    pages_with_headings = 0
    breadcrumb_pages = 0
    semantic_pages = 0

    for path in pages:
        name = relative(path)
        source = path.read_text(encoding="utf-8")
        h1_count = len(re.findall(r"<h1\b", source, re.I))
        heading_counts[str(h1_count)] += 1
        headings = re.findall(r"<h[1-6]\b([^>]*)>", source, re.I)
        if headings:
            pages_with_headings += 1
        if headings and all("data-oof-section-id" in attrs and re.search(r'\bid=["\'][^"\']+["\']', attrs, re.I) for attrs in headings):
            stable_id_pages += 1
        if '"@type":"BreadcrumbList"' in source or '"@type": "BreadcrumbList"' in source:
            breadcrumb_pages += 1
        if re.search(r"<main\b", source, re.I) and re.search(r"<article\b", source, re.I):
            semantic_pages += 1

        source_links = [(href, False) for href in parse_links(path)] + [(href, True) for href in shared_links]
        for href, shared_navigation in source_links:
            target = resolve_link(name, href, shared_navigation)
            if target is None:
                continue
            directory_index = f"{target.rstrip('/')}/index.html" if target != "index.html" else target
            if target not in all_files and directory_index in all_files:
                target = directory_index
            if target in all_files:
                if target in page_names:
                    graph[name].add(target)
                continue
            actual = casefold_files.get(target.casefold())
            issue = {"source": name, "href": href, "resolvedTarget": target}
            if actual:
                issue["actualTarget"] = actual
                case_mismatches.append(issue)
            else:
                broken.append(issue)

    indegree = Counter()
    for targets in graph.values():
        indegree.update(targets)
    excluded = {"index.html"}
    orphans = sorted(name for name in page_names if name not in excluded and indegree[name] == 0)

    depth: dict[str, int] = {"index.html": 0}
    queue = deque(["index.html"])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, set()):
            if target not in depth:
                depth[target] = depth[current] + 1
                queue.append(target)
    unreachable = sorted(page_names - set(depth))
    max_depth = max(depth.values(), default=0)

    unique_broken = list({(item["source"], item["href"], item["resolvedTarget"]): item for item in broken}.values())
    unique_case = list({(item["source"], item["href"], item["resolvedTarget"]): item for item in case_mismatches}.values())
    report = {
        "schemaVersion": "1.0",
        "summary": {
            "publicPages": len(pages),
            "stableSectionIdPages": stable_id_pages,
            "pagesWithHeadings": pages_with_headings,
            "breadcrumbPages": breadcrumb_pages,
            "semanticMainArticlePages": semantic_pages,
            "brokenInternalLinks": len(unique_broken),
            "caseMismatchLinks": len(unique_case),
            "orphanPages": len(orphans),
            "unreachablePages": len(unreachable),
            "maximumCrawlDepth": max_depth,
        },
        "h1CountDistribution": dict(sorted(heading_counts.items(), key=lambda item: int(item[0]))),
        "brokenInternalLinks": unique_broken,
        "caseMismatchLinks": unique_case,
        "orphanPages": orphans,
        "unreachablePages": unreachable,
        "crawlDepth": dict(sorted(depth.items())),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], indent=2))
    if args.strict and (unique_broken or unique_case):
        print("Discovery audit failed because internal link errors remain.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
