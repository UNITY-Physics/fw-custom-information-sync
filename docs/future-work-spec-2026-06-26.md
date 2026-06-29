# Future Work Spec Sheet — Custom Information Sync (v2)
Date: 2026-06-26
Owner: Product/Research Data Team
Audience: Developer implementing next iteration
Status: Approved implementation spec

## 1. Scope and intent
This spec defines the next implementation changes for Run 1 and Run 2 behavior based on review findings and product decisions.

Goals:
1. Make site_raw behavior explicit and operator-visible.
2. Minimize unintended mutation in Run 1 for already-current sessions.
3. Treat invalid typed values as invalid (null) with warnings and audit traceability.
4. Keep permissive date parsing for now, while making fallback usage visible in logs and outputs.
5. Make duplicate row handling visible, reviewable, and safe under concurrency.
6. Restore test coverage so CI reflects the current public interfaces.

Out of scope:
1. Major schema redesign.
2. Full harmonisation engine extraction into a separate module.
3. Backporting to old gear versions.

## 2. Definitions
1. Canonical field: field name present in utils/cde_template.yaml runtime schema.
2. Unknown field: input CSV column not in canonical schema after variable_map / legacy harmonization.
3. site_raw candidate: unknown field eligible for storage under session info namespace site_raw.*.
4. Matching key:
- label mode: subject_id + session_id
- date mode: subject_id + normalized_date
- subject_only mode: subject_id

## 3. Functional requirements

### FR-1: site_raw routing policy
Decision implemented exactly as approved:
1. Existing flag store_site_raw remains the operator opt-in for copying unknown fields into session info under site_raw.*.
2. site_raw_pattern remains useful for identifying expected raw field families and for reconciliation/report grouping, but it is not a write allowlist.

Required config behavior:
1. Existing flag store_site_raw remains master gate.
- false: no unknown fields written to site_raw.
- true: all unknown fields are written to site_raw.
2. site_raw_pattern is used for audit/report classification only.
3. Reconciliation should distinguish regex-matched site_raw fields from other unknown fields so operators can confirm what was expected versus opportunistic preservation.

Audit/report additions per row:
1. unknown_seen
2. unknown_written
3. unknown_regex_matched
4. unknown_non_regex_written

Logging:
1. Log resolved site_raw policy at run start, including whether unknowns will be preserved.
2. Log count summary at run end, including regex-matched vs non-regex unknown counts when a pattern is configured.

### FR-2: Run 1 mutation behavior
Product intent:
1. Run 1 should not mutate sessions that are already current/canonical.
2. Run 1 may mutate legacy sessions when migration/cleanup is required.

Required behavior:
1. Compute cleaned session dict as today.
2. Compare original vs cleaned session info.
3. Call replace_info only if there is a real delta.
4. If no delta, skip write.

Operational metrics (stdout + report file optional):
1. sessions_scanned
2. sessions_changed
3. sessions_unchanged
4. sessions_failed

Optional (recommended) enhancement:
1. Add run_1_apply_legacy_cleanup (default true).
- false: no mutation, export-only mode.
- true: current behavior but delta-gated.

### FR-3: Invalid typed values handling
Decision:
1. Invalid typed values become null and produce warning/audit trace.

Applies to:
1. bool
2. float/int
3. list parsing where relevant

Required behavior:
1. Valid token -> parsed value.
2. Empty token -> null (no warning).
3. Invalid token -> null + warning + audit reason code.

Boolean parsing policy:
1. True tokens: use configured allowlist (default includes 1,true,yes,y).
2. False tokens: explicit false allowlist required (for example 0,false,no,n).
3. Any other non-empty token is invalid, not false.

Audit/report additions:
1. invalid_cast_fields (semicolon separated canonical fields)
2. invalid_cast_count
3. invalid_cast_details (optional compact format field=value)

### FR-4: Date parsing remains permissive with traceability
Decision:
1. Keep fallback parsing behavior.
2. Add clear traceability in logs and reconciliation outputs.

Required behavior:
1. Continue trying configured format first.
2. Continue trying fallback formats.
3. When fallback format is used, mark parse mode as fallback.

Audit/report additions:
1. date_parse_mode: configured|fallback|failed
2. date_parse_format_used

Logging:
1. Warning on fallback usage with subject and row index.
2. End-of-run counts:
- configured_date_parses
- fallback_date_parses
- failed_date_parses

### FR-5: Duplicate row handling and concurrency safety
Decision:
1. Duplicate matching keys must be handled deterministically before threaded writes.

Required pre-validation phase:
1. Compute matching key based on selected session_match mode.
2. Detect duplicates.
3. Default behavior: emit warnings, produce a duplicate report output, and continue only with a deterministic policy.
4. Default deterministic policy: keep the last row encountered for a duplicate key.
5. Dropped row indexes and chosen survivor row index must be recorded in the duplicate report and run logs.

Thread safety requirements:
1. Do not allow concurrent creation of same non-imaging target.
2. Ensure per-key serialization for non-imaging create/update path.

### FR-6: Test-suite refresh for current interfaces
Decision:
1. The test suite must be brought back in line with the current module names, fixtures, and public APIs before using CI as a release gate.

Required work:
1. Replace stale imports and patch targets that reference removed module paths or deleted helper functions.
2. Add lightweight mock-based tests for run_1 delta-gated writes and run_2 warning behavior.
3. Ensure parser and main tests run without external Flywheel state or deprecated fixtures.

Acceptance intent:
1. Focused unit tests for parser, main, run_1, and run_2 should pass in local development and CI.

## 4. Non-functional requirements
1. Backward compatibility:
- Existing configs continue to run with sensible defaults.
- No change to default behavior unless explicitly requested by new flags.
2. Observability:
- All policy decisions visible in logs.
- Reconciliation report captures enough detail for operator troubleshooting.
3. Performance:
- Pre-validation and audit enhancements should not materially degrade runtime for typical project sizes.

## 5. Config changes
Optional additions:
1. run_1_apply_legacy_cleanup (boolean, default true)

Update docs/site_config_README.md and release notes to reflect:
1. store_site_raw preserves all unknown fields when enabled
2. site_raw_pattern is for expected raw-field families and reporting, not write restriction
3. run_1 non-mutation expectation for current sessions
4. invalid value handling
5. duplicate warning policy and deterministic survivor selection

## 6. Reconciliation report schema updates
Add columns:
1. unknown_seen
2. unknown_written
3. unknown_regex_matched
4. unknown_non_regex_written
5. invalid_cast_fields
6. invalid_cast_count
7. date_parse_mode
8. date_parse_format_used
9. duplicate_key
10. duplicate_action
11. duplicate_survivor_row
12. duplicate_dropped_rows

## 7. Acceptance criteria

AC-1 site_raw reporting behavior:
1. Given store_site_raw=true and regex present
2. Then all unknown fields are written to site_raw
3. And reconciliation distinguishes regex-matched unknown fields from other preserved unknown fields

AC-3 Run 1 no-op on current sessions:
1. Given a session with no legacy keys and no cleanup delta
2. Then Run 1 does not call replace_info for that session

AC-4 invalid bool token handling:
1. Given a bool field value of "maybe"
2. Then stored value is null
3. And reconciliation marks invalid cast for that field

AC-5 date fallback traceability:
1. Given configured format does not parse but fallback does
2. Then row reports date_parse_mode=fallback and date_parse_format_used populated

AC-6 duplicate key warning handling:
1. Given duplicate matching keys in CSV
2. Then the run emits warnings before threaded writes
3. And a duplicate report identifies the kept row and dropped rows

## 8. Test plan (minimum)

Unit tests:
1. site_raw reporting cases with and without site_raw_pattern.
2. bool invalid token behavior (invalid != false).
3. date parse mode/format reporting.
4. duplicate key detector by each session_match mode.
5. run_1 delta-gated no-op behavior.

Integration tests:
1. Run 2 with mixed unknown columns and regex.
2. Run 2 with fallback date parsing and reconciliation assertions.
3. Run 1 with unchanged canonical sessions verifies no writes.
4. Non-imaging duplicate-create race protection.
5. Main/parser tests with current fixture wiring.

Regression tests:
1. Existing v1 fallback path (no site config).
2. Existing Pakistan/PRISMA fixture behavior.

## 9. Risks and mitigations
1. Risk: operators expect old broad site_raw behavior.
Mitigation: explicit manifest/docs wording and startup policy log.
2. Risk: stricter invalid parsing increases null rates.
Mitigation: reconciliation visibility and site feedback loop.
3. Risk: duplicate warning mode may hide upstream data quality problems if logs are ignored.
Mitigation: duplicate report output plus explicit warning summary at end of run.
4. Risk: stale tests create false confidence or false failures.
Mitigation: refresh test fixtures and make focused unit tests part of release gating.

## 10. Developer implementation checklist
1. Add run-level logging and reconciliation fields for site_raw reporting.
2. Add Run 1 delta-check before replace_info.
3. Update parse/cast logic to classify invalid typed values.
4. Extend reconciliation report schema + writing logic.
5. Add duplicate pre-validation phase before ThreadPoolExecutor with warning-first survivor selection.
6. Refresh stale parser/main/run_1 tests and add targeted new coverage.
7. Update docs/release notes.

## 11. Handoff notes
1. This spec reflects approved product decisions captured on 2026-06-26.
2. If behavior conflicts with existing production assumptions, prioritize manifest/docs clarity before release.
3. Do not change defaults that increase write scope without explicit flag.
