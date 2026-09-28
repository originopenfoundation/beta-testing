#!/usr/bin/env python3
"""Build static VALIDOS links from one governed relationship registry."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "v"
REGISTRY_PATH = ROOT / "data" / "oof-relationship-registry.json"
START = "<!-- OOF GOVERNED LINKS START -->"
END = "<!-- OOF GOVERNED LINKS END -->"


class SearchTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()

STANDARD_CODES = ["vobs", "vpss", "vcrs", "vmts", "vefs", "vsrs", "vexs", "vdts", "vsgs", "vrrs"]
COMPATIBILITY = {
    "vobs": ["vpss", "vsgs", "vrrs"],
    "vpss": ["vobs", "vcrs", "vmts", "vrrs"],
    "vcrs": ["vpss", "vmts", "vexs", "vdts"],
    "vmts": ["vcrs", "vefs", "vexs"],
    "vefs": ["vmts", "vsrs", "vexs", "vdts"],
    "vsrs": ["vefs", "vexs", "vdts"],
    "vexs": ["vmts", "vefs", "vsrs", "vdts", "vsgs"],
    "vdts": ["vcrs", "vefs", "vexs", "vsgs", "vrrs"],
    "vsgs": ["vobs", "vexs", "vdts", "vrrs"],
    "vrrs": ["vpss", "vdts", "vsgs"],
}

ARCHITECTURE_RESOURCES = [
    {"title": "About VALIDOS® — Validation Governance Architecture", "url": "content/v/validos-about.html"},
    {"title": "VALIDOS® Architecture Map", "url": "content/v/validos-architecture-map.html"},
    {"title": "VALIDOS® Validation Governance Architecture — Validation Governance Layer", "url": "content/v/validos-architecture.html"},
    {"title": "VALIDOS® Complete Standards & Modules Index", "url": "content/v/validos-complete-index.html"},
    {"title": "VALIDOS® — Four-Layer Validation Protocol™", "url": "content/v/validos-four-layer-validation-protocol.html"},
]

CROSS_ARCHITECTURE = [
    {
        "target": "GOA™ — Governance Architecture",
        "url": "content/g/GOA™.html",
        "direction": "Bidirectional governance interface",
        "boundary": "GOA governs governance architecture and constitutional conditions; VALIDOS governs the lifecycle through which Validation Objects acquire, maintain, change, or lose governed validation status.",
    },
    {
        "target": "ORA™ — Operational Reality Architecture",
        "url": "content/o/ora-architecture.html",
        "direction": "Operational Reality to validation governance, with governed feedback",
        "boundary": "ORA governs what is occurring in Operational Reality; VALIDOS governs whether a defined Validation Object can support a validation determination under governed conditions.",
    },
    {
        "target": "OBIDENITY® — Origin-Bound Identity Governance Architecture",
        "url": "content/o/obidenity-architecture.html",
        "direction": "Identity and provenance into validation governance",
        "boundary": "OBIDENITY governs origin, identity, ownership, authority, permission, provenance, transfer, and continuity; VALIDOS governs their validation-specific use.",
    },
    {
        "target": "INTEGROS® — Integrity Governance Architecture",
        "url": "content/integros/INTEGROS® Integrity Governance Architecture - Integrity Governance Layer.html",
        "direction": "Integrity conditions into validation determination and reliance",
        "boundary": "INTEGROS governs integrity across objects, information, states, processes, and records; VALIDOS governs whether the complete validation basis supports determination, state, and bounded reliance.",
    },
    {
        "target": "ADIT® — Continuous Audit & Evidence Governance Architecture",
        "url": "content/adit/ADIT® Continuous Audit & Evidence Governance Architecture - Audit & Evidence Governance Layer.html",
        "direction": "Evidence governance into the validation lifecycle",
        "boundary": "ADIT governs evidential observation, preservation, verification, traceability, and auditability; VALIDOS governs evidence fitness and use within validation.",
    },
    {
        "target": "AGA™ — Accountability Governance Architecture",
        "url": "content/r/ref-aga-architecture-index.html",
        "direction": "Accountability governance around validation activity",
        "boundary": "AGA governs authority, responsibility, accountability, attribution, escalation, and decision relationships; VALIDOS governs validation methodology, execution, determination, state, reliance, and revalidation.",
    },
]


def title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<h2>(.*?)</h2>", text, flags=re.S | re.I)
    if not match:
        raise ValueError(f"Missing h2 title: {path}")
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def root_url(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def page_href(url: str) -> str:
    return "../../" + url


def links_section(heading: str, links: list[dict[str, str]], descriptions: bool = False) -> str:
    lines = [f'<section class="container governed-links">', f"<h1>{html.escape(heading)}</h1>", '<div class="oof-warning20">']
    for index, link in enumerate(links):
        lines.append(f'<a href="{html.escape(page_href(link["url"]), quote=True)}">&rarr; {html.escape(link["title"])}</a>')
        if descriptions and link.get("description"):
            lines.append(f'<br><span class="governed-link-context">{html.escape(link["description"])}</span>')
        if index < len(links) - 1:
            lines.append("<br><br>")
    lines.extend(["</div>", '<section class="viewbor"></section>', "</section>"])
    return "\n".join(lines)


def cross_architecture_section() -> str:
    lines = ['<section class="container governed-links">', "<h1>Cross-Architecture Interfaces</h1>", '<div class="oof-warning20">']
    for index, interface in enumerate(CROSS_ARCHITECTURE):
        lines.append(f'<a href="{html.escape(page_href(interface["url"]), quote=True)}"><b>&rarr; {html.escape(interface["target"])}</b></a><br>')
        lines.append(f'<span class="governed-link-context"><b>Direction:</b> {html.escape(interface["direction"])}<br>')
        lines.append(f'<b>Governed boundary:</b> {html.escape(interface["boundary"])}</span>')
        if index < len(CROSS_ARCHITECTURE) - 1:
            lines.append("<br><br>")
    lines.extend(["</div>", '<section class="viewbor"></section>', "</section>"])
    return "\n".join(lines)


def discover_registry() -> dict:
    standards = []
    for code in STANDARD_CODES:
        standard_path = CONTENT / f"validos-{code}.html"
        about_path = CONTENT / f"validos-{code}-about.html"
        module_paths = sorted(
            CONTENT.glob(f"validos-{code}-*.html"),
            key=lambda path: int(re.search(r"-(\d+)\.html$", path.name).group(1)) if re.search(r"-(\d+)\.html$", path.name) else 99,
        )
        module_paths = [path for path in module_paths if re.search(r"-\d+\.html$", path.name)]
        modules = [{"title": title(path), "url": root_url(path), "position": index + 1} for index, path in enumerate(module_paths)]
        standards.append(
            {
                "id": code.upper(),
                "title": title(standard_path),
                "url": root_url(standard_path),
                "about": {"title": title(about_path), "url": root_url(about_path)},
                "modules": modules,
                "compatibleStandards": [target.upper() for target in COMPATIBILITY[code]],
            }
        )
    return {
        "schemaVersion": "1.0",
        "methodology": "OOF® Governed Linking Methodology",
        "architecture": {
            "id": "VALIDOS",
            "title": "VALIDOS® — Validation Governance Architecture",
            "resources": ARCHITECTURE_RESOURCES,
            "standards": standards,
            "crossArchitectureInterfaces": CROSS_ARCHITECTURE,
        },
    }


def add_registry_discovery(text: str) -> str:
    discovery = '<link rel="alternate" type="application/json" href="../../data/oof-relationship-registry.json" title="OOF Governed Relationship Registry" />'
    if discovery not in text:
        text = text.replace("</head>", discovery + "\n</head>", 1)
    return text


def replace_generated_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\s*", flags=re.S)
    text = pattern.sub("", text)
    if not block:
        return text
    marker = '<section class="container">\n<h1>Related Documents</h1>'
    if marker not in text:
        marker = '<div id="footer"></div>'
    generated = START + "\n" + block + "\n" + END + "\n"
    return text.replace(marker, generated + marker, 1)


def render(registry: dict) -> None:
    architecture = registry["architecture"]
    standard_by_id = {item["id"]: item for item in architecture["standards"]}
    resource_by_url = {item["url"]: item for item in architecture["resources"]}

    for resource in architecture["resources"]:
        path = ROOT / resource["url"]
        text = add_registry_discovery(path.read_text(encoding="utf-8"))
        block = cross_architecture_section() if resource["url"].endswith(("validos-architecture.html", "validos-architecture-map.html")) else ""
        path.write_text(replace_generated_block(text, block), encoding="utf-8", newline="\n")

    for standard in architecture["standards"]:
        standard_path = ROOT / standard["url"]
        standard_text = add_registry_discovery(standard_path.read_text(encoding="utf-8"))
        parent_links = [
            resource_by_url["content/v/validos-architecture-map.html"],
            resource_by_url["content/v/validos-complete-index.html"],
            resource_by_url["content/v/validos-four-layer-validation-protocol.html"],
        ]
        compatible = [
            {
                "title": standard_by_id[target]["title"],
                "url": standard_by_id[target]["url"],
                "description": "Operational compatibility within the governed validation lifecycle.",
            }
            for target in standard["compatibleStandards"]
        ]
        standard_block = links_section("Parent Resources", parent_links) + "\n" + links_section("Standards Compatibility", compatible, descriptions=True)
        standard_path.write_text(replace_generated_block(standard_text, standard_block), encoding="utf-8", newline="\n")

        about_path = ROOT / standard["about"]["url"]
        about_text = add_registry_discovery(about_path.read_text(encoding="utf-8"))
        about_links = [resource_by_url["content/v/validos-architecture-map.html"], resource_by_url["content/v/validos-complete-index.html"]]
        about_path.write_text(replace_generated_block(about_text, links_section("Parent Resources", about_links)), encoding="utf-8", newline="\n")

        modules = standard["modules"]
        for index, module in enumerate(modules):
            module_path = ROOT / module["url"]
            module_text = add_registry_discovery(module_path.read_text(encoding="utf-8"))
            module_parent_links = [
                resource_by_url["content/v/validos-architecture.html"],
                resource_by_url["content/v/validos-architecture-map.html"],
                resource_by_url["content/v/validos-complete-index.html"],
            ]
            flow = []
            if index > 0:
                flow.append({"title": f'Previous module: {modules[index - 1]["title"]}', "url": modules[index - 1]["url"]})
            if index + 1 < len(modules):
                flow.append({"title": f'Next module: {modules[index + 1]["title"]}', "url": modules[index + 1]["url"]})
            module_block = links_section("Parent Resources", module_parent_links) + "\n" + links_section("Internal Module Flow", flow)
            module_path.write_text(replace_generated_block(module_text, module_block), encoding="utf-8", newline="\n")


def update_search_index() -> None:
    index_path = ROOT / "search-index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    by_url = {entry["url"]: entry for entry in entries}
    for path in sorted(CONTENT.glob("validos-*.html")):
        url = root_url(path)
        parser = SearchTextParser()
        parser.feed(path.read_text(encoding="utf-8"))
        entry = by_url.get(url)
        record = {"title": title(path), "url": url, "text": parser.text()}
        if entry is None:
            entries.append(record)
        else:
            entry.update(record)
    index_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    registry = discover_registry()
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    render(registry)
    update_search_index()
    print(f"Updated {sum(1 for _ in CONTENT.glob('validos-*.html'))} VALIDOS pages from {REGISTRY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
