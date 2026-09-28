#!/usr/bin/env python3
"""Generate indexable static entry routes for the incident intelligence UI."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ai-incidents" / "index.html"
ROUTES = {
    "map": "Global AI Incident Map",
    "latest": "Latest AI Incidents",
    "critical": "Critical AI Incidents",
    "architectures": "AI Incident Architecture Intelligence",
    "industries": "AI Incidents by Industry",
    "countries": "AI Incidents by Country",
    "trends": "AI Incident Trends",
    "stress-tests": "OOF® Architecture Stress Tests",
    "methodology": "OOF® AI Incident Intelligence Methodology",
}


def build() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    for route, title in ROUTES.items():
        page = re.sub(r'<html lang="en" data-ai-incidents-view="[^"]+">', f'<html lang="en" data-ai-incidents-view="{route}">', source, count=1)
        page = re.sub(r"<title>.*?</title>", f"<title>{title} | OOF®</title>", page, count=1)
        page = re.sub(
            r'<link rel="canonical" href="[^"]+" />',
            f'<link rel="canonical" href="https://originopenfoundation.org/ai-incidents/{route}/" />',
            page,
            count=1,
        )
        target = ROOT / "ai-incidents" / route / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
    print(f"Generated {len(ROUTES)} AI incident routes.")


if __name__ == "__main__":
    build()
