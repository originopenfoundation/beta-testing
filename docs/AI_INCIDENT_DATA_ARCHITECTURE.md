# OOF® Global AI Incident Intelligence™ Data Architecture

## Current Storage

The transitional canonical incident store is `data/ai-incidents/incident-store.json`. It contains one canonical record per incident. The public site never fetches this complete store; generated, bounded public projections live under `data/ai-incidents/public/`.

## Canonical Model and Identity

`data/ai-incidents/incident.schema.json` defines factual, geographic, entity, classification, evidence, provenance, architecture-relevance, and assessment fields. Stable public IDs use `OOF-AII-000000`. Source records remain attached through `sources[]` and are never treated as canonical incident identity.

## Data Access Boundary

The browser uses `IncidentRepository` in `assets/js/ai-incidents/repository.js`. It requests summary, map, and paginated projections only. UI components do not know whether these responses originate from static JSON, an API, or a future database.

The current Python `FileIncidentRepository` implements the write-side boundary. A future database adapter can replace it without changing incident identity, public projections, map behavior, or frontend components.

## Map and Page-Load Strategy

The map projection contains country aggregates and minimal marker fields only. Full evidence and governance analysis are excluded. Incident lists are paginated at 25 records. Large knowledge-base size therefore does not determine visitor payload size.

## Source Adapters

`SourceAdapter` isolates provider-specific retrieval and normalization. `ManualOOFIncidentAdapter` supports reviewed local submissions. `AIIDWeeklyExcelAdapter` discovers and imports the latest official weekly AI Incident Database Excel snapshot from its public snapshots page. The public projection is bounded to the newest 100 records plus all records that currently include a classified country; duplicate records are removed by stable source ID.

The AIID adapter preserves source provenance, links each record to its public AIID citation page, and labels imported records as source-catalogued and not assessed by OOF®. It does not infer severity or architecture relevance. Other external adapters must likewise use a stable, permitted API, dataset, export, feed, or structured endpoint and preserve provider terms and provenance. A fragile provider scrape must not become a platform dependency.

## Caching and Scaling

Static public projections inherit CDN caching. A future API should preserve the same bounded endpoints with ETags or last-modified validation, server-side filters, country/date queries, viewport queries, and aggregate caching.

## Git Boundary

Git currently contains application code, schema, configuration, documentation, and a transitional limited store. At operational scale, incident records, evidence objects, review history, source-sync history, and aggregates should move to external data infrastructure. Git must not remain the permanent production database.

## Migration Path

1. Implement a database-backed `IncidentRepository` with the existing schema and stable IDs.
2. Import canonical records while preserving IDs, timestamps, provenance, and public slugs.
3. Expose bounded API responses matching the current public projection contracts.
4. Point `IncidentRepository` in the browser to the API base URL.
5. Preserve URLs and historical assessment states; remove the transitional file store only after parity verification.

The storage layer may change. Identity, structure, relationships, and public behavior must not.
