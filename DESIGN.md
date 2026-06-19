# Abnormal File Vault — Design Document

**Author:** Vaishnavi Vaishnav  
**Date:** June 2026

## Problem Statement

Security teams routinely upload the same forensic artifacts, reports, and evidence files across multiple incidents. Storing every upload independently wastes disk space and slows retrieval at scale. Abnormal File Vault addresses this with **content-based deduplication** and **composable search/filtering**.

---

## Architecture

```
┌─────────────┐     POST /api/files/      ┌──────────────────┐
│   React UI  │ ─────────────────────────▶│   FileViewSet    │
│  (filters)  │◀─────────────────────────│   (Django DRF)   │
└─────────────┘     GET  /api/files/      └────────┬─────────┘
                                                     │
                    ┌────────────────────────────────┼────────────────────┐
                    ▼                                ▼                    ▼
              ┌──────────┐                    ┌─────────────┐      ┌──────────────┐
              │   File   │  FK (many-to-one)  │ StoredFile  │      │  Media disk  │
              │ (logical)│───────────────────▶│  (physical) │─────▶│  uploads/    │
              └──────────┘                    └─────────────┘      └──────────────┘
```

### Two-table deduplication model

| Table | Role |
|-------|------|
| `StoredFile` | One row per unique file content (SHA-256 hash). Holds the physical `FileField`, MIME type, size, and `ref_count`. |
| `File` | One row per user upload. Stores `original_filename`, `uploaded_at`, and a FK to `StoredFile`. |

**Why two tables?** A single-table design conflates "what the user named it" with "what bytes exist on disk." Separating them allows multiple uploads of the same content under different names while storing bytes once.

---

## Upload Flow

1. Stream-upload file and compute **SHA-256** hash (memory-safe chunked reads).
2. Look up `StoredFile` by `file_hash` (unique index).
3. **Duplicate:** increment `ref_count`, create logical `File` — no disk write.
4. **New:** reset file pointer, save to disk, create `StoredFile` + `File`.

---

## Delete Flow

1. Soft-delete logical `File` (`is_deleted=True`) — preserves audit trail option.
2. Atomically decrement `StoredFile.ref_count` via `F()` expression.
3. If `ref_count <= 0`, delete physical file and `StoredFile` row.

---

## Search & Filter API

`GET /api/files/` accepts combinable query parameters (AND logic):

| Parameter | Behavior |
|-----------|----------|
| `search` | Case-insensitive substring match on `original_filename` |
| `file_type` | Exact MIME type match |
| `size_min` / `size_max` | Byte range on `StoredFile.size` |
| `date_from` / `date_to` | Upload date range (`date_to` includes end of day) |
| `order` | `asc` or `desc` by `uploaded_at` |

### Index strategy

| Field | Index | Rationale |
|-------|-------|-----------|
| `StoredFile.file_hash` | Unique + db_index | O(1) dedup lookup |
| `StoredFile.file_type`, `size` | Composite indexes | Filter performance |
| `File.original_filename`, `uploaded_at`, `is_deleted` | Indexes | Search + default sort + soft-delete filter |

> **Note:** `icontains` on filename won't fully leverage B-tree indexes on SQLite. Acceptable for MVP; production would use PostgreSQL + `pg_trgm` or a search index.

---

## Storage Summary

`GET /api/files/summary/` returns:

- `total_logical_bytes` = Σ (`size` × `ref_count`)
- `total_actual_bytes` = Σ (`size`)
- `savings_bytes` = logical − actual

Computed via SQL `Sum(F('size') * F('ref_count'))` — no Python iteration.

---

## Key Design Decisions

| Decision | Choice | Alternative considered |
|----------|--------|----------------------|
| Hash algorithm | SHA-256 | MD5 (faster but weaker), xxHash (not cryptographic) |
| Dedup granularity | Content hash only | Name + size (misses renamed duplicates) |
| Delete strategy | Soft-delete + ref counting | Hard delete immediately |
| Filter UX | Apply on button click | Live/debounced search (more API calls) |
| DB | SQLite | PostgreSQL (better for prod scale) |

---

## Known Limitations & Future Work

- **No pagination** — list endpoint returns all matches; add cursor pagination for large datasets.
- **No concurrent upload locking** — `file_hash` unique constraint prevents duplicate `StoredFile` rows; race on ref_count is mitigated by `transaction.atomic`.
- **No virus scanning** — natural extension for a security product (hook in `create()`).
- **No object storage** — files on local disk; production would use S3/GCS with `StoredFile.file` as a key.
- **No user/auth** — single-tenant MVP; add per-user namespaces in production.

---

## Testing

```bash
cd backend && source venv/bin/activate
python manage.py test files.tests
```

Covers deduplication, ref-count delete semantics, search/filter combinations, and storage summary accuracy.
