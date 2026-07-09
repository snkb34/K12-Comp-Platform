# Sprint 1 Database Foundation

## Purpose

Sprint 1 expands the application from a scraper-style database into a compensation intelligence database.

The current app already works with:

- `sources`
- `runs`
- `documents`
- `comp_rows`

Sprint 1 keeps those tables and adds support for:

- source metadata
- data quality tracking
- normalized position compensation
- normalized licensed salary schedule cells
- market snapshots
- job title aliases

## Key Design Principle

Do not delete or replace the working extraction pipeline.

Instead:

1. Continue landing extracted data in `comp_rows`.
2. Add normalized tables for analytics.
3. Add Source Manager fields to `sources`.
4. Add Data Quality tracking.

## Expanded Source Fields

The `sources` table now supports:

| Field | Purpose |
|---|---|
| district | District name |
| state | State |
| category | Backward-compatible legacy field |
| employee_group | Licensed, Admin, Classified, Cabinet, etc. |
| employee_sub_group | Paraeducators, School Leaders, Education Support, etc. |
| document_type | Salary Schedule, Job Listing, Job Descriptions, Contract |
| school_year | 2025-26, 2026-27, etc. |
| parser | Teacher Schedule, Admin Range, Classified Range, Job List, Generic |
| status | Active, Inactive, Needs Review, Broken Link |
| priority | 1 = official source, 2 = support source, 3 = backup |
| notes | Optional notes |

## New Tables

### data_quality_issues

Stores issues found during extraction or validation.

Examples:

- Missing steps
- Missing lanes
- Suspicious salary values
- Broken links
- No rows extracted

### position_compensation

Normalized table for position-based salary comparisons.

Used for:

- Administrator
- Classified
- Cabinet
- Non-represented

### licensed_schedule_cells

Normalized table for teacher/licensed schedules.

One row per salary cell:

District + School Year + Step + Lane + Salary

### market_snapshots

Stores generated market-analysis outputs.

Examples:

- Licensed Market Summary
- Administrator Position Comparison
- Classified Pay Comparison

### job_aliases

Stores title matching and standardization rules.

Example:

Chief Talent Officer → Chief Human Resources Officer

## Migration Strategy

This patch does not use Alembic yet.

Instead, `database.py` includes lightweight startup schema upgrades:

- `create_all()` creates new tables
- `upgrade_schema()` adds missing columns to `sources`
- `backfill_source_fields()` populates new fields from legacy `category`

This is safe for the current prototype and Render deployment.

A future sprint should add Alembic migrations once the schema stabilizes.
