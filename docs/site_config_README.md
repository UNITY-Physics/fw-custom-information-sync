# Site Config Guide — UNITY Custom Information Sync

This guide is for site data managers who prepare and upload participant data to the UNITY Flywheel platform. You do not need programming experience to follow it.

V.1.0 (2026-06-26): niall.bourke@kcl.ac.uk 

---

## What is the site config?

When you upload a spreadsheet to Flywheel, the column names in your file may not match the standard names used across the UNITY consortium. The site config is a small settings file (`.yaml` format) that tells the gear how to translate your spreadsheet into the consortium standard.

Think of it as a **translation dictionary**: your column name on the right, the UNITY standard name on the left.

You only need to create this file once per site. After that, re-use it and only update it each time you make changes to the column names in your spreadsheet.

---

## The two files you upload

| File | What it is |
|---|---|
| Your data spreadsheet | The CSV exported from your database or Excel file — column names in your own format |
| `site_config.yaml` | The settings file described in this guide |

Both are uploaded as gear inputs when running **Custom Information Sync (Run 2)**.

---

## Step-by-step setup

### Step 1 — Get the template

You will have received `site_config_template.yaml` from your study coordinator, or retrieve by running the gear with no input. If run with no input, the gear will generate the template for you, that you can download. Open it in any text editor (Notepad, TextEdit, VS Code, etc.).

> **Do not open it in Excel.** Excel will corrupt the formatting.

### Step 2 — Set your subject ID column

Find this line near the top:

```yaml
id_field: "sub_id"
```

Replace `sub_id` with the name of the column in your spreadsheet that contains the **subject identifier** — the same ID used to label participants in Flywheel.

Example: if your spreadsheet has a column called `participant_id`, change this to:
```yaml
id_field: "participant_id"
```

> **Important:** The values in this column must match the subject labels in Flywheel exactly, including capitalisation. If they do not match, sessions will not be found. See [Sessions not matching](#sessions-not-matching) below.

### Step 3 — Choose how sessions are matched

The gear needs to know which row in your spreadsheet corresponds to which MRI session in Flywheel.

```yaml
session_match: "date"
```

Choose one mode using this quick guide:

1. If each participant has exactly one session in Flywheel, use `"subject_only"`.
2. If participants can have multiple sessions and your CSV has a scan date column, use `"date"` (recommended).
3. If participants can have multiple sessions but you do not have reliable scan dates, use `"label"`.

Required fields by mode:

| `session_match` value | Required CSV columns | Extra site config needed |
|---|---|---|
| `"date"` | `subject_id` (via `id_field`) + your date column | `session_date_field`, `session_date_format`, `session_date_tolerance_days` |
| `"label"` | `subject_id` (via `id_field`) + `session_id` | none |
| `"subject_only"` | `subject_id` (via `id_field`) only | none |

Examples:

**A) Date matching (recommended when multiple sessions exist):**

```yaml
id_field: "participant_id"
session_match: "date"
session_date_field: "scan_date"
session_date_format: "%d/%m/%Y"
session_date_tolerance_days: 1
```

**B) Label matching (use when you have a `session_id` column):**

```yaml
id_field: "participant_id"
session_match: "label"
```

Your CSV must contain a `session_id` column in this mode.

**C) Subject-only matching (use only when each subject has one session):**

```yaml
id_field: "participant_id"
session_match: "subject_only"
```

If a subject has more than one session in Flywheel, that row will be marked as `ambiguous` and skipped.

#### Date format codes

| Your date looks like | Format string |
|---|---|
| 27/03/2026 | `"%d/%m/%Y"` |
| 03/27/2026 | `"%m/%d/%Y"` |
| 2026-03-27 | `"%Y-%m-%d"` |
| 27-03-2026 | `"%d-%m-%Y"` |
| 27/03/26 | `"%d/%m/%y"` |

If your dates are stored as Excel serial numbers or in an unusual format, contact your study coordinator.

### Step 4 — Map your column names

Open the `variable_map` section. It looks like a long commented-out list:

```yaml
variable_map:
  # childTimepointAge_days: "your_column"    # float
  # childBirthWeight_kgs: "your_column"      # float
  ...
```

For each UNITY field that you collect, **remove the `#` at the start** of the line and replace `"your_column"` with the exact name of the corresponding column in your spreadsheet.

Example — if your spreadsheet has a column `age_at_scan_days` for the child's age:
```yaml
  childTimepointAge_days: "age_at_scan_days"
```

#### Columns that are already named correctly

If a column in your spreadsheet already uses the exact UNITY canonical name (e.g. your column is already called `childTimepointAge_days`), you do **not** need to list it in `variable_map`. The gear will find it automatically.

#### Hardcoded values (same for every participant)

If a value is the same for every participant and is not in your spreadsheet at all — for example, all participants are from the same country — use `constant_map` (see Step 4b below), **not** `variable_map`. Writing a string literal directly inside `variable_map` is not supported and will be logged as a warning.

### Step 4b — Set constant values (same for all participants)

If a value does not come from your spreadsheet but is the same for every participant — for example, all sessions are from Pakistan, or all were scanned at 3T — use `constant_map`:

```yaml
constant_map:
  CohortLocation_country: "Pakistan"
  MRI_fieldStrength: 3.0
```

Every session will receive these values regardless of what the CSV contains. Use `variable_map` only for values that **vary per row**.

### Step 5 — Remap coded values (if needed)

If your spreadsheet uses codes instead of the UNITY standard text (for example `M`/`F` instead of `Male`/`Female`), use `value_map`:

```yaml
value_map:
  childBiologicalSex:
    "M": "Male"
    "F": "Female"
    "1": "Male"
    "0": "Female"
```

Only include fields where your codes differ from the expected values.

### Step 6 — Declare unit conversions (if needed)

If any measurements in your spreadsheet are in different units from the UNITY standard, declare them in `unit_map`.

UNITY canonical units: **weight → kg**, **height/length → inches**, **head circumference → cm**, **gestational age → weeks**, **age → days**.

Example — birth weight recorded in pounds:
```yaml
variable_map:
  childBirthWeight_kgs: "birth_weight_column"   # <-- use the _kgs field name

unit_map:
  childBirthWeight_kgs:
    source_unit: "lbs"
    target_unit: "kg"
    conversion: "multiply_by_0.453592"
```

> **Important:** The field name in `unit_map` must match exactly the field name used in `variable_map`. If `variable_map` maps to `childBirthWeight_kgs`, then `unit_map` must also use `childBirthWeight_kgs`. Using `childBirthWeight_lbs` in one and `childBirthWeight_kgs` in the other will silently skip the conversion — the gear will log a warning if this happens.

### Step 7 — Drop columns you do not want to upload

If your spreadsheet contains internal tracking columns, admin notes, or any data you do not want stored in Flywheel, list them under `drop_columns`:

```yaml
drop_columns:
  - "internal_notes"
  - "data_entry_initials"
  - "admin_flag"
```

### Step 8 — Save and upload

Save the file as `site_config.yaml` (not `.txt`). Upload it as a gear input alongside your data CSV when running the gear.

### Optional — Enable non-imaging session creation

Some studies collect visits that do not correspond to MRI scan sessions. To preserve these rows safely, the gear now supports an optional non-imaging path.

1. Enable gear config `additional_non_imaging_sessions`.
2. In `site_config.yaml`, set:

```yaml
non_imaging_date_field: "visit_date"
non_imaging_date_format: "%d/%m/%Y"
non_imaging_visit_type_field: "visit_type"
non_imaging_visit_type_allowlist:
  - "home_visit"
  - "clinic_visit"
non_imaging_visit_marker_fields:
  - "non_imaging_visit_flag"
```

Safety behavior:

1. If a row can be matched to an imaging session, imaging sync is used.
2. If no imaging match is found, the gear may create/update a non-imaging session.
3. Creation is blocked when the row date is very close to an imaging date (guard window), unless explicitly overridden by force-create settings.
4. Re-runs are idempotent: the same row updates the same non-imaging session via a deterministic row UID.

### Staging validation checklist

Before production use, run this checklist on a staging Flywheel project:

1. Start with `dry_run: true` and `additional_non_imaging_sessions: true`.
2. Upload a CSV that includes:
3. One row that should match an imaging session.
4. One row with a valid non-imaging visit date that should create a non-imaging session.
5. One row within the near-imaging guard window that should be blocked.
6. One malformed date row that should fail parsing.
7. Confirm `reconciliation_report.csv` contains expected `row_status` values:
8. `imaging_matched`
9. `non_imaging_created` (in dry-run this is simulated in report only)
10. `non_imaging_blocked_near_imaging`
11. `invalid_row`
12. Re-run with `dry_run: false` using the same CSV.
13. Confirm non-imaging sessions are created only for expected rows.
14. Re-run the same file a third time and verify idempotency:
15. No duplicate non-imaging sessions should appear.
16. Existing non-imaging sessions should show `non_imaging_updated`.

### Recommended staging test scenarios

Use these focused scenarios when tuning site config rules:

1. Visit marker required:
2. Set `non_imaging_require_visit_marker: true` with no marker fields populated.
3. Confirm rows are rejected with `reason_code = no_visit_marker`.
4. Visit allowlist enforcement:
5. Provide `non_imaging_visit_type_allowlist` and include one out-of-list visit type.
6. Confirm row is rejected with `reason_code = visit_type_not_allowed`.
7. Near-imaging override behavior:
8. Set `non_imaging_allow_within_imaging_window_if_explicit: true`.
9. Provide force-create marker for a near-imaging row.
10. Confirm row is allowed only when explicit override value is present.
11. Field routing filters:
12. Set `non_imaging_include_fields_regex` and `non_imaging_exclude_fields_regex`.
13. Confirm only intended fields are written onto non-imaging sessions.

---

## Outputs from the gear

The gear produces three files in the gear output:

| File | Contents |
|---|---|
| `reconciliation_report.csv` | One row per participant/session: what was written, what was empty, whether the session was found |
| `canonical_not_in_csv.csv` | List of UNITY standard fields that were not present in your uploaded spreadsheet at all |
| `site_config_template.yaml` | (Run 1 only) Blank template for you to fill in |

**Always check `reconciliation_report.csv` after a run.** The `match_status` column tells you whether each session was found (`updated`) or missed (`not_found`).

---

## FAQ

**Q: Do I need to include every column in `variable_map`?**  
No. Only columns whose names differ from the UNITY canonical names. Columns already named correctly are picked up automatically.

**Q: What happens to columns in my spreadsheet that are not UNITY standard fields?**  
If the gear config option `store_site_raw` is enabled (ask your study coordinator), they are stored in Flywheel under a `site_raw` namespace and listed in `site_raw_written` in the reconciliation report. If it is disabled, they are listed in `unknown_skipped` and not uploaded. Either way, they do not cause an error.

**Q: What if I accidentally upload data with a mistake and want to correct it?**  
Fix the values in your spreadsheet and re-run the gear with the corrected CSV. The gear will overwrite the previously uploaded values. There is no need to manually delete anything in Flywheel first. Fields that are blank in your corrected CSV will not overwrite existing values — only filled-in cells are written.

**Q: Can I add new participants to the spreadsheet and re-run?**  
Yes. The gear processes every row in the CSV. Rows for participants already uploaded will be updated; rows for new participants will be added. Participants in Flywheel with no row in the CSV are left untouched.

**Q: My spreadsheet has 300 GSED item columns. Will they all be uploaded?**  
They will go to `site_raw` if `store_site_raw` is enabled, which may be undesirable. Use `site_raw_pattern` to route them explicitly, or add them to `drop_columns` to discard them. Example:
```yaml
site_raw_pattern: "^(gl1|gs1)"    # routes all GSED item columns to site_raw
drop_columns:
  - "agedays_gsed_lf"             # individual admin column
```

**Q: The gear ran but nothing was written. What went wrong?**  
Check the reconciliation report. If every row shows `not_found`, the subject IDs or dates in your spreadsheet are not matching what is in Flywheel. See [Sessions not matching](#sessions-not-matching).

**Q: Does the gear delete data from Flywheel?**  
Run 2 does not delete existing session custom info fields — it only adds or updates values. However, Run 1 applies `clean_session`, which permanently removes fields listed in the legacy migration table (`old_new_harmonization.yaml`). This affects old field names that have been renamed or removed from the agreed schema (e.g. `birth_hc_cm`, `birth_length_cm`, v1 GSED scoring columns). Canonical fields in `cde_template.yaml` are never removed by Run 1 — only legacy keys listed in `delete_keys`.

**Q: What is `dry_run`?**  
A gear config option (set in the Flywheel gear run form, not in this file). When enabled, the gear runs through all matching and mapping logic and writes the reconciliation report, but does not actually write any values to Flywheel. Use it to verify your config is correct before committing.

---

## Troubleshooting

### Sessions not matching

**Symptom:** `reconciliation_report.csv` shows `not_found` for some or all rows.

The gear tried to find each row's participant in Flywheel but could not. Work through the following checks:

1. **Wrong `id_field`**  
   Open your CSV and confirm the column name exactly matches what you put in `id_field`. Column names are case-sensitive.

2. **Subject IDs don't match Flywheel labels**  
   Go to Flywheel → your project → Subjects. Compare the subject labels there with the values in your subject ID column. Common differences:
   - Hyphens vs underscores (`subject-001` vs `subject_001`)
   - Leading zeros (`001` vs `1`)
   - Extra spaces
   
   Fix the labels in either Flywheel or your CSV so they match exactly. The gear does not transform IDs automatically.

3. **Wrong date column or date format** (when `session_match: "date"`)  
   - Check `session_date_field` matches the column header exactly.
   - Open your CSV and look at how dates are formatted. Are they `27/03/2026` or `2026-03-27`? Update `session_date_format` to match.
   - Check `session_date_tolerance_days`. If your scan dates in Flywheel were recorded a day or two off, increase this to `2` or `3`.
   - Excel sometimes exports dates as serial numbers (e.g. `46116`). If you see numbers instead of dates, re-export your spreadsheet ensuring the date column is formatted as text.

4. **Multiple sessions per subject on the same date**  
   If a subject has two Flywheel sessions on the same date, the gear will report `ambiguous` and skip that row. Resolve the duplicate sessions in Flywheel or use `session_match: "label"` with an explicit session label column instead.

5. **Session exists in Flywheel but not at the expected date**  
   The gear checks both the session's recorded timestamp and its label. If neither matches your date, the session will not be found. Contact your study coordinator to verify when the sessions were created in Flywheel.

---

### Non-canonical data (columns not in the UNITY standard)

**Symptom:** The reconciliation report shows columns in `unknown_skipped` that you expected to be written.

Non-canonical columns are columns in your CSV that do not match any UNITY standard field name. What happens to them depends on the `store_site_raw` gear setting:

- **`store_site_raw: false` (default):** Non-canonical columns are not written to Flywheel. They appear in `unknown_skipped` in the reconciliation report. This is not an error — they are simply not part of the agreed consortium variables.
- **`store_site_raw: true`:** Non-canonical columns are written to Flywheel under a `site_raw` namespace and appear in `site_raw_written`.

If a column you expected to be written is showing up in `unknown_skipped`:
1. Check whether that field exists in the UNITY canonical list (`canonical_not_in_csv.csv` tells you which canonical fields were absent from your upload — but for the reverse, check `variable_map`).
2. If the field has a different name in the canonical schema, add a mapping in `variable_map`.
3. If it is genuinely a site-specific field that you want preserved, ask your study coordinator to enable `store_site_raw`.

---

### Re-running after data is already uploaded

You can re-run the gear as many times as needed. The key behaviour to know:

- **Filled cells overwrite existing values.** If you correct a birth weight in your CSV and re-run, the new value replaces the old one in Flywheel.
- **Empty cells do not overwrite.** If a cell is blank in your CSV, whatever is already in Flywheel for that field is left unchanged. This means you can upload a partial spreadsheet and only the columns you provide will be affected.
- **Re-running does not duplicate data.** It is safe to re-run with the same CSV. The gear is idempotent for filled cells.
- **The `pre_existing` column in the reconciliation report** lists fields that already had a value in Flywheel before this run. Review it if you are concerned about accidental overwrites.

---

### Likely causes of an unsuccessful gear run

| Symptom | Likely cause | Fix |
|---|---|---|
| Gear fails immediately with a YAML error | The site config file has a formatting problem — most commonly using `{...}` brace syntax for `value_map` or `unit_map` | Use the indented block style shown in the template; do not use `{}` |
| Gear fails with "required column missing: subject_id" | `id_field` is not set, or the column name in `id_field` does not exist in the CSV | Check the column name exactly matches (case-sensitive) |
| Gear fails with "required column missing: session_id" | `session_match` is set to `"label"` but there is no `session_id` column in the CSV | Either add a `session_id` column, or switch to `session_match: "date"` or `"subject_only"` |
| 0 sessions updated, all `not_found` | Subject IDs or dates do not match Flywheel | See [Sessions not matching](#sessions-not-matching) |
| Unit conversion not applied | `variable_map` and `unit_map` use different field names for the same column | They must use identical field names; the gear logs a warning |
| Gear runs but `fields_written` is empty for all sessions | All cells in the CSV are blank, or all column names are unrecognised | Check that your CSV exported correctly and that `variable_map` is filled in |
| `value_map` not being applied | The field named in `value_map` is not present in `variable_map` or not in the CSV | Ensure the field is mapped (or already canonical) before `value_map` runs |
| API key error / authentication failure | The gear was run without a valid Flywheel API key, or the key has expired | Re-enter the API key in the gear input form |
| Gear times out with large CSV | Very large CSVs (thousands of rows) take longer; the gear uses parallel processing but Flywheel API rate limits apply | Contact your study coordinator if timeouts are frequent |

---

## YAML formatting — common mistakes

YAML is whitespace-sensitive. The most common mistakes that break the file:

**Use spaces, not tabs.** If your text editor inserts tab characters when you press Tab, switch it to insert spaces instead.

**Indentation must be consistent.** Entries under `variable_map:`, `value_map:`, `unit_map:` must all be indented with exactly two spaces:
```yaml
variable_map:
  childBiologicalSex: "sex"     ✓  (2 spaces)
	childBiologicalSex: "sex"     ✗  (tab character — will fail)
 childBiologicalSex: "sex"      ✗  (1 space — will fail)
```

**Do not use curly braces for `value_map` or `unit_map`:**
```yaml
value_map: { "M": "Male" }     ✗  will fail
value_map:                      ✓
  childBiologicalSex:
    "M": "Male"
```

**Quote strings that contain special characters** (colons, hashes, brackets):
```yaml
id_field: participant:id        ✗  colon breaks YAML
id_field: "participant:id"      ✓
```

**Check your file was saved as plain text.** If you edited the YAML in Word or another rich-text editor, it may have introduced "smart quotes" (`"` instead of `"`). Use a plain text editor.

---

## Quick reference — canonical units

| Measurement | UNITY unit |
|---|---|
| Weight | kg |
| Height / length | inches |
| Head circumference | cm |
| Gestational age | weeks |
| Age | days |

---

## Getting help

If you are unsure whether a field in your data matches a UNITY canonical field, or if the gear fails in a way not covered here, contact your study coordinator and share:

1. The reconciliation report (`reconciliation_report.csv`)
2. The canonical fields list (`canonical_not_in_csv.csv`)
3. The gear log from the failed run (available in Flywheel under the gear run's **Logs** tab)
