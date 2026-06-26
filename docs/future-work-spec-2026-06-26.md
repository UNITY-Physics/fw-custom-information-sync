# Future Work Spec Sheet — Custom Information Sync (v2)
Date: 2026-06-26
Owner: Product/Research Data Team
Audience: Developer implementing next iteration
Status: Approved implementation spec

## 1. Scope and intent
This spec defines the next implementation changes for Run 1 and Run 2 behavior based on review findings and product decisions.

Goals:
1. Make site_raw behavior explicit and policy-driven.
2. Minimize unintended mutation in Run 1 for already-current sessions.
3. Treat invalid typed values as invalid (null) with warnings and audit traceability.
4. Keep permissive date parsing for now, while making fallback usage visible in logs and outputs.
5. Make duplicate row handling deterministic and safe under concurrency.

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
1. If site config contains site_raw_pattern, regex mode is strict by default.
2. Add gear-level config flag to allow all unknown fields when explicitly enabled.

Required config behavior:
1. Existing flag store_site_raw remains master gate.
- false: no unknown fields written to site_raw.
- true: unknown fields may be written, subject to below policy.
2. New flag: store_all_unknown_site_raw (default false).
3. Policy matrix:
- store_site_raw=false: write none.
- store_site_raw=true and regex present and store_all_unknown_site_raw=false: write only regex-matched unknown fields.
- store_site_raw=true and regex present and store_all_unknown_site_raw=true: write all unknown fields (regex subset plus others).
- store_site_raw=true and regex absent and store_all_unknown_site_raw=false: write none (strict behavior since no allowlist).
- store_site_raw=true and regex absent and store_all_unknown_site_raw=true: write all unknown fields.

Audit/report additions per row:
1. unknown_seen
2. unknown_written
3. unknown_skipped_by_regex
4. unknown_skipped_by_policy

Logging:
1. Log resolved site_raw policy at run start.
2. Log count summary at run end.

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
3. Default behavior: fail fast with duplicate report output and non-zero exit.

Optional mode:
1. duplicate_row_policy with values fail|keep_last.
2. Default fail.
3. keep_last must emit warnings and include dropped row indexes in report.

Thread safety requirements:
1. Do not allow concurrent creation of same non-imaging target.
2. Ensure per-key serialization for non-imaging create/update path.

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
Add to manifest.json:
1. store_all_unknown_site_raw (boolean, default false)
Description: When store_site_raw is enabled, also write all unknown CSV fields to site_raw even if not matched by site_raw_pattern.

Optional additions:
1. duplicate_row_policy (string enum: fail|keep_last, default fail)
2. run_1_apply_legacy_cleanup (boolean, default true)

Update docs/site_config_README.md and release notes to reflect:
1. strict regex routing behavior
2. optional all-unknown override
3. run_1 non-mutation expectation for current sessions
4. invalid value handling
5. duplicate policy

## 6. Reconciliation report schema updates
Add columns:
1. unknown_seen
2. unknown_written
3. unknown_skipped_by_regex
4. unknown_skipped_by_policy
5. invalid_cast_fields
6. invalid_cast_count
7. date_parse_mode
8. date_parse_format_used
9. duplicate_key
10. duplicate_action

## 7. Acceptance criteria

AC-1 site_raw strict behavior:
1. Given store_site_raw=true, regex present, store_all_unknown_site_raw=false
2. Then only regex-matched unknown fields are written to site_raw
3. And non-matching unknown fields appear in unknown_skipped_by_regex

AC-2 site_raw all-unknown override:
1. Given store_site_raw=true and store_all_unknown_site_raw=true
2. Then all unknown fields are written regardless of regex

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

AC-6 duplicate key fail-fast:
1. Given duplicate matching keys in CSV and duplicate_row_policy=fail
2. Then run exits non-zero before threaded writes
3. And duplicate report is produced

## 8. Test plan (minimum)

Unit tests:
1. site_raw policy matrix cases.
2. bool invalid token behavior (invalid != false).
3. date parse mode/format reporting.
4. duplicate key detector by each session_match mode.

Integration tests:
1. Run 2 with mixed unknown columns and regex.
2. Run 2 with fallback date parsing and reconciliation assertions.
3. Run 1 with unchanged canonical sessions verifies no writes.
4. Non-imaging duplicate-create race protection.

Regression tests:
1. Existing v1 fallback path (no site config).
2. Existing Pakistan/PRISMA fixture behavior.

## 9. Risks and mitigations
1. Risk: operators expect old broad site_raw behavior.
Mitigation: explicit manifest/docs wording and startup policy log.
2. Risk: stricter invalid parsing increases null rates.
Mitigation: reconciliation visibility and site feedback loop.
3. Risk: duplicate fail-fast blocks previously "working" files.
Mitigation: optional keep_last mode and pre-run guidance.

## 10. Developer implementation checklist
1. Implement policy gate in run_2 write path for site_raw.
2. Add new manifest config(s).
3. Add Run 1 delta-check before replace_info.
4. Update parse/cast logic to classify invalid typed values.
5. Extend reconciliation report schema + writing logic.
6. Add duplicate pre-validation phase before ThreadPoolExecutor.
7. Add tests and update docs/release notes.

## 11. Handoff notes
1. This spec reflects approved product decisions captured on 2026-06-26.
2. If behavior conflicts with existing production assumptions, prioritize manifest/docs clarity before release.
3. Do not change defaults that increase write scope without explicit flag.
