#!/usr/bin/env python3
"""OOF Global AI Incident Intelligence data-domain utilities.

The current adapter is intentionally local and review-oriented. External source
adapters can implement SourceAdapter without changing the canonical record or UI.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "ai-incidents"
PUBLIC_ROOT = DATA_ROOT / "public"
STORE_PATH = DATA_ROOT / "incident-store.json"
INBOX_PATH = DATA_ROOT / "manual-inbox.json"
SYNC_STATE_PATH = DATA_ROOT / "sync-state.json"
ARCHITECTURE_REGISTRY = ROOT / "data" / "oof-architecture-registry.json"
COUNTRY_GEOJSON = ROOT / "assets" / "data" / "ne_50m_admin_0_countries.geojson"
AIID_SNAPSHOTS_URL = "https://incidentdatabase.ai/research/snapshots"
AIID_INCIDENT_URL = "https://incidentdatabase.ai/cite/{incident_id}"
ALLOWED_EVENT_TYPES = {"Incident", "Hazard", "Near Miss", "Emerging Risk"}
ALLOWED_EVIDENCE = {"Verified", "High Confidence", "Moderate Confidence", "Unverified"}
ALLOWED_SEVERITY = {"Low", "Moderate", "High", "Critical", "Unclassified"}

COUNTRY_ALIASES = {
    "u s": "US", "u s a": "US", "united states": "US", "united states of america": "US",
    "american": "US", "britain": "GB", "great britain": "GB", "united kingdom": "GB",
    "british": "GB", "russian": "RU", "chinese": "CN", "canadian": "CA", "australian": "AU",
    "indian": "IN", "japanese": "JP", "south korean": "KR", "north korean": "KP",
    "german": "DE", "french": "FR", "italian": "IT", "spanish": "ES", "brazilian": "BR",
    "mexican": "MX", "ukrainian": "UA", "israeli": "IL", "iranian": "IR", "turkish": "TR",
    "south african": "ZA", "new zealand": "NZ", "dutch": "NL", "swiss": "CH",
}
AMBIGUOUS_COUNTRY_NAMES = {"georgia"}
US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington state", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
}
ARCHITECTURE_RULES = {
    "validos": ("validation", "verify", "verification", "hallucination", "hallucinated", "misidentified", "misidentification", "misread", "incorrect", "inaccurate", "false citation", "fabricated citation", "error"),
    "cla": ("classification", "classify", "classified", "screening", "recognition", "detection", "labeling", "ranking", "eligibility", "admission", "license plate reader"),
    "obidenity": ("identity", "biometric", "facial", "impersonation", "impersonated", "deepfake", "cloned voice", "voice cloning", "identity theft"),
    "asga": ("autonomous", "self driving", "self-driving", "autopilot", "robot", "drone", "agentic", "ai agent", "automated driving"),
    "integros": ("cyber", "security", "hack", "malware", "phishing", "vulnerability", "data breach", "compromised", "ransomware"),
    "aga": ("accountability", "responsibility", "oversight", "audit", "regulator", "governance failure"),
    "mgia": ("memory", "memorized", "retention", "training data", "data provenance"),
    "clia": ("intelligence", "cognitive", "decision support", "predictive", "reasoning", "chatbot", "large language model", "llm"),
    "simulos": ("simulation", "simulated", "digital twin", "synthetic environment"),
    "vfm": ("pricing", "credit", "loan", "insurance", "financial value", "valuation"),
    "trega": ("tax", "taxation", "taxable", "revenue service"),
    "ora": ("operational reality", "sensor", "perception", "physical environment", "location data"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value or "incident"


def normalized_text(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def country_aliases() -> dict[str, str]:
    aliases = dict(COUNTRY_ALIASES)
    for code, name in _country_names().items():
        normalized_name = normalized_text(name)
        if normalized_name not in AMBIGUOUS_COUNTRY_NAMES:
            aliases[normalized_name] = code
    for state in US_STATE_NAMES:
        aliases[state] = "US"
    return aliases


def infer_country(record: dict) -> tuple[str, str | None]:
    existing_code = _normalize_country_code(record.get("countryCode"))
    names = _country_names()
    if existing_code:
        return names.get(existing_code, record.get("country") or existing_code), existing_code

    aliases = sorted(country_aliases().items(), key=lambda item: len(item[0]), reverse=True)
    weighted_fields = (
        (record.get("title"), 4),
        (record.get("organization"), 3),
        (record.get("region"), 3),
        (record.get("summary"), 1),
        (" ".join(record.get("affectedParties") or []), 1),
    )
    scores: Counter[str] = Counter()
    for value, weight in weighted_fields:
        text = normalized_text(value)
        if not text:
            continue
        occupied: list[tuple[int, int]] = []
        for alias, code in aliases:
            if not alias:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
            for match in pattern.finditer(text):
                span = match.span()
                if any(span[0] < end and span[1] > start for start, end in occupied):
                    continue
                scores[code] += weight
                occupied.append(span)
    if not scores:
        return "Location not specified", None
    ranked = scores.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "Multiple countries", None
    code = ranked[0][0]
    return names.get(code, code), code


def classify_architecture(record: dict) -> dict:
    registry = read_json(ARCHITECTURE_REGISTRY, {"architectures": []})
    approved = {item["id"]: item for item in registry["architectures"]}
    text = normalized_text(" ".join(str(record.get(key) or "") for key in (
        "title", "summary", "organization", "system", "technology", "industry", "aiSystemType"
    )))
    scores: Counter[str] = Counter()
    matches: dict[str, list[str]] = defaultdict(list)
    padded_text = f" {text} "
    for architecture_id, keywords in ARCHITECTURE_RULES.items():
        if architecture_id not in approved:
            continue
        for keyword in keywords:
            normalized_keyword = normalized_text(keyword)
            if normalized_keyword and f" {normalized_keyword} " in padded_text:
                scores[architecture_id] += 1
                matches[architecture_id].append(keyword)

    if scores:
        ranked = sorted(scores, key=lambda architecture_id: (-scores[architecture_id], architecture_id))
        primary = ranked[0]
        secondary = ranked[1:3]
        if primary != "aig" and "aig" in approved and "aig" not in secondary:
            secondary = (secondary + ["aig"])[:3]
        signals = ", ".join(matches[primary][:4])
        confidence = min(0.92, 0.62 + 0.06 * scores[primary])
        rationale = f"Automated mapping matched incident descriptors to {approved[primary]['displayName']} using signals: {signals}. Human review remains available."
    else:
        primary = "aig" if "aig" in approved else next(iter(approved), None)
        secondary = []
        confidence = 0.55
        rationale = "Automated mapping assigned the general AI governance architecture because no more specific approved architecture signal was sufficiently explicit. Human review remains available."

    if not primary:
        return {
            "status": "NO_ARCHITECTURE_IDENTIFIED", "classification": "Automated",
            "primaryArchitectureId": None, "secondaryArchitectureIds": [],
            "architectureIndexState": None, "classifiedAt": record.get("updatedAt") or now_iso(),
            "confidence": 0.0, "rationale": "No approved architecture was available in the Architecture Index.",
        }
    return {
        "status": "ARCHITECTURE_IDENTIFIED",
        "classification": "Automated",
        "primaryArchitectureId": primary,
        "secondaryArchitectureIds": secondary,
        "architectureIndexState": approved[primary].get("acronymLabel") or approved[primary].get("acronym"),
        "classifiedAt": record.get("updatedAt") or now_iso(),
        "confidence": round(confidence, 2),
        "rationale": rationale,
    }


def enrich_incident(record: dict) -> dict:
    enriched = dict(record)
    country, country_code = infer_country(enriched)
    enriched["country"] = country
    enriched["countryCode"] = country_code
    architecture = enriched.get("architectureRelevance") or {}
    if architecture.get("classification") != "Human Approved":
        enriched["architectureRelevance"] = classify_architecture(enriched)
    return enriched


def stable_incident_id(source_id: str) -> str:
    number = int(hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12], 16) % 1_000_000
    return f"OOF-AII-{number:06d}"


def dedup_key(record: dict) -> str:
    values = [
        str(record.get("occurredAt") or record.get("reportedAt") or "")[:10],
        str(record.get("countryCode") or "").upper(),
        str(record.get("organization") or "").casefold(),
        str(record.get("system") or "").casefold(),
        re.sub(r"\W+", " ", str(record.get("title") or "").casefold()).strip(),
    ]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def validate_incident(record: dict) -> None:
    required = ("id", "slug", "title", "eventType", "evidenceConfidence", "publicationStatus", "sources", "createdAt", "updatedAt")
    missing = [key for key in required if not record.get(key)]
    if missing:
        raise ValueError(f"Incident is missing required fields: {', '.join(missing)}")
    if not re.fullmatch(r"OOF-AII-\d{6}", record["id"]):
        raise ValueError("Incident ID does not match the stable OOF-AII identifier format")
    if record["eventType"] not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {record['eventType']}")
    if record["evidenceConfidence"] not in ALLOWED_EVIDENCE:
        raise ValueError(f"Unsupported evidence confidence: {record['evidenceConfidence']}")
    if record.get("severity", "Unclassified") not in ALLOWED_SEVERITY:
        raise ValueError(f"Unsupported severity: {record['severity']}")
    if not record["sources"]:
        raise ValueError("At least one source with provenance is required")


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch_new_records(self, since: str | None) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, record: dict) -> dict:
        raise NotImplementedError

    def metadata(self) -> dict:
        return {"name": self.name, "mode": "incremental"}


class ManualOOFIncidentAdapter(SourceAdapter):
    name = "ManualOOFIncidentAdapter"

    def fetch_new_records(self, since: str | None) -> list[dict]:
        del since
        return read_json(INBOX_PATH, [])

    def normalize(self, record: dict) -> dict:
        source = record.get("source") or {}
        source_id = str(source.get("sourceId") or source.get("url") or record.get("title") or "")
        created = record.get("createdAt") or now_iso()
        incident_id = record.get("id") or stable_incident_id(source_id)
        normalized = {
            "id": incident_id,
            "slug": record.get("slug") or f"{incident_id.casefold()}-{slugify(record.get('title', 'incident'))}",
            "title": record.get("title"),
            "summary": record.get("summary", ""),
            "eventType": record.get("eventType", "Incident"),
            "occurredAt": record.get("occurredAt"),
            "reportedAt": record.get("reportedAt"),
            "country": record.get("country"),
            "countryCode": record.get("countryCode"),
            "region": record.get("region"),
            "coordinates": record.get("coordinates"),
            "organization": record.get("organization"),
            "system": record.get("system"),
            "technology": record.get("technology"),
            "industry": record.get("industry"),
            "aiSystemType": record.get("aiSystemType"),
            "severity": record.get("severity", "Unclassified"),
            "impactTypes": record.get("impactTypes", []),
            "affectedParties": record.get("affectedParties", []),
            "evidenceConfidence": record.get("evidenceConfidence", "Unverified"),
            "verificationState": record.get("verificationState", "Pending Review"),
            "publicationStatus": record.get("publicationStatus", "Pending Review"),
            "sources": record.get("sources") or [{
                "sourceId": source_id,
                "publisher": source.get("publisher", "Unknown"),
                "publicationDate": source.get("publicationDate"),
                "sourceType": source.get("sourceType"),
                "url": source.get("url"),
                "retrievedAt": source.get("retrievedAt") or now_iso(),
                "verificationStatus": source.get("verificationStatus", "Pending Review"),
            }],
            "architectureRelevance": record.get("architectureRelevance") or {
                "status": "NOT_ASSESSED",
                "classification": "Not Assessed",
                "primaryArchitectureId": None,
                "secondaryArchitectureIds": [],
                "architectureIndexState": None,
                "classifiedAt": None,
                "confidence": None,
                "rationale": None,
            },
            "assessment": record.get("assessment"),
            "createdAt": created,
            "updatedAt": record.get("updatedAt") or created,
        }
        validate_incident(normalized)
        return normalized


class AIIDWeeklyExcelAdapter(SourceAdapter):
    """Read a bounded public projection from the official weekly AIID export."""

    name = "AIIDWeeklyExcelAdapter"

    def __init__(self, workbook_bytes: bytes | None = None, snapshot_url: str | None = None):
        self.workbook_bytes = workbook_bytes
        self.snapshot_url = snapshot_url

    @staticmethod
    def _request(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "OOF-Incident-Sync/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def _latest_snapshot_url(self) -> str:
        if self.snapshot_url:
            return self.snapshot_url
        html = self._request(AIID_SNAPSHOTS_URL).decode("utf-8", errors="replace")
        matches = re.findall(r'https://[^"\']+/AIID_Excel_Export-(\d{8})\.xlsx', html)
        if not matches:
            raise ValueError("No AIID weekly Excel snapshot was found")
        snapshot_date = max(matches)
        match = re.search(rf'https://[^"\']+/AIID_Excel_Export-{snapshot_date}\.xlsx', html)
        if not match:
            raise ValueError("The latest AIID weekly Excel snapshot URL is invalid")
        self.snapshot_url = match.group(0)
        return self.snapshot_url

    def fetch_new_records(self, since: str | None) -> list[dict]:
        del since
        snapshot_url = self._latest_snapshot_url()
        workbook_bytes = self.workbook_bytes or self._request(snapshot_url)
        workbook = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
        sheet = workbook["Incidents"]
        headers = [str(value or "").strip() for value in next(sheet.iter_rows(min_row=3, max_row=3, values_only=True))]
        rows = [dict(zip(headers, values)) for values in sheet.iter_rows(min_row=4, values_only=True)]
        rows = [row for row in rows if row.get("Incident ID") and row.get("title")]

        # Keep the browser payload bounded while retaining recent activity and
        # every currently classified country needed by the public map.
        newest = sorted(rows, key=lambda row: int(row["Incident ID"]), reverse=True)[:100]
        located = [row for row in rows if str(row.get("Country Code") or "").strip()]
        selected = {int(row["Incident ID"]): row for row in newest + located}
        return [{**row, "_snapshotUrl": snapshot_url} for row in selected.values()]

    def normalize(self, record: dict) -> dict:
        incident_number = int(record["Incident ID"])
        source_id = f"aiid:{incident_number}"
        incident_id = stable_incident_id(source_id)
        occurred = record.get("date")
        modified = record.get("Date Modified")
        occurred_at = occurred.date().isoformat() if hasattr(occurred, "date") else str(occurred or "")[:10] or None
        updated_at = modified.isoformat() + "Z" if hasattr(modified, "isoformat") else occurred_at + "T00:00:00Z" if occurred_at else now_iso()
        country_code = _normalize_country_code(record.get("Country Code"))
        country_names = _country_names()
        source_url = AIID_INCIDENT_URL.format(incident_id=incident_number)
        snapshot_match = re.search(r"AIID_Excel_Export-(\d{4})(\d{2})(\d{2})", str(record.get("_snapshotUrl") or ""))
        retrieved_at = "-".join(snapshot_match.groups()) + "T00:00:00Z" if snapshot_match else now_iso()
        description = str(record.get("description") or "").strip()
        risk_domain = str(record.get("Risk Domain") or "").strip()
        harm_domain = str(record.get("Harm Domain") or "").strip()
        impact_types = [value for value in (risk_domain, harm_domain) if value and value.casefold() != "none"]
        normalized = {
            "id": incident_id,
            "slug": f"{incident_id.casefold()}-{slugify(str(record['title']))}",
            "title": str(record["title"]).strip(),
            "summary": description,
            "eventType": "Incident",
            "occurredAt": occurred_at,
            "reportedAt": updated_at,
            "country": country_names.get(country_code, country_code),
            "countryCode": country_code,
            "region": str(record.get("Location Region") or "").strip() or None,
            "coordinates": None,
            "organization": str(record.get("deployer") or "").strip() or None,
            "system": str(record.get("Implicated Systems") or record.get("AI System") or "").strip() or None,
            "technology": str(record.get("AI Technology") or "").strip() or None,
            "industry": str(record.get("Sector of Deployment") or "").strip() or None,
            "aiSystemType": str(record.get("AI Task") or "").strip() or None,
            "severity": "Unclassified",
            "impactTypes": impact_types,
            "affectedParties": [part.strip() for part in str(record.get("harmed") or "").split(",") if part.strip()],
            "evidenceConfidence": "Moderate Confidence",
            "verificationState": "Source Catalogued / OOF Not Assessed",
            "publicationStatus": "Monitored",
            "sources": [{
                "sourceId": source_id,
                "publisher": "AI Incident Database (Responsible AI Collaborative)",
                "publicationDate": occurred_at,
                "sourceType": "Official weekly data export",
                "url": source_url,
                "datasetUrl": record.get("_snapshotUrl"),
                "retrievedAt": retrieved_at,
                "verificationStatus": "Source Catalogued / OOF Not Assessed",
            }],
            "architectureRelevance": {
                "status": "NOT_ASSESSED",
                "classification": "Not Assessed",
                "primaryArchitectureId": None,
                "secondaryArchitectureIds": [],
                "architectureIndexState": None,
                "classifiedAt": None,
                "confidence": None,
                "rationale": None,
            },
            "assessment": None,
            "createdAt": updated_at,
            "updatedAt": updated_at,
        }
        validate_incident(normalized)
        return normalized

    def metadata(self) -> dict:
        return {"name": self.name, "mode": "weekly-snapshot", "snapshotUrl": self.snapshot_url}


def _country_names() -> dict[str, str]:
    if not COUNTRY_GEOJSON.exists():
        return {}
    features = read_json(COUNTRY_GEOJSON, {"features": []}).get("features", [])
    result = {}
    for feature in features:
        properties = feature.get("properties") or {}
        primary_code = properties.get("ISO_A2") or properties.get("iso_a2")
        code = primary_code
        if code == "-99":
            code = properties.get("ISO_A2_EH") or properties.get("iso_a2_eh")
        name = properties.get("NAME_EN") or properties.get("NAME")
        if code and name and code != "-99":
            normalized_code = str(code).upper()
            if primary_code == "-99":
                result.setdefault(normalized_code, str(name))
            else:
                result[normalized_code] = str(name)
    return result


def _normalize_country_code(value) -> str | None:
    code = str(value or "").strip().upper()
    if not code:
        return None
    aliases = {
        "UNITED STATES": "US",
        "UNITED STATES OF AMERICA": "US",
        "UNITED KINGDOM": "GB",
    }
    return aliases.get(code, code if len(code) == 2 else None)


class IncidentRepository(ABC):
    @abstractmethod
    def list(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def upsert_sources(self, records: Iterable[dict]) -> tuple[int, int]:
        raise NotImplementedError


class FileIncidentRepository(IncidentRepository):
    """Transitional adapter. Replace this class when a database is introduced."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path

    def list(self) -> list[dict]:
        return read_json(self.path, {"incidents": []})["incidents"]

    def upsert_sources(self, records: Iterable[dict]) -> tuple[int, int]:
        existing = self.list()
        by_id = {item["id"]: item for item in existing}
        by_dedup = {dedup_key(item): item["id"] for item in existing}
        created = updated = 0
        for record in records:
            validate_incident(record)
            duplicate_id = by_dedup.get(dedup_key(record))
            record_id = duplicate_id or record["id"]
            if record_id in by_id:
                current = by_id[record_id]
                known_sources = {item["sourceId"] for item in current["sources"]}
                new_sources = [item for item in record["sources"] if item["sourceId"] not in known_sources]
                if new_sources:
                    current["sources"].extend(new_sources)
                    current["updatedAt"] = now_iso()
                    updated += 1
                elif record_id == record["id"]:
                    candidate = {**record, "createdAt": current.get("createdAt") or record["createdAt"]}
                    if (current.get("architectureRelevance") or {}).get("status") != "NOT_ASSESSED":
                        candidate["architectureRelevance"] = current["architectureRelevance"]
                        candidate["assessment"] = current.get("assessment")
                        candidate["publicationStatus"] = current.get("publicationStatus", candidate["publicationStatus"])
                    if candidate != current:
                        by_id[record_id] = candidate
                        updated += 1
            else:
                by_id[record_id] = record
                by_dedup[dedup_key(record)] = record_id
                created += 1
        incidents = sorted(by_id.values(), key=lambda item: item.get("reportedAt") or item["createdAt"], reverse=True)
        write_json(self.path, {"schemaVersion": "1.0", "incidents": incidents})
        return created, updated


def architecture_ids() -> set[str]:
    registry = read_json(ARCHITECTURE_REGISTRY, {"architectures": []})
    return {item["id"] for item in registry["architectures"]}


def public_records(records: list[dict]) -> list[dict]:
    allowed = architecture_ids()
    result = []
    for record in records:
        if record["publicationStatus"] not in {"Monitored", "Published"}:
            continue
        architecture = record.get("architectureRelevance") or {}
        primary = architecture.get("primaryArchitectureId")
        if primary and primary not in allowed:
            architecture = dict(architecture)
            architecture.update({
                "status": "ARCHITECTURE_REVIEW_REQUIRED",
                "primaryArchitectureId": None,
                "classification": "Automated",
                "rationale": "The referenced architecture is not present in the current approved Architecture Index.",
            })
            record = dict(record)
            record["architectureRelevance"] = architecture
        result.append(record)
    return result


def export_public(records: list[dict]) -> None:
    records = public_records(records)
    generated = now_iso()
    countries = defaultdict(lambda: {"incidentCount": 0, "criticalIncidents": 0, "coverage": Counter()})
    architectures = set()
    for record in records:
        country_code = record.get("countryCode")
        if country_code:
            countries[country_code]["incidentCount"] += 1
            if record.get("severity") == "Critical":
                countries[country_code]["criticalIncidents"] += 1
            countries[country_code]["coverage"][record.get("architectureRelevance", {}).get("status", "NOT_ASSESSED")] += 1
        primary = record.get("architectureRelevance", {}).get("primaryArchitectureId")
        if primary:
            architectures.add(primary)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    coverage = Counter(item.get("architectureRelevance", {}).get("status", "NOT_ASSESSED") for item in records)
    summary = {
        "generatedAt": generated,
        "datasetScope": "Public AI incident records catalogued from identified external sources for OOF® monitoring; architecture relevance is not assessed automatically.",
        "totalIncidents": len(records),
        "incidentsThisMonth": sum(1 for item in records if str(item.get("reportedAt") or "").startswith(month)),
        "criticalIncidents": sum(1 for item in records if item.get("severity") == "Critical"),
        "countriesAffected": len(countries),
        "architecturesExposed": len(architectures),
        "potentialGovernanceGaps": sum(1 for item in records if (item.get("assessment") or {}).get("coverage") == "POTENTIAL_GOVERNANCE_GAP"),
        "crossArchitectureIncidents": sum(1 for item in records if item.get("architectureRelevance", {}).get("secondaryArchitectureIds")),
        "stressTestsCompleted": sum(1 for item in records if (item.get("assessment") or {}).get("status") == "Approved"),
        "coverage": {
            "identified": coverage["ARCHITECTURE_IDENTIFIED"],
            "reviewRequired": coverage["ARCHITECTURE_REVIEW_REQUIRED"],
            "notIdentified": coverage["NO_ARCHITECTURE_IDENTIFIED"],
            "notAssessed": coverage["NOT_ASSESSED"],
        },
    }
    map_data = {
        "generatedAt": generated,
        "countries": [
            {"countryCode": code, "incidentCount": data["incidentCount"], "criticalIncidents": data["criticalIncidents"], "coverage": dict(data["coverage"])}
            for code, data in sorted(countries.items())
        ],
        "incidents": [
            {
                "id": item["id"], "slug": item["slug"], "title": item["title"],
                "countryCode": item.get("countryCode"), "coordinates": item.get("coordinates"),
                "severity": item.get("severity"), "eventType": item.get("eventType"),
                "architectureRelevance": item.get("architectureRelevance"),
            }
            for item in records if item.get("coordinates")
        ],
    }
    write_json(PUBLIC_ROOT / "summary.json", summary)
    write_json(PUBLIC_ROOT / "map.json", map_data)
    page_size = 25
    pages = max(1, (len(records) + page_size - 1) // page_size)
    for page in range(1, pages + 1):
        start = (page - 1) * page_size
        write_json(PUBLIC_ROOT / f"incidents-page-{page}.json", {
            "page": page, "pageSize": page_size, "total": len(records), "items": records[start:start + page_size]
        })


def sync() -> dict:
    repository = FileIncidentRepository()
    state = read_json(SYNC_STATE_PATH, {"sources": {}, "lastDailySummary": None})
    adapters = [ManualOOFIncidentAdapter(), AIIDWeeklyExcelAdapter()]
    totals = {"recordsRetrieved": 0, "recordsCreated": 0, "recordsUpdated": 0, "duplicatesDetected": 0, "sourceErrors": []}
    for adapter in adapters:
        attempted = now_iso()
        source_state = state["sources"].get(adapter.name, {})
        try:
            raw = adapter.fetch_new_records(source_state.get("lastSuccessfulSync"))
            normalized = [enrich_incident(adapter.normalize(item)) for item in raw]
            before = len(repository.list())
            created, updated = repository.upsert_sources(normalized)
            totals["recordsRetrieved"] += len(raw)
            totals["recordsCreated"] += created
            totals["recordsUpdated"] += updated
            totals["duplicatesDetected"] += max(0, len(raw) - created - updated)
            state["sources"][adapter.name] = {
                "lastAttemptedSync": attempted, "lastSuccessfulSync": now_iso(),
                "recordsRetrieved": len(raw), "recordsCreated": created, "recordsUpdated": updated,
                "duplicatesDetected": max(0, len(raw) - created - updated), "syncStatus": "success", "sourceErrors": [],
                **adapter.metadata(),
            }
            assert len(repository.list()) >= before
        except Exception as error:  # keep source failures isolated
            totals["sourceErrors"].append({"source": adapter.name, "error": str(error)})
            state["sources"][adapter.name] = {
                **source_state, "lastAttemptedSync": attempted, "syncStatus": "failed", "sourceErrors": [str(error)]
            }
    export_public(repository.list())
    state["lastDailySummary"] = {"createdAt": now_iso(), **totals}
    write_json(SYNC_STATE_PATH, state)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sync", "validate", "export"))
    args = parser.parse_args()
    repository = FileIncidentRepository()
    if args.command == "sync":
        print(json.dumps(sync(), indent=2))
    elif args.command == "export":
        export_public(repository.list())
        print(f"Exported {len(public_records(repository.list()))} public incidents.")
    else:
        for incident in repository.list():
            validate_incident(incident)
        print(f"Validated {len(repository.list())} canonical incident records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
