# Release Notes
05/31/2026:
V0.1.19 (staging candidate):
1) Added guarded non-imaging session upsert flow for unmatched rows when `additional_non_imaging_sessions=true`.
2) Added non-imaging guardrails:
    - block creation near imaging dates (configurable window)
    - optional visit marker requirement
    - optional explicit override for near-imaging creation
3) Added deterministic row UID behavior so repeated uploads update existing non-imaging sessions instead of creating duplicates.
4) Expanded reconciliation reporting with row-level status and reason codes for imaging, non-imaging, blocked, and invalid rows.
5) Wired `dry_run` through run-2 no-write path for both imaging and non-imaging decisions.

06/08/25:
V0.1.0
In this version, the gear can 
1) Clean existing legacy data that used the old template by renaming and replacing session information fields
    Where fields are not in the new template, the columns are kept as they are.
2) Clean data where the default value was an integer (0) to avoid confusion

04/02/2026:
V0.1.3:
Fix utf-8 encoding when reading the csv