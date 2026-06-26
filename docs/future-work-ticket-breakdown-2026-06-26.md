# Implementation Ticket Breakdown — Future Work
Date: 2026-06-26
Source spec: docs/future-work-spec-2026-06-26.md
Audience: Dev lead, implementer, QA

## Overview
This breakdown converts the approved spec into implementation tickets with dependency order, estimates, and done criteria.

Recommended sprint order:
1. Policy plumbing and config flags
2. Core behavior changes in run_2 and run_1
3. Reconciliation/report expansions
4. Validation and concurrency safety
5. Docs and release notes

Estimate scale:
1. S = 0.5 to 1 day
2. M = 1 to 2 days
3. L = 2 to 4 days

## Ticket 1: Add config flags and startup policy logging
Type: Feature
Estimate: S
Depends on: none

Scope:
1. Add manifest config flag store_all_unknown_site_raw with default false.
2. Optional flag duplicate_row_policy with default fail.
3. Optional flag run_1_apply_legacy_cleanup with default true.
4. Emit startup log line summarizing resolved policies.

Files likely touched:
1. manifest.json
2. app/main.py
3. app/parser.py
4. app/run_1.py
5. app/run_2.py

Acceptance criteria:
1. New flags visible in manifest and runtime config parsing.
2. Startup logs show effective values.
3. Existing runs without new flags behave as before.

Test notes:
1. Unit test parser defaults.
2. Smoke test run startup logs include policy summary.

## Ticket 2: Implement strict site_raw policy matrix
Type: Feature
Estimate: M
Depends on: Ticket 1

Scope:
1. Enforce site_raw_pattern in write path as strict allowlist when store_site_raw is true and store_all_unknown_site_raw is false.
2. When store_all_unknown_site_raw is true, write all unknown fields.
3. Keep canonical dedup guard.
4. Add policy-driven counters for unknown_seen, unknown_written, unknown_skipped_by_regex, unknown_skipped_by_policy.

Files likely touched:
1. app/run_2.py

Acceptance criteria:
1. Regex present plus strict mode writes only regex-matched unknown fields.
2. Regex absent plus strict mode writes no unknown fields.
3. All-unknown override writes all unknown fields.
4. Counters are present and correct in reconciliation output.

Test notes:
1. Unit tests for full matrix combinations.
2. Integration test with mixed unknown columns.

## Ticket 3: Add invalid typed value classification and warnings
Type: Feature
Estimate: M
Depends on: none

Scope:
1. Change cast logic so invalid non-empty values become null and are recorded as invalid, not silently coerced to false or dropped without trace.
2. Define explicit true and false token allowlists for bool parsing.
3. Wire per-row invalid cast audit fields.

Files likely touched:
1. app/run_2.py

Acceptance criteria:
1. Invalid bool values map to null with warning.
2. Invalid numeric values map to null with warning.
3. Reconciliation includes invalid_cast_fields and invalid_cast_count.

Test notes:
1. Unit tests for bool token matrix.
2. Unit tests for numeric invalid tokens.
3. Integration assertion in reconciliation row content.

## Ticket 4: Keep permissive date parsing with parse-trace audit
Type: Feature
Estimate: S
Depends on: none

Scope:
1. Preserve existing fallback date parsing behavior.
2. Add row-level audit fields date_parse_mode and date_parse_format_used.
3. Add warning when fallback format is used.
4. Add end-of-run parse mode summary counts.

Files likely touched:
1. app/run_2.py

Acceptance criteria:
1. Configured format success marks configured.
2. Fallback success marks fallback and format used.
3. Failed parse marks failed with reason code.

Test notes:
1. Unit tests for configured, fallback, failed paths.
2. Integration test validates reconciliation columns.

## Ticket 5: Run 1 delta-gated mutation behavior
Type: Feature
Estimate: M
Depends on: Ticket 1 if run_1_apply_legacy_cleanup flag included

Scope:
1. Compute pre-clean and post-clean session info.
2. Call replace_info only when delta exists.
3. Add run summary counters for scanned, changed, unchanged, failed.
4. If run_1_apply_legacy_cleanup is false, skip mutation and export only.

Files likely touched:
1. app/run_1.py

Acceptance criteria:
1. Canonical unchanged sessions are not written.
2. Legacy sessions with real delta are written.
3. Summary metrics print at run end.

Test notes:
1. Unit tests with mocked session objects.
2. Integration-like test for mixed legacy/current inputs.

## Ticket 6: Duplicate row pre-validation and deterministic policy
Type: Feature
Estimate: L
Depends on: Ticket 1

Scope:
1. Build pre-validation stage before ThreadPool execution.
2. Compute matching key by mode:
- label: subject_id + session_id
- date: subject_id + normalized_date
- subject_only: subject_id
3. Implement duplicate_row_policy fail default.
4. Optional keep_last policy with explicit dropped row tracking.
5. Emit duplicate report output when duplicates detected.

Files likely touched:
1. app/run_2.py

Acceptance criteria:
1. Duplicate rows in fail mode stop run before writes.
2. Duplicate rows in keep_last mode process deterministically.
3. Duplicate metadata captured in report.

Test notes:
1. Unit tests by session_match mode.
2. Integration tests for fail and keep_last.

## Ticket 7: Non-imaging creation race safety
Type: Reliability
Estimate: M
Depends on: Ticket 6 recommended

Scope:
1. Prevent concurrent duplicate creation of same non-imaging target.
2. Introduce per-key lock or equivalent serialization around create/update decision path.
3. Preserve current idempotent source_row_uid behavior.

Files likely touched:
1. app/run_2.py

Acceptance criteria:
1. Concurrent duplicate candidate rows do not create duplicate non-imaging sessions.
2. Re-runs remain idempotent.

Test notes:
1. Multi-row same-key stress test.
2. Simulated concurrency test with mock subject sessions.

## Ticket 8: Reconciliation schema expansion and migration notes
Type: Feature
Estimate: S
Depends on: Tickets 2, 3, 4, 6

Scope:
1. Add new reconciliation columns from spec.
2. Ensure stable column ordering and backward compatibility handling for downstream consumers.
3. Add simple changelog note in output or docs about new columns.

Files likely touched:
1. app/run_2.py
2. docs/release_notes.md

Acceptance criteria:
1. New columns present with expected values.
2. Existing columns preserved.

Test notes:
1. Snapshot-style reconciliation schema test.

## Ticket 9: Documentation updates for operator behavior
Type: Docs
Estimate: S
Depends on: Tickets 1 to 8

Scope:
1. Update operator guide with site_raw strict vs all-unknown behavior.
2. Update Run 1 behavior to explain delta-gated mutation.
3. Document invalid value handling and warnings.
4. Document duplicate policy and recommended preprocessing.
5. Update release notes.

Files likely touched:
1. docs/site_config_README.md
2. docs/release_notes.md
3. README.md

Acceptance criteria:
1. Docs match runtime behavior.
2. No contradictory statements across manifest and docs.

Test notes:
1. Manual review checklist against manifest descriptions.

## Suggested dependency graph
1. Ticket 1 -> Ticket 2
2. Ticket 1 -> Ticket 5
3. Ticket 1 -> Ticket 6
4. Ticket 2, Ticket 3, Ticket 4, Ticket 6 -> Ticket 8
5. Ticket 6 -> Ticket 7
6. Tickets 1 to 8 -> Ticket 9

## Suggested sprint split
Sprint A:
1. Ticket 1
2. Ticket 2
3. Ticket 3
4. Ticket 4

Sprint B:
1. Ticket 5
2. Ticket 6
3. Ticket 7
4. Ticket 8
5. Ticket 9

## QA execution checklist
1. Run unit tests focused on run_2 policy behavior and cast logic.
2. Run integration fixture tests with Pakistan and PRISMA configs.
3. Validate reconciliation CSV schema and row values for new fields.
4. Validate no-op Run 1 behavior on canonical project snapshot.
5. Validate duplicate fail-fast prevents any write operations.

## Delivery definition
All tickets are complete when:
1. Acceptance criteria met.
2. Tests added and passing.
3. Docs updated and aligned with behavior.
4. Release notes updated with user-visible changes.
