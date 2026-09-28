# OOF® External Canonical Master Archive Export

This repository can create portable export packages. It has no connection, credentials, synchronization, or write path to the owner's independent external archive.

## Commands

```powershell
python tools/oof_canonical_archive.py master
python tools/oof_canonical_archive.py architecture ORA
python tools/oof_canonical_archive.py verify exports/oof-canonical/PACKAGE
python tools/oof_canonical_archive.py compare REFERENCE_PACKAGE CURRENT_PACKAGE
```

Packages are written only to `exports/oof-canonical/`, which is excluded from Git. The owner manually transfers packages to the external archive.

## Package Contents

- `manifest.json`: package identity, source commit, counts, format version, and aggregate hash.
- `index.json`: stable object IDs, classifications, canonical URLs, versions, and individual hashes.
- `content/`: byte-preserved public HTML sources in their original relative paths.
- `architectures/`, `standards/`, `modules/`, `taxonomy/`: indexes that reference preserved sources without duplicating content.
- `registries/`: existing structured registry files where available.
- `checksums.sha256`: file-level SHA-256 hashes plus the aggregate snapshot hash.

## Security Boundary

The utility is read-only with respect to canonical content. It does not upload, synchronize, restore, repair, or choose an authoritative version. Comparison reports are diagnostic and always require human review.
