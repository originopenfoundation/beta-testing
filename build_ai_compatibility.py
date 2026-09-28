#!/usr/bin/env python3
"""Generate non-visual AI discovery metadata for the complete OOF website."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://originopenfoundation.org/"
SITE_NAME = "OOF® — OriginOpen® Foundation"
START = "<!-- OOF AI DISCOVERY START -->"
END = "<!-- OOF AI DISCOVERY END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\s*", re.S)
SECTION_ID_MARKER = "data-oof-section-id"
SEMANTIC_START = "<!-- OOF SEMANTIC CONTENT START -->"
SEMANTIC_END = "<!-- OOF SEMANTIC CONTENT END -->"
FIELD_NAMES = (
    "OriginID",
    "Architecture",
    "Architecture Family",
    "Parent Standard",
    "Category",
    "Subcategory",
    "Type",
    "Governed Space",
    "Version",
    "Publication Date",
    "Superseded By",
    "Status",
    "Canonical Language",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.text_parts: list[str] = []
        self.hrefs: list[str] = []
        self.meta_description = ""
        self.in_title = False
        self.in_heading = False
        self.heading_complete = False
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.ignored += 1
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2"} and not self.heading_complete:
            self.in_heading = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href.strip())
        if tag == "meta":
            attributes = {key.casefold(): value for key, value in attrs if value is not None}
            if attributes.get("name", "").casefold() == "description":
                self.meta_description = clean_text(attributes.get("content", ""))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self.ignored:
            self.ignored -= 1
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2"} and self.in_heading:
            self.in_heading = False
            self.heading_complete = True

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        if self.in_heading:
            self.heading_parts.append(value)
        if not self.ignored:
            self.text_parts.append(value)

    def title(self, fallback: str) -> str:
        value = " ".join(self.title_parts) or " ".join(self.heading_parts) or fallback
        return clean_text(value)

    def document_title(self) -> str:
        return clean_text(" ".join(self.title_parts))

    def heading_title(self) -> str:
        return clean_text(" ".join(self.heading_parts))

    def visible_text(self) -> str:
        return clean_text(" ".join(self.text_parts))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def truncate_description(value: str, limit: int = 160) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    clipped = value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if clipped and clipped[-1] not in ".!?":
        clipped = clipped[: limit - 1].rstrip(" ,;:-") + "."
    return clipped


def generated_description(record: dict) -> str:
    title = record["title"]
    body = record["visibleText"]
    while body.casefold().startswith(title.casefold()):
        body = body[len(title) :].lstrip(" .:-")
    if not body:
        body = f"Official canonical reference published by {SITE_NAME}."
    return truncate_description(f"{title}. {body}")


def assign_descriptions(records: list[dict]) -> None:
    counts = Counter(record["existingDescription"].casefold() for record in records if record["existingDescription"])
    used: set[str] = set()
    for record in records:
        existing = record["existingDescription"]
        if record["relative"] == "index.html":
            description = (
                "OOF® — OriginOpen® Foundation publishes Structured Reality™ standards, governance architectures, "
                "methodology infrastructure, and canonical references."
            )
        elif existing and counts[existing.casefold()] == 1:
            description = truncate_description(existing)
        else:
            description = generated_description(record)
        if description.casefold() in used:
            page_name = Path(record["relative"]).stem.replace("-", " ").replace("_", " ")
            description = truncate_description(
                f'{record["title"]}. Official OOF canonical reference for {page_name}.'
            )
        used.add(description.casefold())
        record["description"] = description


def assign_titles(records: list[dict]) -> None:
    counts = Counter(record["existingTitle"].casefold() for record in records if record["existingTitle"])
    used: set[str] = set()
    for record in records:
        existing = record["existingTitle"]
        heading = record["headingTitle"]
        if record["relative"] == "index.html":
            title = "OOF® — OriginOpen® Foundation | Methodology Infrastructure"
        elif heading and existing and heading.casefold().startswith(existing.casefold()) and len(heading) > len(existing):
            title = heading
        elif not existing or counts[existing.casefold()] > 1:
            title = heading or existing or Path(record["relative"]).stem.replace("-", " ")
        else:
            title = existing
        title = clean_text(title)
        if title.casefold() in used:
            title = clean_text(f'{title} — {Path(record["relative"]).stem.replace("-", " ")}')
        used.add(title.casefold())
        record["title"] = title
        record["schemaType"] = page_type(title, record["relative"])


def alias_target(relative: str) -> str | None:
    if not relative.startswith("content/g/"):
        return None
    candidate = "content/aig/" + Path(relative).name
    return candidate if (ROOT / candidate).is_file() else None


def section_slug(value: str) -> str:
    value = clean_text(re.sub(r"<[^>]+>", " ", value)).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "section"


def public_pages() -> list[Path]:
    pages = []
    candidates = sorted(ROOT.rglob("*.html"), key=lambda item: item.relative_to(ROOT).as_posix().casefold())
    for path in candidates:
        relative_parts = path.relative_to(ROOT).parts
        if ".git" in path.parts or (relative_parts and relative_parts[0] in {"exports", ".tmp", "tmp"}):
            continue
        text = path.read_text(encoding="utf-8")
        if "</head>" in text.lower():
            pages.append(path)
    return pages


def relative_url(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def encoded_path(value: str) -> str:
    return quote(unquote(value), safe="/-._~()")


def canonical_url(path_or_relative: Path | str) -> str:
    relative = relative_url(path_or_relative) if isinstance(path_or_relative, Path) else path_or_relative
    if relative == "index.html":
        return BASE_URL
    if relative.endswith("/index.html"):
        return urljoin(BASE_URL, encoded_path(relative.removesuffix("index.html")))
    return urljoin(BASE_URL, encoded_path(relative))


def extract_fields(source: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field in FIELD_NAMES:
        pattern = re.compile(
            rf"<(?:b|strong)>\s*{re.escape(field)}\s*:\s*</(?:b|strong)>\s*(.*?)(?=<br\s*/?>|</p>|</a>)",
            re.I | re.S,
        )
        match = pattern.search(source)
        if not match:
            continue
        value = clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))
        if value:
            fields[field] = value
    return fields


def resolve_internal_links(page_path: Path, hrefs: list[str], known_urls: set[str]) -> list[str]:
    current = canonical_url(page_path)
    links: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        parsed = urlparse(urljoin(current, href))
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() not in {"", "originopenfoundation.org", "www.originopenfoundation.org"}:
            continue
        relative = unquote(parsed.path.lstrip("/"))
        if not relative or relative not in known_urls:
            continue
        target = canonical_url(relative)
        if target != current and target not in seen:
            seen.add(target)
            links.append(target)
    return links


def page_type(title: str, relative: str) -> str:
    lowered = f"{title} {relative}".casefold()
    if relative == "index.html":
        return "WebPage"
    if any(word in lowered for word in ("index", "architecture map", "site map")):
        return "CollectionPage"
    if "faq" in lowered:
        return "WebPage"
    return "TechArticle" if relative.startswith("content/") else "WebPage"


def inspect_pages(paths: list[Path]) -> list[dict]:
    known_urls = {relative_url(path) for path in paths}
    records = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(source)
        relative = relative_url(path)
        title = parser.title(path.stem.replace("-", " ").strip())
        fields = extract_fields(source)
        records.append(
            {
                "path": path,
                "relative": relative,
                "canonical": canonical_url(relative),
                "title": title,
                "existingTitle": parser.document_title(),
                "headingTitle": parser.heading_title(),
                "language": "en",
                "schemaType": page_type(title, relative),
                "existingDescription": parser.meta_description,
                "fields": fields,
                "links": resolve_internal_links(path, parser.hrefs, known_urls),
                "visibleText": parser.visible_text(),
                "source": source,
            }
        )
    assign_titles(records)
    add_typed_relations(records)
    assign_descriptions(records)
    return records


def relation_type(context: str) -> str:
    value = context.casefold()
    if "cross-architecture" in value or "cross architecture" in value:
        return "crossArchitectureInterface"
    if "standards compatibility" in value or "compatible standard" in value:
        return "standardsCompatibility"
    if "internal module flow" in value or "module architecture" in value:
        return "moduleFlow"
    if "parent resource" in value or "parent standard" in value:
        return "parentResource"
    if "related document" in value or "related resource" in value:
        return "relatedDocument"
    return "relatedLink"


def add_typed_relations(records: list[dict]) -> None:
    by_relative = {record["relative"]: record for record in records}
    known = set(by_relative)
    for record in records:
        source = record["source"]
        current_heading = ""
        relations: list[dict] = []
        seen: set[tuple[str, str]] = set()
        token_re = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1>|<a\b[^>]*href\s*=\s*([\"'])(.*?)\3", re.I | re.S)
        for match in token_re.finditer(source):
            if match.group(1):
                current_heading = clean_text(re.sub(r"<[^>]+>", " ", match.group(2)))
                continue
            href = html.unescape(match.group(4)).strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            parsed = urlparse(urljoin(record["canonical"], href))
            if parsed.netloc.lower() not in {"", "originopenfoundation.org", "www.originopenfoundation.org"}:
                continue
            relative = unquote(parsed.path.lstrip("/")) or "index.html"
            if relative not in known or relative == record["relative"]:
                continue
            kind = relation_type(current_heading)
            target = canonical_url(relative)
            key = (kind, target)
            if key not in seen:
                seen.add(key)
                relations.append({"type": kind, "target": target})
        record["relations"] = relations


def page_json_ld(record: dict) -> dict:
    data: dict = {
        "@context": "https://schema.org",
        "@type": record["schemaType"],
        "@id": record["canonical"] + "#webpage",
        "url": record["canonical"],
        "name": record["title"],
        "description": record["description"],
        "inLanguage": record["language"],
        "isPartOf": {"@id": BASE_URL + "#website"},
        "publisher": {"@id": BASE_URL + "#organization"},
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "@id": record["canonical"] + "#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": BASE_URL},
                {"@type": "ListItem", "position": 2, "name": record["title"], "item": record["canonical"]},
            ],
        },
    }
    if record["schemaType"] == "TechArticle":
        data["headline"] = record["title"]
        data["author"] = {"@id": BASE_URL + "#organization"}
        data["mainEntityOfPage"] = {"@id": record["canonical"] + "#webpage"}
    topics = [
        record["fields"].get(field)
        for field in ("Architecture", "Architecture Family", "Parent Standard", "Category", "Subcategory", "Governed Space")
        if record["fields"].get(field)
    ]
    if topics:
        data["keywords"] = topics
        data["about"] = [{"@type": "Thing", "name": topic} for topic in topics]
    if record["links"]:
        data["relatedLink"] = record["links"]
    citations = [item["target"] for item in record["relations"] if item["type"] in {"standardsCompatibility", "relatedDocument"}]
    parts = [item["target"] for item in record["relations"] if item["type"] == "moduleFlow"]
    parents = [item["target"] for item in record["relations"] if item["type"] == "parentResource"]
    if citations:
        data["citation"] = citations
    if parts:
        data["hasPart"] = [{"@id": target + "#webpage"} for target in parts]
    if parents:
        data["isPartOf"] = [{"@id": BASE_URL + "#website"}] + [
            {"@id": target + "#webpage"} for target in parents
        ]
    if record["fields"].get("OriginID"):
        data["identifier"] = record["fields"]["OriginID"]
    if record["fields"].get("Version"):
        data["version"] = record["fields"]["Version"]
    if record["fields"].get("Status"):
        data["creativeWorkStatus"] = record["fields"]["Status"]
    if record["fields"]:
        data["additionalProperty"] = [
            {"@type": "PropertyValue", "name": key, "value": value}
            for key, value in record["fields"].items()
        ]
    return data


def metadata_block(record: dict) -> str:
    canonical = html.escape(record["canonical"], quote=True)
    title = html.escape(record["title"], quote=True)
    description = html.escape(record["description"], quote=True)
    json_ld = json.dumps(page_json_ld(record), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    lines = [
            START,
            f'<meta name="description" content="{description}" />',
            f'<link rel="canonical" href="{canonical}" />',
            f'<link rel="alternate" hreflang="en" href="{canonical}" />',
            f'<link rel="alternate" hreflang="x-default" href="{canonical}" />',
            f'<link rel="alternate" type="application/ld+json" href="{BASE_URL}data/oof-site-knowledge-graph.json" title="OOF Site Knowledge Graph" />',
            f'<link rel="alternate" type="text/plain" href="{BASE_URL}llms.txt" title="OOF LLM Index" />',
            '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1" />',
            '<meta name="googlebot" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1" />',
            '<meta name="content-language" content="en" />',
            f'<meta property="og:title" content="{title}" />',
            f'<meta property="og:description" content="{description}" />',
            f'<meta property="og:url" content="{canonical}" />',
            f'<meta property="og:type" content="{"website" if record["relative"] == "index.html" else "article"}" />',
            f'<meta property="og:site_name" content="{html.escape(SITE_NAME, quote=True)}" />',
            '<meta property="og:locale" content="en_US" />',
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{title}" />',
            f'<meta name="twitter:description" content="{description}" />',
            f'<meta name="DC.title" content="{title}" />',
            '<meta name="DC.language" content="en" />',
            f'<meta name="DC.identifier" content="{canonical}" />',
            f'<script type="application/ld+json">{json_ld}</script>',
    ]
    if record["relative"] == "index.html":
        site_entities = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "Organization",
                    "@id": BASE_URL + "#organization",
                    "name": SITE_NAME,
                    "url": BASE_URL,
                    "logo": {
                        "@type": "ImageObject",
                        "url": canonical_url("favicon.png"),
                        "width": 1254,
                        "height": 1254,
                    },
                    "email": "contact@originopenfoundation.org",
                    "sameAs": ["https://github.com/originopenfoundation"],
                },
                {
                    "@type": "WebSite",
                    "@id": BASE_URL + "#website",
                    "name": SITE_NAME,
                    "url": BASE_URL,
                    "inLanguage": "en",
                    "publisher": {"@id": BASE_URL + "#organization"},
                },
            ],
        }
        site_json_ld = json.dumps(site_entities, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        lines.append(f'<script type="application/ld+json">{site_json_ld}</script>')
    lines.append(END)
    return "\n".join(lines)


def inject_metadata(record: dict) -> None:
    path = record["path"]
    source = path.read_text(encoding="utf-8")
    source = BLOCK_RE.sub("", source)
    source = re.sub(
        r'\s*<meta\b(?=[^>]*\bname=["\']description["\'])[^>]*>',
        "",
        source,
        flags=re.I,
    )
    escaped_title = html.escape(record["title"])
    if re.search(r"<title\b[^>]*>.*?</title>", source, re.I | re.S):
        source = re.sub(
            r"<title\b[^>]*>.*?</title>",
            f"<title>{escaped_title}</title>",
            source,
            count=1,
            flags=re.I | re.S,
        )
    else:
        source = re.sub(r"<head\b[^>]*>", lambda match: match.group(0) + f"\n<title>{escaped_title}</title>", source, count=1, flags=re.I)
    source = re.sub(r"</head>", metadata_block(record) + "\n</head>", source, count=1, flags=re.I)
    path.write_text(source, encoding="utf-8", newline="\n")


def inject_alias_metadata(record: dict, target: dict) -> None:
    path = record["path"]
    source = path.read_text(encoding="utf-8")
    source = BLOCK_RE.sub("", source)
    source = re.sub(
        r'\s*<meta\b(?=[^>]*\bname=["\']description["\'])[^>]*>',
        "",
        source,
        flags=re.I,
    )
    target_url = html.escape(target["canonical"], quote=True)
    description = html.escape(target["description"], quote=True)
    title = html.escape(record["title"], quote=True)
    block = "\n".join(
        [
            START,
            f'<meta name="description" content="{description}" />',
            f'<link rel="canonical" href="{target_url}" />',
            f'<link rel="alternate" hreflang="en" href="{target_url}" />',
            f'<link rel="alternate" hreflang="x-default" href="{target_url}" />',
            '<meta name="robots" content="noindex, follow" />',
            '<meta name="googlebot" content="noindex, follow" />',
            f'<meta property="og:title" content="{title}" />',
            f'<meta property="og:description" content="{description}" />',
            f'<meta property="og:url" content="{target_url}" />',
            '<meta property="og:type" content="article" />',
            f'<meta property="og:site_name" content="{html.escape(SITE_NAME, quote=True)}" />',
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{title}" />',
            f'<meta name="twitter:description" content="{description}" />',
            END,
        ]
    )
    source = re.sub(r"</head>", block + "\n</head>", source, count=1, flags=re.I)
    path.write_text(source, encoding="utf-8", newline="\n")


def inject_section_ids(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    used = set(re.findall(r'\bid=["\']([^"\']+)["\']', source, re.I))
    counters: dict[str, int] = {}

    def add_id(match: re.Match) -> str:
        opening, body = match.group(1), match.group(2)
        if re.search(r'\bid\s*=', opening, re.I):
            return match.group(0)
        base = section_slug(body)
        counters[base] = counters.get(base, 0) + 1
        candidate = base
        while candidate in used:
            counters[base] += 1
            candidate = f"{base}-{counters[base]}"
        used.add(candidate)
        opening = opening[:-1] + f' id="{candidate}" {SECTION_ID_MARKER}="true">'
        return opening + body

    # Match only the opening tag and its immediate text. This also handles a few
    # legacy pages whose heading closing tag is malformed, without rewriting it.
    source = re.sub(r'(<h[1-6]\b[^>]*>)([^<]*)', add_id, source, flags=re.I)
    path.write_text(source, encoding="utf-8", newline="\n")


def inject_semantic_structure(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    source = re.sub(
        re.escape(SEMANTIC_START) + r'\s*<main class="oof-semantic-main"><article class="oof-semantic-article">\s*',
        "",
        source,
        flags=re.I,
    )
    source = re.sub(r"</article></main>\s*" + re.escape(SEMANTIC_END) + r"\s*", "", source, flags=re.I)
    source = re.sub(
        re.escape(SEMANTIC_START) + r'\s*<article class=\\?"oof-semantic-article\\?">\s*',
        "",
        source,
        flags=re.I,
    )
    source = re.sub(r"</article>\s*" + re.escape(SEMANTIC_END) + r"\s*", "", source, flags=re.I)

    if re.search(r"<main\b", source, re.I):
            source = re.sub(
                r"(<main\b[^>]*>)",
                rf'\1\n{SEMANTIC_START}\n<article class="oof-semantic-article">',
                source,
                count=1,
                flags=re.I,
            )
            matches = list(re.finditer(r"</main>", source, re.I))
            if matches:
                position = matches[-1].start()
                source = source[:position] + f"</article>\n{SEMANTIC_END}\n" + source[position:]
    else:
            header = re.search(r'<div\s+id=["\']header["\'][^>]*>\s*</div>', source, re.I)
            if header:
                opening = f'\n{SEMANTIC_START}\n<main class="oof-semantic-main"><article class="oof-semantic-article">\n'
                source = source[: header.end()] + opening + source[header.end() :]
                boundaries = [
                    (re.search(r'<div\s+id=["\']footer["\'][^>]*>', source[header.end() :], re.I), True),
                    (re.search(r"<footer\b", source[header.end() :], re.I), True),
                    (re.search(r"</main>", source[header.end() :], re.I), False),
                    (re.search(r"<script\b[^>]*src=[\"'][^\"']*header\.js", source[header.end() :], re.I), True),
                ]
                positions = [(header.end() + match.start(), close_main) for match, close_main in boundaries if match]
                if positions:
                    position, close_main = min(positions, key=lambda item: item[0])
                    closing = "</article></main>" if close_main else "</article>"
                    source = source[:position] + f"{closing}\n{SEMANTIC_END}\n" + source[position:]

    heading_index = 0

    def add_heading_semantics(match: re.Match) -> str:
        nonlocal heading_index
        opening = match.group(0)
        if "aria-level" in opening.casefold():
            heading_index += 1
            return opening
        heading_index += 1
        level = 1 if heading_index == 1 else 2
        return opening[:-1] + f' role="heading" aria-level="{level}">'

    source = re.sub(r"<h[1-6]\b[^>]*>", add_heading_semantics, source, flags=re.I)
    path.write_text(source, encoding="utf-8", newline="\n")


def graph_record(record: dict) -> dict:
    item: dict = {
        "@type": record["schemaType"],
        "@id": record["canonical"] + "#webpage",
        "url": record["canonical"],
        "name": record["title"],
        "description": record["description"],
        "inLanguage": record["language"],
        "isPartOf": {"@id": BASE_URL + "#website"},
    }
    if record["schemaType"] == "TechArticle":
        item["headline"] = record["title"]
        item["author"] = {"@id": BASE_URL + "#organization"}
        item["mainEntityOfPage"] = {"@id": record["canonical"] + "#webpage"}
    topics = [
        record["fields"].get(field)
        for field in ("Architecture", "Architecture Family", "Parent Standard", "Category", "Subcategory", "Governed Space")
        if record["fields"].get(field)
    ]
    if topics:
        item["keywords"] = topics
        item["about"] = [{"@type": "Thing", "name": topic} for topic in topics]
    if record["links"]:
        item["relatedLink"] = record["links"]
    item["oofRelationships"] = record["relations"]
    if record["fields"].get("OriginID"):
        item["identifier"] = record["fields"]["OriginID"]
    if record["fields"].get("Version"):
        item["version"] = record["fields"]["Version"]
    if record["fields"].get("Status"):
        item["creativeWorkStatus"] = record["fields"]["Status"]
    if record["fields"]:
        item["additionalProperty"] = [
            {"@type": "PropertyValue", "name": key, "value": value}
            for key, value in record["fields"].items()
        ]
    return item


def write_knowledge_graph(records: list[dict]) -> None:
    graph = [
        {
            "@type": "Organization",
            "@id": BASE_URL + "#organization",
            "name": SITE_NAME,
            "url": BASE_URL,
            "logo": canonical_url("favicon.png"),
        },
        {
            "@type": "WebSite",
            "@id": BASE_URL + "#website",
            "name": SITE_NAME,
            "url": BASE_URL,
            "inLanguage": "en",
            "publisher": {"@id": BASE_URL + "#organization"},
            "hasPart": [{"@id": record["canonical"] + "#webpage"} for record in records],
        },
    ]
    graph.extend(graph_record(record) for record in records)
    output = {"@context": "https://schema.org", "@graph": graph}
    path = ROOT / "data" / "oof-site-knowledge-graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_typed_relationships(records: list[dict]) -> None:
    relationships = []
    for record in records:
        for relation in record["relations"]:
            relationships.append(
                {"source": record["canonical"], "type": relation["type"], "target": relation["target"]}
            )
    output = {
        "schemaVersion": "1.0",
        "baseUrl": BASE_URL,
        "relationshipTypes": [
            "parentResource",
            "standardsCompatibility",
            "moduleFlow",
            "crossArchitectureInterface",
            "relatedDocument",
            "relatedLink",
        ],
        "relationships": relationships,
    }
    path = ROOT / "data" / "oof-typed-relationships.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_sitemap(records: list[dict]) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for record in records:
        lines.extend(["  <url>", f'    <loc>{xml_escape(record["canonical"])}</loc>', "  </url>"])
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_robots() -> None:
    text = "\n".join(
        ["User-agent: OAI-SearchBot", "Allow: /", "", "User-agent: *", "Allow: /", "", f"Sitemap: {BASE_URL}sitemap.xml", ""]
    )
    (ROOT / "robots.txt").write_text(text, encoding="utf-8", newline="\n")


def write_llm_indexes(records: list[dict]) -> None:
    preferred = [
        "index.html",
        "oof-site-index.html",
        "oof-structured-architecture-index.html",
        "standardinde.html",
        "reference-architectures.html",
        "content/v/validos-architecture.html",
        "content/v/validos-complete-index.html",
    ]
    by_relative = {record["relative"]: record for record in records}
    lines = [
        f"# {SITE_NAME}",
        "",
        "> Canonical methodological reference website for OOF architectures, standards, modules, services, and governance resources.",
        "",
        "All canonical documents are in English. Follow each document's explicit hierarchy and governed links; do not infer compatibility from proximity or link volume.",
        "",
        "## Primary Navigation",
        "",
    ]
    for relative in preferred:
        if relative in by_relative:
            record = by_relative[relative]
            lines.append(f'- [{record["title"]}]({record["canonical"]})')
    lines.extend(
        [
            "",
            "## Machine-Readable Resources",
            "",
            f"- [XML Sitemap]({BASE_URL}sitemap.xml)",
            f"- [OOF Site Knowledge Graph]({BASE_URL}data/oof-site-knowledge-graph.json)",
            f"- [OOF Typed Relationship Graph]({BASE_URL}data/oof-typed-relationships.json)",
            f"- [OOF URL Registry]({BASE_URL}data/oof-url-registry.json)",
            f"- [OOF URL Alias Registry]({BASE_URL}data/oof-url-alias-registry.json)",
            f"- [OOF Version Registry]({BASE_URL}data/oof-version-registry.json)",
            f"- [OOF Governed Relationship Registry]({BASE_URL}data/oof-relationship-registry.json)",
            f"- [Site Search Index]({BASE_URL}search-index.json)",
            f"- [Complete Page Catalog]({BASE_URL}llms-full.txt)",
            "",
            "## Retrieval Guidance",
            "",
            "Use canonical URLs from the sitemap or knowledge graph. Treat Parent Resources, Standards Compatibility, Module Flow, and Cross-Architecture Interfaces as distinct governed relationship types.",
            "",
        ]
    )
    (ROOT / "llms.txt").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    full = [
        f"# {SITE_NAME} — Complete Page Catalog",
        "",
        f"> {len(records)} canonical HTML documents. Fetch the linked canonical page for its authoritative content and formatting.",
        "",
    ]
    current_group = None
    for record in records:
        parts = record["relative"].split("/")
        group = "Root Documents" if len(parts) == 1 else "/".join(parts[:-1])
        if group != current_group:
            if current_group is not None:
                full.append("")
            full.extend([f"## {group}", ""])
            current_group = group
        full.append(f'- [{record["title"]}]({record["canonical"]})')
    full.append("")
    (ROOT / "llms-full.txt").write_text("\n".join(full), encoding="utf-8", newline="\n")


def update_search_index(records: list[dict]) -> int:
    path = ROOT / "search-index.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    canonical_relatives = {record["relative"] for record in records}
    entries = [entry for entry in entries if entry.get("url") in canonical_relatives]
    existing = {entry.get("url") for entry in entries}
    added = 0
    for record in records:
        if record["relative"] in existing:
            continue
        entries.append({"title": record["title"], "url": record["relative"], "text": record["visibleText"]})
        existing.add(record["relative"])
        added += 1
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return added


def main() -> None:
    paths = public_pages()
    all_records = inspect_pages(paths)
    records = [record for record in all_records if alias_target(record["relative"]) is None]
    by_relative = {record["relative"]: record for record in records}
    for record in records:
        inject_metadata(record)
        inject_section_ids(record["path"])
        inject_semantic_structure(record["path"])
    for record in all_records:
        target_relative = alias_target(record["relative"])
        if target_relative:
            inject_alias_metadata(record, by_relative[target_relative])
    write_knowledge_graph(records)
    write_typed_relationships(records)
    write_sitemap(records)
    write_robots()
    write_llm_indexes(records)
    added = update_search_index(records)
    print(f"AI compatibility generated for {len(records)} pages; {added} missing search entries added.")


if __name__ == "__main__":
    main()
