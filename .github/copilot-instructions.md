# Custom Information Sync Gear — v2 Development Context

## What this gear does (v1)

**Custom Information Sync** is a Flywheel gear that syncs clinical/demographic metadata into Flywheel session custom info containers across multi-site neuroimaging studies.

It has two operating modes:

### Run 1 — No inputs (template generation)
- Iterates all non-phantom subjects/sessions in a Flywheel project
- Pre-populates any missing canonical fields on each session using defaults from `utils/cde_template.yaml`
- Applies legacy key migration via `utils/old_new_harmonization.yaml` and `utils/clean_session_info.py`
- Exports a CSV template: rows = sessions, columns = `[group_id, project_id, subject_id, session_id, ...canonical_fields]`
- The CSV is intended to be downloaded, filled by site data managers, and re-uploaded

### Run 2 — With session_info CSV input (metadata write-back)
- Reads the user-provided CSV
- Applies legacy column renaming from `utils/old_new_harmonization.yaml`
- Type-casts all fields against the canonical template using `cast_metadata_fields()`
- Updates each matching Flywheel session's custom info using 8-thread parallel execution
- Session matching is done by **exact string match** on `session_id` (the session label in Flywheel)

### Key files
| File | Role |
|---|---|
| `app/main.py` | Entry point; dispatches to run_1 or run_2 |
| `app/run_1.py` | Template generation logic |
| `app/run_2.py` | Metadata write-back logic; type casting; thread pool |
| `app/get_inputs.py` | Loads gear inputs (api-key, session_info CSV path) |
| `app/parser.py` | Reads `dry_run` config flag |
| `utils/cde_template.yaml` | Canonical variable registry (Demographics, SES, Cognitive, Clinical, Derived, SiteRaw) |
| `utils/old_new_harmonization.yaml` | Legacy column rename map (`old_key_new_key`) and keys to delete |
| `utils/clean_session_info.py` | Applies legacy renames + default cleanup to individual session dicts |
| `utils/site_config_template.yaml` | **[v2 — planned]** Annotated site config template distributed to sites for onboarding |
| `manifest.json` | Gear metadata; current version 0.1.10; Python 3.11 |

### Canonical variable schema
Defined in `utils/cde_template.yaml` across six sections (113 fields total):
- **Demographics** — cohort IDs, anthropometrics, gestational age, birth data, household composition
- **SES** — maternal education (HHS + years), child SES scores
- **Cognitive** — GSED, MSEL, BSID, ASQ, WPPSI, WISC, AAB scores
- **Clinical** — health group, birth setting
- **Derived** — WHO z-scores (WAZ, HAZ, WHZ, HCZ, BMIZ), BMI, nutritional status flags
- **SiteRaw** — placeholder namespace; not used in template generation or type casting

Type is inferred from the default value (`0` → float, `None` → str, `True` → bool, `[]` → list).

---

## Known v1 limitations

1. **Fragile session matching** — join key is the exact Flywheel session label (often a DICOM-derived timestamp string). Any formatting difference causes a silent miss.
2. **ID inconsistency** — subject labels may differ between Flywheel and site spreadsheets (e.g. hyphen vs underscore). No normalisation is applied during matching.
3. **Rigid template** — sites must return data in the exact column layout. Variable names must exactly match canonical names; no aliasing at upload time.
4. **Template is project-agnostic** — every project gets the same column set regardless of which variables that site actually collects.
5. **No reconciliation report** — there is no output indicating which sessions matched, which were skipped, or which rows were unmatched.
6. **Unit assumptions** — weights/heights are assumed to be in canonical units; no conversion is applied.
7. **`dry_run` config flag exists but is not fully wired into write-back logic in run_2**.

---

## v2 Architecture Goals

The core architectural shift for v2 is:

> **Sites upload data in their own format. The gear does the reconciliation.**

### 1. Site-specific config files (per-project)
A YAML config stored as a Flywheel project attachment (or gear input) that encodes site conventions:

```yaml
# Example site config
id_field: "participant_id"           # their column for subject
id_transform: "replace('-', '_')"    # normalisation to match Flywheel labels
session_match: "date"                # match on date rather than session label
session_date_field: "visit_date"
session_date_format: "%d/%m/%Y"
session_date_tolerance_days: 3       # fuzzy window for date matching
variable_map:
  childBirthWeight_kgs: "Weight"     # canonical → site column name
  childGestation_weeks: "GA_weeks"
  cohortLocation_country: "KENYA"    # hardcoded constant (no site column needed)
unit_map:
  childBirthWeight_kgs:
    source_unit: "lbs"
    target_unit: "kg"
    conversion: "multiply_by_0.453592"
```

### 2. Variable classification

When processing an uploaded CSV, classify each column into:

| Category | Description | Action |
|---|---|---|
| **A — Canonical** | Exact match or known alias in `cde_template.yaml` | Auto-map, cast type, write |
| **B — Unknown** | Not in canonical schema, not ambiguous | Store under `site_raw.<field>` namespace OR report for admin review |
| **C — Ambiguous** | Short name that could map to multiple canonical fields (e.g. `weight`) | Warn; do not auto-map |

Known aliases should be maintained in `old_new_harmonization.yaml` and augmented over time (persistent learning).

### 3. Reconciliation report
Run 2 must produce an output file (`reconciliation_report.csv` or `.txt`) containing:
- Sessions matched (subject_id, session_id, match method)
- Sessions in CSV but not found in Flywheel
- Sessions in Flywheel but not in CSV
- Variables mapped (canonical name ← uploaded column)
- Variables skipped (unknown / ambiguous)
- Unit conversions applied
- Dry-run: what *would* have been written

### 4. Flexible session matching
Priority order for matching:
1. Exact `session_id` label match (current behaviour)
2. Date-based match using site config `session_date_field` + tolerance window
3. Subject-only match when there is exactly one session per subject

### 5. Unit normalisation
Define unit conversion rules in site config or a global `unit_conversions.yaml`. Apply before writing. Always store in canonical unit.

### 6. Backward compatibility
- v1 behaviour (no site config, template CSV with canonical column names) must continue to work
- Detect whether a site config is present; if absent, fall back to v1 logic

---

## v2 Site Config Template

### Overview — the three-layer data flow

```
Layer 1 — Canonical schema      utils/cde_template.yaml
           (stable, gear-owned)          |
                                         | Run 1 generates template CSV
                                         ↓
Layer 2 — Site mapping config   site_config_<site>.yaml
           (per-project, site fills in)  |
                                         | Site fills CSV + config, uploads both
                                         ↓
Layer 3 — Raw site data         session_info.csv (site's own column names)
           (gear input, CSV)             |
                                         | Run 2: config drives reconciliation
                                         ↓
                               Flywheel session custom info
```

The site config is the **translation key** between layer 3 (raw site data) and layer 1 (canonical schema). Without a site config the gear falls back to v1 behaviour (raw CSV must already use canonical column names).

### Planned file: `utils/site_config_template.yaml`

This annotated template is distributed to sites alongside the Run 1 CSV. Sites complete it and upload it as a gear input (or as a Flywheel project attachment named `site_config.yaml`).

```yaml
# ============================================================
# UNITY Custom Information Sync — Site Config Template
# Version: 2
# ============================================================
# Complete this file for your site and supply it as a gear
# input when running Custom Information Sync (Run 2).
# Only include keys relevant to your data; all keys with
# null or empty defaults are optional.
# ============================================================

# --- Subject / session matching ---

# REQUIRED: the column in your CSV that holds the subject identifier
id_field: "participant_id"

# Optional transform applied to id_field values before matching Flywheel
# subject labels. Supported values:
#   "upper"              → convert to uppercase
#   "lower"              → convert to lowercase
#   "strip"              → strip leading/trailing whitespace
#   "replace('-','_')"   → replace hyphens with underscores
#   null                 → no transform
id_transform: null

# How to match rows in your CSV to Flywheel sessions.
#   "label"        → exact match on Flywheel session label (v1 default)
#   "date"         → match on scan date (requires session_date_field below)
#   "subject_only" → use when every subject has exactly one session
session_match: "label"

# Required when session_match is "date":
session_date_field: null          # your CSV column name for scan date
session_date_format: "%Y-%m-%d"   # Python strptime format string
session_date_tolerance_days: 0    # allow ±N days when matching

# --- Variable mapping ---

# Maps canonical field names (from cde_template.yaml) to either:
#   - a column name string  → gear reads values from that CSV column
#   - a scalar constant     → gear writes that value for every session
# Omit fields that are already named canonically in your CSV
# (they will be auto-mapped) or that are covered by old_new_harmonization.yaml.
variable_map: {}
# Examples:
#   CohortLocation_country: "Kenya"     # constant — written for every row
#   studyTimepoint: "visit"             # read from column "visit"
#   childBiologicalSex: "sex_column"    # read from column "sex_column"

# --- Value transforms ---

# Remap raw cell values to canonical controlled-vocabulary values.
# Keys must be canonical field names that also appear in variable_map above.
value_map: {}
# Example:
#   childBiologicalSex:
#     "yes": "Male"
#     "no": "Female"
#     "1": "Male"
#     "0": "Female"

# --- Unit conversions ---

# Declare the source unit for any field where your data differs from the
# canonical unit. The gear converts before writing.
# Canonical units: weight → kg, height/length → cm, head circumference → cm,
#                  gestational age → weeks, age → days.
unit_map: {}
# Example:
#   childBirthWeight_kgs:
#     source_unit: "lbs"
#     target_unit: "kg"
#     conversion: "multiply_by_0.453592"
#   childTimepointHeight_cm:
#     source_unit: "inches"
#     target_unit: "cm"
#     conversion: "multiply_by_2.54"

# --- Column filtering ---

# Columns to drop entirely before any processing (site-internal IDs,
# admin tracking columns, etc.). These will not appear in site_raw either.
drop_columns: []

# Regex pattern matching columns to route to the site_raw namespace in
# Flywheel custom info rather than the canonical mapping.
# Use this for raw instrument item scores or other non-canonical data
# you want to preserve but not treat as canonical fields.
site_raw_pattern: null
# Example:  "^(gl1|gs1)"   # routes all GSED item-level columns to site_raw

# Prefix used when storing site_raw fields in Flywheel custom info.
# Stored as:  custom_info["site_raw"]["<column_name>"]
site_raw_prefix: "site_raw"
```

### Key design decisions

| Decision | Rationale |
|---|---|
| YAML over JSON | Human-readable; site data managers can edit directly without tooling |
| Config as gear input (not hardcoded) | Sites differ; config is data not code |
| `variable_map` is canonical→site direction | Site must look up their own column names; canonical names are the stable reference |
| Constants allowed as values in `variable_map` | Avoids needing a CSV column when a value is the same for every row (e.g. country) |
| `drop_columns` is explicit, not implicit | Prevents accidental data loss; if a column is not dropped or mapped it goes to `site_raw` or triggers a warning |
| `site_raw_pattern` regex | Efficiently handles instruments with hundreds of item-level columns (e.g. GSED) without listing each one |

### Workflow for v2 site onboarding

1. **Admin runs the gear (Run 1)** — generates the blank template CSV for the project
2. **Admin also provides the site config template** (`utils/site_config_template.yaml`) to the site
3. **Site data manager** fills in `variable_map`, `value_map`, `unit_map`, `id_field`, `session_match` based on their data dictionary
4. **Site uploads** their raw CSV + completed site config as gear inputs
5. **Gear (Run 2)** loads the site config, applies it during reconciliation, writes canonical fields to Flywheel, routes unknowns to `site_raw`, produces reconciliation report
6. **Admin reviews** reconciliation report; if any columns are ambiguous or unmapped they update the site config and re-run

### Loading precedence

1. Gear input named `site_config` (highest priority)
2. Flywheel project attachment named `site_config.yaml`
3. No config → v1 fallback (CSV must use canonical column names)

---

## Design principles for v2 code

- **Keep canonical schema stable** — `cde_template.yaml` is the single source of truth for field names, types, and domains. Do not add site-specific fields to it.
- **Separate concerns** — parsing/harmonisation should be independent of Flywheel I/O. Write unit-testable harmonisation logic in a new `app/harmonise.py` module.
- **Site config is data, not code** — transforms and mappings live in YAML/JSON config files, not in Python logic.
- **Reconciliation report is mandatory** — every run 2 must produce one, even if all sessions match perfectly.
- **Python 3.11** — the gear runs on Python 3.11.6 (see `manifest.json`). Avoid 3.12+ syntax.
- **No silent data loss** — if a row cannot be matched, it must appear in the reconciliation report. Never silently skip.

---

## Development priorities (suggested order)

1. **Reconciliation report** — highest impact, lowest risk; add to existing run_2 without changing matching logic
2. **Alias expansion** — extend `old_new_harmonization.yaml` to cover common site column name variants; test against real site CSVs in `sanityCheck/`
3. **ID normalisation** — configurable transform applied to subject labels before matching
4. **Date-based session matching** — new matching mode activated by site config
5. **Unit conversion** — conversion rules in config; apply in `cast_metadata_fields()`
6. **Site config loading** — load per-project YAML from Flywheel project attachments or gear input
7. **Category B variable storage** — store unknowns under `site_raw` namespace
8. **REDCap API input** — alternative to CSV upload

---

## Reference data files (`.github/`)

Two CSV files in `.github/` ground the v2 design in real data. Consult them when working on variable mapping, alias expansion, or the site config schema.

---

### `final_agreed_columns.csv` — the agreed cross-site canonical column set

This is the **full set of columns** that the UNITY consortium has agreed to harmonise across all sites (464 columns total). It is the authoritative source for what should ultimately live in Flywheel session custom info.

**Current coverage gap:** `cde_template.yaml` only captures 83 of these 464 columns. The remaining 381 fall into distinct groups:

| Group | Columns | Notes |
|---|---|---|
| `RA_*` | 243 | FreeSurfer regional volumes, cortical thickness, surface area — output of analysis gears, **not collected at site** |
| `ss_*` | 42 | SynthSeg subcortical volumes — analysis gear output |
| `sc_*` | 14 | Subcortical volumes (alternate pipeline) — analysis gear output |
| `MM_*` | 21 | MorphoMetric measures — analysis gear output |
| `eeg_*` / `power_*` / `alpha_*` / `theta_*` / `high_*` | ~20 | EEG power spectra — analysis gear output |
| `HC_*` | 2 | Normalised white matter / cortical volume — analysis gear output |
| WPPSI scores | 13 | `wppsi_FSIQ`, `wppsi_VCI`, `wppsi_VSI`, etc. — **needs adding to `cde_template.yaml`** |
| WISC scores | 12 | `wisc_FSIQ`, `wisc_VCI`, `wisc_VSI`, etc. — **needs adding to `cde_template.yaml`** |
| AAB scores | 2 | `aab_lwrScaled`, `aab_mcScaled` — **needs adding to `cde_template.yaml`** |
| WHO z-scores | 5 | `WAZ`, `HAZ`, `WHZ`, `HCZ`, `BMIZ` — **needs adding to `cde_template.yaml`** |
| Nutritional status | 4 | `CurrentlyStunted`, `CurrentlyWasted`, `EverStunted`, `EverWasted` — bool flags, **needs adding** |
| QC flags | 5 | `is_MM_outlier`, `is_RA_outlier`, `is_duplicate`, `pass_amygdala`, `zero_count` — analysis QC |
| `MAX_*` | 8 | Derived max-value summaries (e.g. `MAX_gsed_LongForm_DAZScore`) |
| Other | misc | `CohortName`, `SubCohort_Group`, `StudyID`, `UniqueStudyID`, `timepoint`, `occurenceD`, `childTimepointHC_MRI_cm` |

**Important design note:** The `RA_*`, `ss_*`, `sc_*`, `MM_*`, `eeg_*`, and `HC_*` groups are populated by downstream analysis gears (FreeSurfer, SynthSeg, MorphoMetric, EEG pipeline), **not** by this gear. This gear only handles clinically-collected demographic/anthropometric/cognitive data. Do not add analysis-pipeline columns to `cde_template.yaml`.

**Action items for `cde_template.yaml`:**
- Add a `Cognitive_v2` or extend `Cognitive` with WPPSI and WISC score fields
- Add a `Anthropometry_derived` section for WHO z-scores (WAZ, HAZ, WHZ, HCZ, BMIZ) and nutritional status flags
- Add `childTimepointHC_MRI_cm` to Demographics (it is already used in v1 harmonization)

**Casing aliases already handled:** `CohortLocation_city`, `CohortLocation_country`, `MaternalEducation_HHS`, `MaternalEducation_schoolingYears`, `timepointFamilySize` are all present in `old_new_harmonization.yaml` under their old-casing forms.

---

### `unity_final_Pakistan.csv` — real site upload from REMIND Pakistan cohort

This is a real export from the Pakistan site (REMIND study), with 352 columns and one data row. It illustrates exactly what a site will actually upload in v2.

**ID and session matching fields:**
| Pakistan column | Role | v2 site config key |
|---|---|---|
| `infantid` | Subject identifier | `id_field: "infantid"` |
| `scan_date` | Date of MRI scan (format `%d/%m/%Y`) | `session_date_field: "scan_date"` |
| `visit` | Timepoint label (e.g. `"12 month"`) | maps to `studyTimepoint` |
| `site` | Always `"Pakistan"` | hardcoded constant in config |

**Category A — already in `old_new_harmonization.yaml` (auto-mapped today):**
```
birth_weight_kg       → childBirthWeight_kgs
gestational_age_weeks → childGestation_weeks
num_children_in_household → timepoint_otherChildrenLivingWithChild
birth_length_cm       → childBirthLength_cm
birth_hc_cm           → childBirthHC_cm
country_of_birth      → childCountryOfBirth
```

**Category A — new aliases to add to `old_new_harmonization.yaml`:**
```
age_scan_days         → childTimepointAge_days
length                → childTimepointHeight_cm   (infant length = height)
hc_cm                 → childTimepointHC_measured_cm
length_for_age_zscore → HAZ
weight_for_length_zscore → WHZ
weight_for_age_zscore → WAZ
hc_for_age_zscore     → HCZ
mat_age               → maternalAgeAtChildBirth_years
school_yrs            → maternalEducation_schoolingYears
household_size        → timepoint_FamilySize
daz_lf                → gsed_LongForm_DAZScore
daz_sf                → gsed_ShortForm_DAZScore
```

**Category A — needs transform (site config `value_map`):**
```
male_child  → childBiologicalSex   (transform: "yes" → "Male", "no" → "Female")
```

**Category C — ambiguous (warn, do not auto-map):**
```
weight   Could be childTimepointWeight_kgs OR childBirthWeight_kgs
         Context: appears in scan-visit anthropometry block, so likely scan weight.
         Require explicit mapping in site config to resolve.
```

**Category A — new canonical fields needed before these can be mapped:**
```
dob          → date of birth (not currently in cde_template.yaml)
dscore_lf    → GSED D-score long form (companion to daz_lf)
dscore_sf    → GSED D-score short form
```

**Category B — store as `site_raw.*` or discard:**
- **ID fields:** `site`, `momid`, `pregid`, `study_id` — site internal IDs, not needed in Flywheel
- **Scan admin:** `REMIND_ENROLLMENT_STATUS_TEXT`, `Scan_attempted_*`, `Scan_outcome_*`, `Success_type_*`, `diff_anthro_scan`
- **GSED item-level data:** 294 columns (`gl1gmd*`, `gl1lgd*`, `gl1fmd*`, `gs1*`) — raw item scores; summary DAZ scores are canonical
- **Other site-specific:** `agedays_gsed_lf`, `date_assessment_gsed_lf/sf`, birth z-scores (`birth_length_for_age_zscore` etc.), `smoke`, `chew_tobacco`, `chew_betelnut`, `drink`, `gravidity`, `parity`, `birth_setting`, `educated`

**Example v2 site config YAML for Pakistan:**
```yaml
# site_config_pakistan.yaml
id_field: "infantid"
session_match: "date"
session_date_field: "scan_date"
session_date_format: "%d/%m/%Y"
session_date_tolerance_days: 3
variable_map:
  cohortLocation_country: "Pakistan"   # hardcoded constant
  studyTimepoint: "visit"
  childBiologicalSex: "male_child"
value_map:
  childBiologicalSex:
    "yes": "Male"
    "no": "Female"
drop_columns:
  - "momid"
  - "pregid"
  - "study_id"
  - "REMIND_ENROLLMENT_STATUS_TEXT"
  - "Scan_attempted_3M_overall"
  - "Scan_outcome_3M"
  - "Success_type_3M"
  - "Scan_attempted_12M_overall"
  - "Scan_outcome_12M"
  - "Success_type_12M"
site_raw_prefix: "site_raw"   # store Category B vars here
site_raw_pattern: "^(gl1|gs1)"   # columns matching this regex → site_raw
```

---

## Testing

- Tests live in `tests/`. Use `conftest.py` fixtures and the mock gear data in `tests/gears/`.
- `sanityCheck/` contains real-world CSVs that can be used for integration testing of the harmonisation engine.
- `.github/unity_final_Pakistan.csv` is the primary integration test fixture for the harmonisation engine.
- Run tests with: `pytest tests/`
- The `dry_run` flag should be fully respected in v2 — no Flywheel writes when set.
- **Note:** existing tests in `tests/` call an older API signature for `load_inputs` and `run_second_stage_with_inputs` and are currently broken. They need rewriting for v2.

---

## v2 Implementation Status

### Implemented

| Feature | File |
|---|---|
| `variable_map` — rename column or inject scalar constant | `run_2.apply_site_config` |
| `value_map` — remap cell values to canonical vocabulary | `run_2.apply_site_config` |
| `unit_map` — `multiply_by_X` unit conversion | `run_2.apply_site_config` |
| `drop_columns` — remove admin/internal columns before processing | `run_2.apply_site_config` |
| `id_field` — rename site subject-ID column to `subject_id` | `run_2.apply_site_config` |
| `site_raw_pattern` (also accepts `gsed_item_pattern`) — regex routes matched columns to `site_raw.*` | `run_2.apply_site_config` |
| Dedup guard — site_raw cols that are also canonical are never duplicated | `run_2` |
| `store_site_raw` gear config — gate on writing `site_raw.*` to session.info | `manifest.json`, `run_2` |
| Only filled (non-null/non-empty) values written | `run_2.process_row` |
| Legacy column harmonisation via `old_new_harmonization.yaml` | `run_2` |
| Reconciliation report (`reconciliation_report.csv`) — per-session audit of written, empty, pre-existing, site_raw fields | `run_2` |
| `download_site_config_template` gear config — outputs `site_config_template.yaml` on Run 1 | `run_1`, `manifest.json` |
| v1 fallback — no site config needed if CSV uses canonical column names | `run_2` |
| 6-section canonical schema (Demographics, SES, Cognitive, Clinical, Derived, SiteRaw) | `cde_template.yaml` |

### Not yet implemented (open gaps)

| Gap | Notes |
|---|---|
| **Date-based session matching** (`session_match: "date"`) | ✅ Implemented — parses `session_date_field` using `session_date_format`, matches within `session_date_tolerance_days`. Ambiguous (multiple matches) and not-found cases are captured in the reconciliation report. |
| **`id_transform`** | Intentionally not implemented. Subject ID values must exactly match Flywheel subject labels. Sites should reconcile labels in Flywheel or in their CSV before running. |
| **`session_id` not required when `session_match` ≠ `"label"`** | ✅ Fixed — required-columns check is now conditional on `session_match` mode. |
| **`subject_only` session matching** | ✅ Implemented — uses the subject's single session; returns `ambiguous` status if subject has >1 session. |
| **Flywheel-only sessions in reconciliation report** | Report covers only uploaded CSV rows. Sessions in Flywheel with no CSV row are not flagged as unmatched. |
| **`dry_run` respected in Run 2** | Flag is parsed but never passed to `run_second_stage_with_inputs`. Writes always happen. |
| **Category C (ambiguous) column detection** | No logic to detect and warn on short/ambiguous column names (e.g. `weight`). |
| **`app/harmonise.py` module** | Unit-testable harmonisation logic still embedded in `run_2.py`. Should be separated for testability. |
