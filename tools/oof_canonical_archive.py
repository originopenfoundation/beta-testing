#!/usr/bin/env python3
"""Create and compare read-only OOF canonical export packages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = ROOT / "exports" / "oof-canonical"
FORMAT_VERSION = "1.0"
PUBLIC_EXCLUDES = {"exports", ".git", ".tmp", "tmp", "pdf-pilot"}
REGISTRY_FILES = (
    "data/oof-version-registry.json",
    "data/oof-url-registry.json",
    "data/oof-url-alias-registry.json",
    "data/oof-relationship-registry.json",
    "data/oof-typed-relationships.json",
    "data/oof-architecture-registry.json",
    "content-migration-manifest.json",
    "os-index.json",
)
JSON_LD_RE = re.compile(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def source_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def public_html_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.html"):
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] in PUBLIC_EXCLUDES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix().casefold())


def json_ld(source: str) -> dict:
    for raw in JSON_LD_RE.findall(source):
        try:
            value = json.loads(html.unescape(raw))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("@type") not in {"BreadcrumbList", "ImageObject"}:
            return value
    return {}


def properties(metadata: dict) -> dict[str, str]:
    result = {}
    for item in metadata.get("additionalProperty", []) or []:
        if isinstance(item, dict) and item.get("name"):
            result[str(item["name"])] = str(item.get("value", ""))
    return result


def classify(relative: str, source: str) -> dict:
    metadata = json_ld(source)
    props = properties(metadata)
    title_match = TITLE_RE.search(source)
    title = html.unescape(TAG_RE.sub("", title_match.group(1))).strip() if title_match else relative
    object_type = props.get("Type", "Other Canonical Object")
    lower_title = title.casefold()
    if "core module" in object_type.casefold() or lower_title.endswith(" module"):
        category = "module"
    elif "parent standard" in object_type.casefold() or " standard" in lower_title:
        category = "standard"
    elif "architecture" in lower_title and any(
        phrase in lower_title for phrase in ("about ", "architecture map", "governance layer", "reference architecture")
    ):
        category = "architecture"
    else:
        category = "other"
    return {
        "objectId": relative,
        "path": relative,
        "title": title,
        "category": category,
        "type": object_type,
        "architecture": props.get("Architecture Family") or props.get("Parent Architecture"),
        "parentStandard": props.get("Parent Standard"),
        "version": metadata.get("version") or props.get("Version"),
        "canonicalUrl": metadata.get("url"),
    }


def inventory() -> list[dict]:
    objects = []
    for path in public_html_files():
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        item = classify(relative, raw.decode("utf-8", errors="replace"))
        item["sha256"] = sha256_bytes(raw)
        item["size"] = len(raw)
        objects.append(item)
    return objects


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_assets(package: Path, objects: list[dict]) -> None:
    for item in objects:
        source = ROOT / item["path"]
        target = package / "content" / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for relative in REGISTRY_FILES:
        source = ROOT / relative
        if source.exists():
            target = package / "registries" / relative.removeprefix("data/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def write_classification_indexes(package: Path, objects: list[dict]) -> None:
    for category, directory in (("architecture", "architectures"), ("standard", "standards"), ("module", "modules")):
        write_json(package / directory / "index.json", [item for item in objects if item["category"] == category])
    write_json(package / "taxonomy" / "index.json", {
        "categories": {
            category: sum(1 for item in objects if item["category"] == category)
            for category in ("architecture", "standard", "module", "other")
        }
    })


def package_checksums(package: Path) -> tuple[int, str]:
    rows = []
    for path in sorted(package.rglob("*"), key=lambda item: item.relative_to(package).as_posix().casefold()):
        if path.is_file() and path.name != "checksums.sha256":
            rows.append((sha256_file(path), path.relative_to(package).as_posix()))
    aggregate = sha256_bytes("".join(f"{digest}  {name}\n" for digest, name in rows).encode("utf-8"))
    (package / "checksums.sha256").write_text(
        "".join(f"{digest}  {name}\n" for digest, name in rows) + f"{aggregate}  MASTER_SNAPSHOT\n",
        encoding="utf-8",
    )
    return len(rows), aggregate


def unique_destination(base_name: str) -> Path:
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = EXPORT_ROOT / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while (EXPORT_ROOT / f"{base_name}_{suffix}").exists():
        suffix += 1
    return EXPORT_ROOT / f"{base_name}_{suffix}"


def create_package(objects: list[dict], package: Path, package_type: str, identity: str | None = None) -> Path:
    package.mkdir(parents=True, exist_ok=False)
    copy_assets(package, objects)
    write_json(package / "index.json", objects)
    write_classification_indexes(package, objects)
    counts = {category: sum(1 for item in objects if item["category"] == category) for category in ("architecture", "standard", "module", "other")}
    manifest = {
        "snapshotId": package.name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": source_commit(),
        "websiteVersion": None,
        "packageType": package_type,
        "architecture": identity,
        "architectureCount": counts["architecture"],
        "standardCount": counts["standard"],
        "moduleCount": counts["module"],
        "registryObjectCount": sum(1 for item in (package / "registries").rglob("*") if item.is_file()),
        "otherCanonicalObjectCount": counts["other"],
        "totalCanonicalObjects": len(objects),
        "exportFormatVersion": FORMAT_VERSION,
    }
    write_json(package / "manifest.json", manifest)
    _, aggregate = package_checksums(package)
    manifest["aggregateSha256"] = aggregate
    write_json(package / "manifest.json", manifest)
    package_checksums(package)
    return package


def master_export() -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return create_package(inventory(), unique_destination(f"OOF_CANONICAL_MASTER_{date}"), "master")


def architecture_export(acronym: str) -> Path:
    acronym = acronym.upper()
    all_objects = inventory()
    registry = json.loads((ROOT / "data" / "oof-architecture-registry.json").read_text(encoding="utf-8"))
    architecture = next((item for item in registry["architectures"] if item["acronym"] == acronym), None)
    if not architecture:
        raise SystemExit(f"Architecture {acronym} is not present in the approved Architecture Index registry.")
    standard_paths = {item["url"].split("#", 1)[0] for item in architecture["standards"]}
    standard_titles = {item["name"] for item in architecture["standards"]}
    selected = [
        item for item in all_objects
        if item["path"] in standard_paths
        or (item.get("architecture") or "").startswith(acronym)
        or item.get("parentStandard") in standard_titles
        or acronym in item["title"]
    ]
    if not selected:
        raise SystemExit(f"No canonical objects were associated with {acronym}.")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return create_package(selected, unique_destination(f"OOF_{acronym}_{date}_CANONICAL"), "architecture", acronym)


def verify(package: Path) -> bool:
    expected = {}
    for line in (package / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    errors = []
    for name, digest in expected.items():
        if name == "MASTER_SNAPSHOT":
            continue
        path = package / name
        if not path.exists() or sha256_file(path) != digest:
            errors.append(name)
    rows = sorted(
        ((digest, name) for name, digest in expected.items() if name != "MASTER_SNAPSHOT"),
        key=lambda item: item[1].casefold(),
    )
    aggregate = sha256_bytes("".join(f"{digest}  {name}\n" for digest, name in rows).encode("utf-8"))
    if aggregate != expected.get("MASTER_SNAPSHOT"):
        errors.append("MASTER_SNAPSHOT")
    if errors:
        print("Checksum verification failed:", ", ".join(errors), file=sys.stderr)
        return False
    print(f"Checksum verification passed: {len(rows)} files.")
    return True


def compare(reference: Path, current: Path) -> Path:
    old = {item["objectId"]: item for item in json.loads((reference / "index.json").read_text(encoding="utf-8"))}
    new = {item["objectId"]: item for item in json.loads((current / "index.json").read_text(encoding="utf-8"))}
    unchanged = sorted(key for key in old.keys() & new.keys() if old[key]["sha256"] == new[key]["sha256"])
    modified = sorted(key for key in old.keys() & new.keys() if old[key]["sha256"] != new[key]["sha256"])
    added = sorted(new.keys() - old.keys())
    missing = sorted(old.keys() - new.keys())
    report = {
        "referenceSnapshot": reference.name,
        "currentSnapshot": current.name,
        "objectsChecked": len(set(old) | set(new)),
        "unchanged": unchanged,
        "new": added,
        "modified": modified,
        "missing": missing,
        "status": "PASS" if not (modified or missing) else "REVIEW REQUIRED",
    }
    target = EXPORT_ROOT / f"comparison-{reference.name}-vs-{current.name}.json"
    write_json(target, report)
    markdown = target.with_suffix(".md")
    sections = []
    for label, values in (("NEW", added), ("MODIFIED", modified), ("MISSING", missing)):
        sections.append(f"## {label}\n" + ("\n".join(f"- `{item}`" for item in values) or "None"))
    markdown.write_text(
        "# OOF® Canonical Integrity Comparison\n\n"
        f"Reference Snapshot: `{reference.name}`\n\nCurrent Website: `{current.name}`\n\n"
        f"Objects checked: {report['objectsChecked']}\n\n"
        f"UNCHANGED: {len(unchanged)}  \nNEW: {len(added)}  \nMODIFIED: {len(modified)}  \nMISSING: {len(missing)}\n\n"
        f"INTEGRITY STATUS: **{report['status']}**\n\n" + "\n\n".join(sections) + "\n",
        encoding="utf-8",
    )
    return markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("master")
    architecture = sub.add_parser("architecture")
    architecture.add_argument("acronym")
    verification = sub.add_parser("verify")
    verification.add_argument("package", type=Path)
    comparison = sub.add_parser("compare")
    comparison.add_argument("reference", type=Path)
    comparison.add_argument("current", type=Path)
    args = parser.parse_args()
    if args.command == "master":
        target = master_export()
        print(target)
        return 0 if verify(target) else 1
    if args.command == "architecture":
        target = architecture_export(args.acronym)
        print(target)
        return 0 if verify(target) else 1
    if args.command == "verify":
        return 0 if verify(args.package.resolve()) else 1
    print(compare(args.reference.resolve(), args.current.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
