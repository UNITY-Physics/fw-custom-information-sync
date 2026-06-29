"""Second run of gear with inputs and doing renaming"""

import logging
import re
import csv
import ast
import yaml
import sys
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from utils.clean_session_info import clean_session

log = logging.getLogger(__name__)


import pandas as pd
import ast
import flywheel

from concurrent.futures import ThreadPoolExecutor, as_completed

# Date formats tried when parsing session labels (order = priority)
# Includes Flywheel's DICOM-derived label format (YYYY-MM-DD_HH_MM_SS)
_LABEL_DATE_FORMATS = [
    '%Y-%m-%d_%H_%M_%S',  # Flywheel DICOM label: 2026-03-30_15_41_04
    '%Y-%m-%dT%H:%M:%S',  # ISO datetime: 2026-03-30T15:41:04
    '%Y-%m-%d',           # ISO date: 2024-01-01
    '%Y/%m/%d',           # 2024/12/01
    '%d/%m/%Y',           # 01/06/2025
    '%d/%m/%y',           # 01/06/25  (Excel UK 2-digit year)
    '%m/%d/%Y',           # 06/01/2025
    '%m/%d/%y',           # 06/01/25  (Excel US 2-digit year)
    '%d-%m-%Y',           # 01-06-2025
    '%d-%m-%y',           # 01-06-25
]


def _session_date_for_matching(session_obj, primary_format=None):
    """Return the best available date for a Flywheel session.

    Priority:
    1) session timestamp date
    2) session label parsed as date using configured + fallback formats
    """
    if session_obj.timestamp:
        try:
            return session_obj.timestamp.date(), 'timestamp'
        except Exception:
            pass

    label_date = _parse_label_as_date(session_obj.label, primary_format)
    if label_date:
        return label_date, 'label'

    return None, None


def _derive_row_status(match_status, additional_non_imaging_sessions=False):
    """Map legacy match_status text to a stable row_status enum."""
    if match_status == 'non_imaging_created':
        return 'non_imaging_created'
    if match_status == 'non_imaging_updated':
        return 'non_imaging_updated'
    if match_status == 'non_imaging_blocked_near_imaging':
        return 'non_imaging_blocked_near_imaging'
    if match_status == 'updated':
        return 'imaging_matched'
    if isinstance(match_status, str) and match_status.startswith('ambiguous:'):
        return 'imaging_ambiguous'
    if isinstance(match_status, str) and match_status.startswith('not_found'):
        if additional_non_imaging_sessions:
            return 'non_imaging_ineligible'
        return 'imaging_not_found'
    if isinstance(match_status, str) and match_status.startswith('error:'):
        return 'invalid_row'
    return 'invalid_row'


def _normalize_str(value):
    if value is None:
        return ''
    return str(value).strip()


def _sanitize_label_token(value, default='unknown'):
    token = _normalize_str(value).lower()
    token = re.sub(r'[^a-z0-9]+', '-', token).strip('-')
    return token or default


def _to_bool_with_truthy(value, truthy_values=None):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    norm = _normalize_str(value).lower()
    truthy = {'1', 'true', 'yes', 'y'}
    if truthy_values:
        truthy = {str(v).strip().lower() for v in truthy_values}
    return norm in truthy


def _build_source_row_uid(project_label, subject_id, visit_date_iso, visit_type):
    """Build deterministic row UID for idempotent non-imaging upserts."""
    payload = '|'.join([
        _normalize_str(project_label),
        _normalize_str(subject_id),
        _normalize_str(visit_date_iso),
        _normalize_str(visit_type),
    ])
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]


def _is_non_imaging_session(session_obj):
    """Detect whether a session is tagged as non-imaging."""
    try:
        info = session_obj.info or {}
    except Exception:
        info = {}
    return _normalize_str(info.get('session_kind')).lower() == 'non_imaging'


def _find_non_imaging_session_by_uid(sessions, source_row_uid):
    """Return existing non-imaging session matching source_row_uid if present."""
    for session in sessions:
        if not _is_non_imaging_session(session):
            continue
        info = session.info or {}
        if _normalize_str(info.get('source_row_uid')) == source_row_uid:
            return session
    return None


def _find_non_imaging_session_by_label(sessions, prefix, visit_type, visit_date):
    """Fallback dedup: find an existing NI session by label pattern.

    Used when source_row_uid was not written in a prior run (e.g. sessions created
    before UID tracking was implemented).  Matches the base label and any
    collision-suffixed variants (NI-visit-20260401, NI-visit-20260401-2, …).
    After a match is updated, write_row_values_to_session will stamp the UID so
    future runs use the faster UID path instead.
    """
    date_token = visit_date.strftime('%Y%m%d')
    visit_token = _sanitize_label_token(visit_type)
    base = f"{prefix}-{visit_token}-{date_token}"
    pattern = re.compile(rf'^{re.escape(base)}(-\d+)?$')
    for session in sessions:
        if not _is_non_imaging_session(session):
            continue
        if pattern.match(session.label or ''):
            return session
    return None


def _derive_non_imaging_label(prefix, visit_type, visit_date, existing_labels):
    """Create a deterministic, collision-safe non-imaging session label."""
    date_token = visit_date.strftime('%Y%m%d')
    visit_token = _sanitize_label_token(visit_type)
    base = f"{prefix}-{visit_token}-{date_token}"
    if base not in existing_labels:
        return base
    counter = 2
    while f"{base}-{counter}" in existing_labels:
        counter += 1
    return f"{base}-{counter}"

def _parse_label_as_date(label, primary_format=None):
    """Try to parse a session label string as a date.
    Tries primary_format first (if given), then common fallback formats.
    Returns a date object, or None if nothing matched.
    """
    formats = []
    if primary_format:
        formats.append(primary_format)
    for fmt in _LABEL_DATE_FORMATS:
        if fmt not in formats:
            formats.append(fmt)
    label = (label or '').strip()
    for fmt in formats:
        try:
            return datetime.strptime(label, fmt).date()
        except ValueError:
            continue
    return None


def _parse_csv_date(date_str, primary_format):
    """Parse a date string from a site CSV.
    Tries primary_format first, then derives a 2-digit-year variant,
    then other common formats.
    Returns (date, format_used) or (None, None) if nothing matched.
    """
    fallbacks = [primary_format]
    # Derive 2-digit-year variant of the configured format (e.g. %d/%m/%Y -> %d/%m/%y)
    two_digit = primary_format.replace('%Y', '%y')
    if two_digit != primary_format and two_digit not in fallbacks:
        fallbacks.append(two_digit)
    # Additional common formats
    for fmt in [
        '%Y-%m-%d_%H_%M_%S',  # Flywheel DICOM label: 2026-03-30_15_41_04
        '%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y',
        '%m/%d/%Y', '%m/%d/%y', '%d-%m-%Y', '%d-%m-%y', '%Y/%m/%d',
    ]:
        if fmt not in fallbacks:
            fallbacks.append(fmt)
    date_str = (date_str or '').strip()
    for fmt in fallbacks:
        try:
            return datetime.strptime(date_str, fmt).date(), fmt
        except ValueError:
            continue
    return None, None

def parse_maybe_list(val):
    val = str(val).strip()
    try:
        parsed = ast.literal_eval(val)
        if isinstance(parsed, list):
            return [item.strip() for item in parsed]
        else:
            return [str(parsed).strip()]
    except (ValueError, SyntaxError):
        if "," in val:
            return [item.strip() for item in val.strip("[]").split(",")]
        else:
            return [val]

def smart_fallback_parser(val):
    """Fallback parser for unknown columns."""
    if pd.isna(val):
        return None
    val_str = str(val).strip().lower()
    try:
        # Check boolean
        if val_str in ["true", "false", "yes", "no"]:
            return val_str in ["true", "yes"]
        # Try int
        if "." not in val_str and val_str.isdigit():
            return int(val_str)
        # Try float
        return float(val_str)
    except:
        pass
    # Try list
    try:
        maybe_list = parse_maybe_list(val)
        if len(maybe_list) > 1:
            return maybe_list
    except:
        pass
    return val  # return as-is string if all else fails

def parse_value(val, target_type):
    try:
        if pd.isna(val):
            return None
        if target_type == bool:
            return _to_bool_with_truthy(val)
        elif target_type == list:
            return parse_maybe_list(val)
        elif target_type == int:
            return int(float(val))
        elif target_type == float:
            return float(val)
        elif target_type == str:
            return str(val).strip()
        else:
            return val
    except (ValueError, TypeError):
        return None

def _id_to_str(x):
    """Convert an identifier cell to a clean string.

    Pandas reads integer-valued CSV columns as float (e.g. 1227 → 1227.0).
    str(1227.0) would give "1227.0", which won't match a Flywheel label of "1227".
    This helper strips the spurious .0 suffix for whole-number values.
    """
    if pd.isna(x):
        return None
    s = str(x).strip()
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s


def cast_metadata_fields(df, template, field_types=None):
    identifier_columns = {'group_id', 'project_id', 'subject_id', 'session_id'}
    _type_map = {'float': float, 'bool': bool, 'str': str, 'list': list, 'int': int}
    for col in df.columns:
        if col in identifier_columns:
            df[col] = df[col].apply(_id_to_str)
            continue
        if field_types and col in field_types:
            # Explicit type declaration takes priority over default-value inference.
            # Required for fields whose default is None but type is not str (e.g. z-scores).
            target_type = _type_map.get(field_types[col], str)
            df[col] = df[col].apply(lambda x: parse_value(x, target_type))
        elif col in template:
            example = template[col]
            if isinstance(example, bool):
                target_type = bool
            elif isinstance(example, int):
                target_type = float
            elif isinstance(example, float):
                target_type = float
            elif isinstance(example, list):
                target_type = list
            elif isinstance(example, str) or example is None:
                target_type = str
            else:
                continue
            df[col] = df[col].apply(lambda x: parse_value(x, target_type))
        else:
            # Unknown column: use smart fallback
            df[col] = df[col].apply(smart_fallback_parser)

    return df


def apply_site_config(df, site_config):
    """Apply site config transformations to a DataFrame before canonical matching.

    Applies (in order): drop_columns, id_field rename, variable_map (column rename),
    constant_map (site-level constant injection), value_map (cell value remap),
    unit_map (numeric conversion), and identifies site_raw columns via site_raw_pattern regex.

    Args:
        df (pd.DataFrame): raw input CSV as DataFrame
        site_config (dict | None): parsed site config YAML, or None for v1 fallback

    Returns:
        df (pd.DataFrame): transformed DataFrame
        site_raw_cols (set): column names to route to site_raw namespace
    """
    if not site_config:
        return df, set()

    # 1. Drop internal/admin columns entirely
    drop = site_config.get('drop_columns') or []
    df = df.drop(columns=[c for c in drop if c in df.columns], errors='ignore')

    # 2. Map site's subject-ID column to the canonical 'subject_id' column name.
    # Copy (not rename) so the original id_field column is still available for variable_map
    # entries that also need to read from it (e.g. StudyID and UniqueStudyID both from study_id).
    id_field = site_config.get('id_field')
    id_field_copied = False
    if id_field and id_field in df.columns and 'subject_id' not in df.columns:
        df['subject_id'] = df[id_field]
        id_field_copied = True

    # 3. variable_map: canonical_field -> site_column
    # Uses copy semantics with deferred source-column drop so that the same source column
    # can map to multiple canonical targets (e.g. study_id -> StudyID and UniqueStudyID).
    variable_map = site_config.get('variable_map') or {}
    mapped_sources = set()
    for canonical, source in variable_map.items():
        if source is None:
            continue
        if isinstance(source, str) and source in df.columns:
            df[canonical] = df[source]  # copy; source dropped after loop
            if source != canonical:
                mapped_sources.add(source)
        elif isinstance(source, str):
            log.warning(
                "variable_map: source column '%s' not found in CSV for canonical field '%s' — "
                "check for a typo in the column name.", source, canonical
            )
        else:
            df[canonical] = source  # scalar constant — prefer constant_map for new configs
    # Drop source columns that were mapped away (deferred to allow same-source multi-target).
    df = df.drop(columns=[c for c in mapped_sources if c in df.columns], errors='ignore')
    # Only drop id_field if we copied it to subject_id — leave it alone when subject_id
    # was already present (the copy was skipped and id_field may still be needed downstream).
    if id_field_copied and id_field in df.columns and id_field != 'subject_id':
        df = df.drop(columns=[id_field], errors='ignore')

    # 3b. constant_map: canonical_field -> scalar  (same value for every row)
    # Use for site-level fields that don't vary per participant: country, city,
    # scanner field strength, cohort name, etc.
    constant_map = site_config.get('constant_map') or {}
    for canonical, value in constant_map.items():
        if value is None:
            continue
        if canonical in variable_map and canonical in df.columns:
            log.warning(
                "constant_map: '%s' is also in variable_map — constant value '%s' will overwrite "
                "per-row CSV values.", canonical, value
            )
        df[canonical] = value

    # 4. value_map: remap raw cell values to canonical controlled-vocabulary values
    value_map = site_config.get('value_map') or {}
    for field, mapping in value_map.items():
        if field not in df.columns:
            log.warning(
                "value_map: field '%s' not found in CSV (after variable_map renames) — "
                "skipping remaps. Ensure variable_map and value_map use the same canonical field name.",
                field
            )
            continue
        df[field] = df[field].apply(
            lambda x, m=mapping: m.get(str(x), x) if pd.notna(x) else x
        )

    # 5. unit_map: numeric unit conversion before type casting
    unit_map = site_config.get('unit_map') or {}
    for field, conv in unit_map.items():
        if field not in df.columns:
            log.warning(
                "unit_map: field '%s' not found in CSV (after variable_map renames) — "
                "skipping conversion. Ensure variable_map and unit_map use the same "
                "canonical field name.", field
            )
            continue
        conversion = conv.get('conversion', '')
        if conversion.startswith('multiply_by_'):
            factor = float(conversion.replace('multiply_by_', ''))
            df[field] = pd.to_numeric(df[field], errors='coerce') * factor

    # 6. Identify site_raw columns via regex pattern (routed to site_raw namespace)
    # Accept both 'site_raw_pattern' and legacy 'gsed_item_pattern' key names
    site_raw_pattern = site_config.get('site_raw_pattern') or site_config.get('gsed_item_pattern')
    site_raw_cols = set()
    if site_raw_pattern:
        pattern = re.compile(site_raw_pattern)
        site_raw_cols = {c for c in df.columns if pattern.match(c)}

    return df, site_raw_cols


def run_second_stage_with_inputs(
    api_key, run_level, df, site_config_path=None, store_site_raw=False,
    dry_run=False, additional_non_imaging_sessions=False,
    non_imaging_label_prefix='NI',
    non_imaging_block_if_near_imaging_days=1,
    non_imaging_require_visit_marker=True,
    non_imaging_allow_within_imaging_window_if_explicit=False,
    context_group=None, context_project_label=None,
):
    """Since input csv files were provided, update labels where new ones were given.

    Args:
        api_key (str): Flywheel API key
        run_level (str): the level at which the gear is running: 'project' or 'subject'
        df (str | Path): path to the session_info CSV
        site_config_path (str | Path | None): path to the site config YAML, or None for v1 fallback
        dry_run (bool): when True, do not write any session info updates
        additional_non_imaging_sessions (bool): enable non-imaging upsert flow for
            unmatched rows after imaging matching fails.
        non_imaging_label_prefix (str): prefix used for created non-imaging labels.
        non_imaging_block_if_near_imaging_days (int): block non-imaging creation when
            candidate date is within this many days of an imaging session.
        non_imaging_require_visit_marker (bool): require visit marker evidence before
            non-imaging creation is allowed.
        non_imaging_allow_within_imaging_window_if_explicit (bool): allow creation
            within the near-imaging window only when explicit force-create is set.
        context_group (str): Flywheel group label from the gear's destination hierarchy
        context_project_label (str): Flywheel project label from the gear's destination hierarchy

    Returns:
        int: 0 if all is well, 1 if there is an error
    """

    fw = flywheel.Client(api_key=api_key)

    # Pre-load the destination project once (avoids per-row Flywheel API calls)
    if not context_group or not context_project_label:
        print("Error: gear context group/project not provided. Exiting.")
        sys.exit(1)
    _group_obj = fw.lookup(context_group)
    project_obj = next(
        (c for c in _group_obj.projects() if c.label == context_project_label), None
    )
    if project_obj is None:
        print(f"Error: project {context_group}/{context_project_label} not found. Exiting.")
        sys.exit(1)
    project_obj = project_obj.reload()

    with open(f"/flywheel/v0/utils/cde_template.yaml", 'r') as file:
        metadata = yaml.safe_load(file)

    demographics_cde = metadata['Demographics']
    ses_cde = metadata['SES']
    cognitive_cde = metadata['Cognitive']
    clinical_cde = metadata.get('Clinical', {})
    derived_cde = metadata.get('Derived', {})

    metadata_template = demographics_cde | ses_cde | cognitive_cde | clinical_cde | derived_cde
    canonical_fields = set(metadata_template.keys())
    field_types = metadata.get('FieldTypes') or {}

    with open("/flywheel/v0/utils/old_new_harmonization.yaml", 'r') as file:
        harmonization_map = yaml.safe_load(file)

    # Load site config if provided
    site_config = None
    if site_config_path:
        with open(site_config_path, 'r') as f:
            try:
                site_config = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                print(
                    f"Failed to parse site config YAML: {exc}\n"
                    "Common cause: using '{{' for multi-line mappings (value_map, unit_map).\n"
                    "Use block style (indented lines) instead of flow style ({{...}}).\n"
                    "See the examples in site_config_template.yaml.\n"
                    "Exiting."
                )
                sys.exit(1)
        print(f"Loaded site config from {site_config_path}")

    print(f"Reading CSV at {run_level} level")
    print(f"Reading CSV file {df}")

    csv_data = pd.read_csv(df, encoding='utf-8', encoding_errors='replace')

    # Apply site config transformations before any required-column checks
    csv_data, site_raw_cols = apply_site_config(csv_data, site_config)
    # Exclude any site_raw candidates that ended up as canonical names (dedup guard)
    site_raw_cols = site_raw_cols - canonical_fields
    site_raw_prefix = (site_config or {}).get('site_raw_prefix', 'site_raw')

    # Session matching mode from site config
    session_match_mode = (site_config or {}).get('session_match', 'label')
    session_date_field = (site_config or {}).get('session_date_field')
    session_date_format = (site_config or {}).get('session_date_format', '%Y-%m-%d')
    session_date_tolerance = timedelta(
        days=int((site_config or {}).get('session_date_tolerance_days', 0))
    )

    # Non-imaging settings (site-config keys override gear-level defaults)
    non_img_date_field = (site_config or {}).get('non_imaging_date_field') or session_date_field
    non_img_date_format = (site_config or {}).get('non_imaging_date_format', session_date_format)
    non_img_visit_type_field = (site_config or {}).get('non_imaging_visit_type_field')
    non_img_visit_type_allowlist = [
        _normalize_str(v).lower()
        for v in ((site_config or {}).get('non_imaging_visit_type_allowlist') or [])
        if _normalize_str(v)
    ]
    non_img_marker_fields = [
        _normalize_str(v)
        for v in ((site_config or {}).get('non_imaging_visit_marker_fields') or [])
        if _normalize_str(v)
    ]
    non_img_force_field = (site_config or {}).get('non_imaging_force_create_field')
    non_img_force_values = (site_config or {}).get(
        'non_imaging_force_create_values', ['yes', 'true', '1']
    )
    non_img_include_regex = (site_config or {}).get('non_imaging_include_fields_regex')
    non_img_exclude_regex = (site_config or {}).get('non_imaging_exclude_fields_regex')
    non_img_include_pattern = re.compile(non_img_include_regex) if non_img_include_regex else None
    non_img_exclude_pattern = re.compile(non_img_exclude_regex) if non_img_exclude_regex else None

    # Rename legacy columns
    harmonization_path = Path("/flywheel/v0/utils/old_new_harmonization.yaml")
    if harmonization_path.exists():
        with harmonization_path.open('r') as file:
            harm = yaml.safe_load(file)
        old_key_new_key = harm.get('old_key_new_key', {})
        csv_data.rename(columns=old_key_new_key, inplace=True, errors='ignore')
    else:
        log.info("Skipping legacy column harmonization; old_new_harmonization.yaml not found")

    # Ensure required identifier columns are present (depends on session_match mode)
    # group_id and project_id are never required — the gear uses its destination context
    if session_match_mode == 'date':
        if not session_date_field:
            print("session_match is 'date' but session_date_field is not set in site config. Exiting.")
            sys.exit(1)
        required_columns = {'subject_id', session_date_field}
    elif session_match_mode == 'subject_only':
        required_columns = {'subject_id'}
    else:  # 'label' (default, v1 behaviour)
        required_columns = {'subject_id', 'session_id'}

    missing = required_columns - set(csv_data.columns)
    if missing:
        print(f"Missing required column(s): {', '.join(sorted(missing))}. Exiting.")
        sys.exit(1)

    csv_data = cast_metadata_fields(csv_data, metadata_template, field_types=field_types)

    # Determine which canonical fields are absent from the CSV entirely (same for all rows)
    canonical_not_in_csv = sorted(canonical_fields - set(csv_data.columns))

    def process_row(row_idx, row, replace):
        def finalize_audit(a):
            if not a.get('row_status'):
                a['row_status'] = _derive_row_status(
                    a['match_status'], additional_non_imaging_sessions
                )
            if a['row_status'] == 'imaging_matched' and not a['reason_code']:
                a['reason_code'] = 'ok'
            if a['row_status'] in {'non_imaging_created', 'non_imaging_updated'} and not a['reason_code']:
                a['reason_code'] = 'ok'
            return a

        def non_imaging_field_allowed(field_name):
            if field_name in identifier_cols:
                return False
            if non_img_include_pattern and not non_img_include_pattern.search(field_name):
                return False
            if non_img_exclude_pattern and non_img_exclude_pattern.search(field_name):
                return False
            return True

        def write_row_values_to_session(target_session, is_non_imaging=False):
            target_session = target_session.reload()
            ses_dict = target_session.info
            ses_dict = clean_session(ses_dict, harmonization_map=harmonization_map, defaults_template=metadata_template)
            if not dry_run:
                target_session.replace_info(ses_dict)
                target_session = target_session.reload()
                ses_dict = target_session.info

            audit['pre_existing'] = sorted(
                k for k in canonical_fields if k in ses_dict and ses_dict[k] is not None
            )

            audit['canonical_empty'] = sorted(
                k for k in canonical_fields
                if k in row
                and (
                    row[k] is None
                    or (isinstance(row[k], float) and pd.isna(row[k]))
                    or str(row[k]).strip() == ''
                )
            )

            site_raw_dict = dict(ses_dict.get(site_raw_prefix, {}))
            for key, value in row.items():
                if key in identifier_cols:
                    continue
                if is_non_imaging and not non_imaging_field_allowed(key):
                    continue
                if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == '':
                    continue
                if key in canonical_fields:
                    ses_dict[key] = value
                    audit['fields_written'].append(key)
                else:
                    if store_site_raw:
                        site_raw_dict[key] = value
                        audit['site_raw_written'].append(key)
                    else:
                        audit['unknown_skipped'].append(key)

            if is_non_imaging:
                ses_dict['session_kind'] = 'non_imaging'
                ses_dict['source_system'] = 'custom_information_sync'
                if audit.get('source_row_uid'):
                    ses_dict['source_row_uid'] = audit['source_row_uid']
                if audit.get('source_date_normalized'):
                    ses_dict['visit_date_normalized'] = audit['source_date_normalized']

            if site_raw_dict:
                ses_dict[site_raw_prefix] = site_raw_dict

            audit['fields_written_count'] = len(audit['fields_written'])

            if not dry_run:
                if replace:
                    target_session.replace_info(ses_dict)
                else:
                    target_session.update_info(ses_dict)

        # Exclude identifier and date columns from field writes
        identifier_cols = {'group_id', 'project_id', 'subject_id', 'session_id'}
        if session_date_field:
            identifier_cols.add(session_date_field)
        if non_img_date_field:
            identifier_cols.add(non_img_date_field)

        subject_id = row.get('subject_id')
        session_id = row.get('session_id')  # may be None in date/subject_only modes

        audit = {
            'row_index': row_idx,
            'subject_id': subject_id,
            'session_id': session_id,
            'match_status': 'not_found',
            'match_method': '',
            'row_status': '',
            'reason_code': '',
            'source_date_raw': str(row.get(session_date_field, '')).strip() if session_date_field else '',
            'source_date_normalized': '',
            'candidate_type': 'imaging',
            'matched_session_label': '',
            'matched_session_kind': 'imaging',
            'created_session_label': '',
            'created_session_kind': '',
            'source_row_uid': '',
            'nearest_imaging_session_label': '',
            'nearest_imaging_day_delta': '',
            'dry_run_applied': bool(dry_run),
            'fields_written': [],
            'canonical_empty': [],
            'pre_existing': [],
            'site_raw_written': [],
            'unknown_skipped': [],
            'fields_written_count': 0,
        }

        try:
            subject = next(
                (c for c in project_obj.subjects() if c.label == subject_id), None
            )
            if subject is None:
                audit['match_status'] = f'error: subject {subject_id} not found'
                audit['reason_code'] = 'subject_not_found'
                return finalize_audit(audit)
            subject = subject.reload()
            # Reload each session so .info is populated — list responses from the
            # Flywheel SDK return lightweight objects with empty .info, which would
            # cause _find_non_imaging_session_by_uid to miss existing NI sessions
            # and create duplicates on every run.
            subject_sessions = [s.reload() for s in subject.sessions()]
            imaging_sessions = [s for s in subject_sessions if not _is_non_imaging_session(s)]

            session = None

            # --- Session matching ---
            if session_match_mode == 'date':
                date_str = str(row.get(session_date_field, '')).strip()
                site_date, used_fmt = _parse_csv_date(date_str, session_date_format)
                if site_date is None:
                    audit['match_status'] = (
                        f'error: could not parse date "{date_str}" '
                        f'with configured format "{session_date_format}" '
                        f'or any common fallback format'
                    )
                    audit['reason_code'] = 'date_parse_failed'
                    return finalize_audit(audit)
                audit['source_date_normalized'] = site_date.isoformat()
                fmt_note = f' (fallback fmt: {used_fmt})' if used_fmt != session_date_format else ''
                # Build candidates: match via session.timestamp OR session.label parsed as date.
                # session.timestamp may be null for manually-created sessions;
                # session.label is often a datetime string derived from the DICOM series date.
                seen_ids = set()
                candidates = []
                match_methods = {}
                for s in imaging_sessions:
                    matched = False
                    method = None
                    candidate_date, candidate_method = _session_date_for_matching(
                        s, session_date_format
                    )
                    if candidate_date is not None:
                        delta_days = abs((candidate_date - site_date).days)
                        if (
                            audit['nearest_imaging_day_delta'] == ''
                            or delta_days < audit['nearest_imaging_day_delta']
                        ):
                            audit['nearest_imaging_day_delta'] = delta_days
                            audit['nearest_imaging_session_label'] = s.label
                        if delta_days <= session_date_tolerance.days:
                            matched = True
                            method = candidate_method
                    if matched and s.id not in seen_ids:
                        seen_ids.add(s.id)
                        candidates.append(s)
                        match_methods[s.id] = method
                if len(candidates) == 0:
                    audit['match_status'] = (
                        f'not_found: no session within {session_date_tolerance.days}d '
                        f'of {date_str} (checked timestamp and label)'
                    )
                    if not additional_non_imaging_sessions:
                        audit['reason_code'] = 'no_session_within_tolerance'
                        return finalize_audit(audit)
                    audit['candidate_type'] = 'non_imaging'
                    # Fall through to the shared non-imaging upsert block below (session stays None)
                elif len(candidates) > 1:
                    labels = [s.label for s in candidates]
                    audit['match_status'] = (
                        f'ambiguous: {len(candidates)} sessions match '
                        f'date {date_str}: {labels}'
                    )
                    audit['reason_code'] = 'multiple_date_matches'
                    return finalize_audit(audit)
                else:
                    session = candidates[0]
                    audit['session_id'] = session.label  # record actual FW session label
                    audit['matched_session_label'] = session.label
                    audit['match_method'] = match_methods.get(session.id, 'unknown') + fmt_note

            elif session_match_mode == 'subject_only':
                all_sessions = imaging_sessions
                if len(all_sessions) == 0:
                    audit['match_status'] = 'not_found: subject has no sessions'
                    audit['reason_code'] = 'subject_has_no_sessions'
                    return finalize_audit(audit)
                if len(all_sessions) > 1:
                    labels = [s.label for s in all_sessions]
                    audit['match_status'] = (
                        f'ambiguous: subject has {len(all_sessions)} sessions, '
                        f'use session_match: date to disambiguate: {labels}'
                    )
                    audit['reason_code'] = 'multiple_subject_sessions'
                    return finalize_audit(audit)
                session = all_sessions[0]
                audit['session_id'] = session.label
                audit['matched_session_label'] = session.label

            else:  # 'label' — exact match on Flywheel session label (default / v1)
                session = next(
                    (c for c in imaging_sessions if c.label == session_id), None
                )
                if session:
                    audit['matched_session_label'] = session.label

            if session:
                write_row_values_to_session(session, is_non_imaging=False)
                audit['match_status'] = 'updated'
                audit['row_status'] = 'imaging_matched'
                return finalize_audit(audit)
            else:
                audit['match_status'] = 'not_found'

                if not additional_non_imaging_sessions:
                    audit['reason_code'] = 'session_label_not_found'
                    return finalize_audit(audit)

                # Phase-2 non-imaging upsert flow
                audit['candidate_type'] = 'non_imaging'
                audit['matched_session_kind'] = 'non_imaging'

                if not non_img_date_field or non_img_date_field not in row:
                    audit['reason_code'] = 'missing_non_imaging_date'
                    return finalize_audit(audit)

                non_img_date_raw = _normalize_str(row.get(non_img_date_field))
                audit['source_date_raw'] = non_img_date_raw
                non_img_date, _ = _parse_csv_date(non_img_date_raw, non_img_date_format)
                if non_img_date is None:
                    audit['reason_code'] = 'date_parse_failed'
                    return finalize_audit(audit)
                audit['source_date_normalized'] = non_img_date.isoformat()

                visit_type = ''
                if non_img_visit_type_field:
                    visit_type = _normalize_str(row.get(non_img_visit_type_field))
                if not visit_type:
                    visit_type = _normalize_str(row.get('studyTimepoint'))

                force_create = False
                if non_img_force_field:
                    force_create = _to_bool_with_truthy(
                        row.get(non_img_force_field), non_img_force_values
                    )

                marker_present = any(
                    _normalize_str(row.get(marker_field))
                    for marker_field in non_img_marker_fields
                )
                visit_type_norm = visit_type.lower()
                visit_type_allowed = (
                    (not non_img_visit_type_allowlist)
                    or (visit_type_norm in non_img_visit_type_allowlist)
                )

                has_marker_evidence = (
                    (bool(visit_type) and visit_type_allowed)
                    or marker_present
                    or force_create
                )

                if non_imaging_require_visit_marker and not has_marker_evidence:
                    audit['reason_code'] = 'no_visit_marker'
                    return finalize_audit(audit)

                if non_img_visit_type_allowlist and visit_type and not visit_type_allowed and not force_create:
                    audit['reason_code'] = 'visit_type_not_allowed'
                    return finalize_audit(audit)

                nearest_delta = None
                nearest_label = ''
                for img_session in imaging_sessions:
                    img_date, _ = _session_date_for_matching(img_session, session_date_format)
                    if img_date is None:
                        continue
                    delta = abs((img_date - non_img_date).days)
                    if nearest_delta is None or delta < nearest_delta:
                        nearest_delta = delta
                        nearest_label = img_session.label

                if nearest_delta is not None:
                    audit['nearest_imaging_day_delta'] = nearest_delta
                    audit['nearest_imaging_session_label'] = nearest_label

                within_guard_window = (
                    nearest_delta is not None
                    and nearest_delta <= int(non_imaging_block_if_near_imaging_days)
                )
                allow_override = (
                    non_imaging_allow_within_imaging_window_if_explicit and force_create
                )
                if within_guard_window and not allow_override:
                    audit['match_status'] = 'non_imaging_blocked_near_imaging'
                    audit['reason_code'] = 'near_imaging_guard'
                    return finalize_audit(audit)

                source_row_uid = _build_source_row_uid(
                    context_project_label,
                    subject_id,
                    audit['source_date_normalized'],
                    visit_type,
                )
                audit['source_row_uid'] = source_row_uid

                existing_non_img = _find_non_imaging_session_by_uid(
                    subject_sessions, source_row_uid
                )
                if not existing_non_img:
                    # Fallback: sessions created before UID tracking won't have
                    # source_row_uid in their info — match by label pattern instead.
                    # write_row_values_to_session will stamp the UID so future runs
                    # use the UID path.
                    existing_non_img = _find_non_imaging_session_by_label(
                        subject_sessions, non_imaging_label_prefix, visit_type, non_img_date
                    )
                if existing_non_img:
                    audit['session_id'] = existing_non_img.label
                    audit['matched_session_label'] = existing_non_img.label
                    write_row_values_to_session(existing_non_img, is_non_imaging=True)
                    audit['match_status'] = 'non_imaging_updated'
                    audit['row_status'] = 'non_imaging_updated'
                    return finalize_audit(audit)

                existing_labels = {s.label for s in subject_sessions}
                created_label = _derive_non_imaging_label(
                    non_imaging_label_prefix, visit_type, non_img_date, existing_labels
                )
                audit['created_session_label'] = created_label
                audit['created_session_kind'] = 'non_imaging'

                if dry_run:
                    audit['session_id'] = created_label
                    audit['match_status'] = 'non_imaging_created'
                    audit['row_status'] = 'non_imaging_created'
                    return finalize_audit(audit)

                new_session = subject.add_session({'label': created_label})
                new_session = new_session.reload()
                audit['session_id'] = new_session.label
                write_row_values_to_session(new_session, is_non_imaging=True)
                audit['match_status'] = 'non_imaging_created'
                audit['row_status'] = 'non_imaging_created'
                return finalize_audit(audit)

        except Exception as e:
            audit['match_status'] = f'error: {e}'
            audit['reason_code'] = 'exception'

        return finalize_audit(audit)

    replace = True
    audit_rows = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(process_row, row_idx, row, replace)
            for row_idx, row in csv_data.iterrows()
        ]
        for future in as_completed(futures):
            result = future.result()
            print(f"{result['match_status']}: subject={result['subject_id']} session={result['session_id']}")
            audit_rows.append(result)

    # Write reconciliation / audit CSV
    run_timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    audit_path = "/flywheel/v0/output/reconciliation_report.csv"
    audit_fieldnames = [
        'run_timestamp', 'row_index', 'subject_id', 'session_id', 'match_status', 'match_method',
        'row_status', 'reason_code', 'source_date_raw', 'source_date_normalized',
        'candidate_type', 'matched_session_label', 'matched_session_kind',
        'created_session_label', 'created_session_kind', 'source_row_uid',
        'nearest_imaging_session_label', 'nearest_imaging_day_delta', 'dry_run_applied',
        'fields_written_count', 'fields_written', 'canonical_empty',
        'pre_existing', 'site_raw_written', 'unknown_skipped',
    ]
    with open(audit_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=audit_fieldnames)
        writer.writeheader()
        for r in audit_rows:
            writer.writerow({
                'run_timestamp':      run_timestamp,
                'row_index':          r.get('row_index', ''),
                'subject_id':         r['subject_id'],
                'session_id':         r['session_id'],
                'match_status':       r['match_status'],
                'match_method':       r.get('match_method', ''),
                'row_status':         r.get('row_status', ''),
                'reason_code':        r.get('reason_code', ''),
                'source_date_raw':    r.get('source_date_raw', ''),
                'source_date_normalized': r.get('source_date_normalized', ''),
                'candidate_type':     r.get('candidate_type', ''),
                'matched_session_label': r.get('matched_session_label', ''),
                'matched_session_kind': r.get('matched_session_kind', ''),
                'created_session_label': r.get('created_session_label', ''),
                'created_session_kind': r.get('created_session_kind', ''),
                'source_row_uid':     r.get('source_row_uid', ''),
                'nearest_imaging_session_label': r.get('nearest_imaging_session_label', ''),
                'nearest_imaging_day_delta': r.get('nearest_imaging_day_delta', ''),
                'dry_run_applied':    r.get('dry_run_applied', False),
                'fields_written_count': r.get('fields_written_count', 0),
                'fields_written':     '; '.join(r['fields_written']),
                'canonical_empty':    '; '.join(r['canonical_empty']),
                'pre_existing':       '; '.join(r['pre_existing']),
                'site_raw_written':   '; '.join(r['site_raw_written']),
                'unknown_skipped':    '; '.join(r.get('unknown_skipped', [])),
            })
    print(f"Reconciliation report written to {audit_path}")

    # Write canonical fields absent from the uploaded CSV as a separate summary
    missing_path = "/flywheel/v0/output/canonical_not_in_csv.csv"
    with open(missing_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['canonical_field'])
        for field in canonical_not_in_csv:
            writer.writerow([field])
    print(f"Canonical fields not in CSV written to {missing_path} ({len(canonical_not_in_csv)} fields)")
    print("All sessions updated from CSV.")

    return 0  # all is well
