"""Second run of gear with inputs and doing renaming"""

import logging
import re
import csv
import ast
import yaml
import sys
from datetime import datetime, timedelta
from pathlib import Path
from utils.clean_session_info import clean_session

log = logging.getLogger(__name__)


import pandas as pd
import ast
import flywheel

from concurrent.futures import ThreadPoolExecutor, as_completed

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
            return str(val).strip().lower() in ["true", "yes"]
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

def cast_metadata_fields(df, template):
    identifier_columns = {'group_id', 'project_id', 'subject_id', 'session_id'}
    for col in df.columns:
        if col in identifier_columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x).strip())
            continue
        if col in template:
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
            # print(col, target_type)
        else:
            # Unknown column: use smart fallback
            df[col] = df[col].apply(smart_fallback_parser)
    
    return df


def apply_site_config(df, site_config):
    """Apply site config transformations to a DataFrame before canonical matching.

    Applies (in order): drop_columns, id_field rename, variable_map (column rename or
    constant injection), value_map (cell value remap), unit_map (numeric conversion),
    and identifies site_raw columns via site_raw_pattern regex.

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

    # 2. Map site's subject-ID column to the canonical 'subject_id' column name
    id_field = site_config.get('id_field')
    if id_field and id_field in df.columns and 'subject_id' not in df.columns:
        df = df.rename(columns={id_field: 'subject_id'})

    # 3. variable_map: canonical_field -> site_column_or_constant
    variable_map = site_config.get('variable_map') or {}
    for canonical, source in variable_map.items():
        if source is None:
            continue
        if isinstance(source, str) and source in df.columns:
            # rename the site column to the canonical name
            df = df.rename(columns={source: canonical})
        else:
            # scalar constant: add a column with the same value for every row
            df[canonical] = source

    # 4. value_map: remap raw cell values to canonical controlled-vocabulary values
    value_map = site_config.get('value_map') or {}
    for field, mapping in value_map.items():
        if field in df.columns:
            df[field] = df[field].apply(
                lambda x, m=mapping: m.get(str(x), x) if pd.notna(x) else x
            )

    # 5. unit_map: numeric unit conversion before type casting
    unit_map = site_config.get('unit_map') or {}
    for field, conv in unit_map.items():
        if field in df.columns:
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
    context_group=None, context_project_label=None,
):
    """Since input csv files were provided, update labels where new ones were given.

    Args:
        api_key (str): Flywheel API key
        run_level (str): the level at which the gear is running: 'project' or 'subject'
        df (str | Path): path to the session_info CSV
        site_config_path (str | Path | None): path to the site config YAML, or None for v1 fallback
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

    # Load site config if provided
    site_config = None
    if site_config_path:
        with open(site_config_path, 'r') as f:
            site_config = yaml.safe_load(f)
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

    csv_data = cast_metadata_fields(csv_data, metadata_template)

    # Determine which canonical fields are absent from the CSV entirely (same for all rows)
    canonical_not_in_csv = sorted(canonical_fields - set(csv_data.columns))

    def process_row(row, replace):
        # Exclude identifier and date columns from field writes
        identifier_cols = {'group_id', 'project_id', 'subject_id', 'session_id'}
        if session_date_field:
            identifier_cols.add(session_date_field)

        subject_id = row.get('subject_id')
        session_id = row.get('session_id')  # may be None in date/subject_only modes

        audit = {
            'subject_id': subject_id,
            'session_id': session_id,
            'match_status': 'not_found',
            'fields_written': [],
            'canonical_empty': [],
            'pre_existing': [],
            'site_raw_written': [],
        }

        try:
            subject = next(
                (c for c in project_obj.subjects() if c.label == subject_id), None
            )
            if subject is None:
                audit['match_status'] = f'error: subject {subject_id} not found'
                return audit
            subject = subject.reload()

            # --- Session matching ---
            if session_match_mode == 'date':
                date_str = str(row.get(session_date_field, '')).strip()
                try:
                    site_date = datetime.strptime(date_str, session_date_format).date()
                except ValueError as exc:
                    audit['match_status'] = (
                        f'error: invalid date "{date_str}" '
                        f'for format "{session_date_format}": {exc}'
                    )
                    return audit
                candidates = [
                    s for s in subject.sessions()
                    if s.timestamp
                    and abs((s.timestamp.date() - site_date).days) <= session_date_tolerance.days
                ]
                if len(candidates) == 0:
                    audit['match_status'] = (
                        f'not_found: no session within {session_date_tolerance.days}d '
                        f'of {date_str}'
                    )
                    return audit
                if len(candidates) > 1:
                    labels = [s.label for s in candidates]
                    audit['match_status'] = (
                        f'ambiguous: {len(candidates)} sessions match '
                        f'date {date_str}: {labels}'
                    )
                    return audit
                session = candidates[0]
                audit['session_id'] = session.label  # record actual FW session label

            elif session_match_mode == 'subject_only':
                all_sessions = list(subject.sessions())
                if len(all_sessions) == 0:
                    audit['match_status'] = 'not_found: subject has no sessions'
                    return audit
                if len(all_sessions) > 1:
                    labels = [s.label for s in all_sessions]
                    audit['match_status'] = (
                        f'ambiguous: subject has {len(all_sessions)} sessions, '
                        f'use session_match: date to disambiguate: {labels}'
                    )
                    return audit
                session = all_sessions[0]
                audit['session_id'] = session.label

            else:  # 'label' — exact match on Flywheel session label (default / v1)
                session = next(
                    (c for c in subject.sessions() if c.label == session_id), None
                )

            if session:
                session = session.reload()
                ses_dict = session.info
                ses_dict = clean_session(ses_dict)
                session.replace_info(ses_dict)
                session = session.reload()
                ses_dict = session.info

                # Audit: canonical fields already populated before this update
                audit['pre_existing'] = sorted(
                    k for k in canonical_fields
                    if k in ses_dict and ses_dict[k] is not None
                )

                # Audit: canonical fields present in CSV but blank for this row
                audit['canonical_empty'] = sorted(
                    k for k in canonical_fields
                    if k in row
                    and (
                        row[k] is None
                        or (isinstance(row[k], float) and pd.isna(row[k]))
                        or str(row[k]).strip() == ''
                    )
                )

                # Write values: skip identifiers, skip empty, route site_raw to sub-dict
                site_raw_dict = dict(ses_dict.get(site_raw_prefix, {}))
                for key, value in row.items():
                    if key in identifier_cols:
                        continue
                    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == '':
                        continue
                    if key in site_raw_cols:
                        # site_raw column: only write if store_site_raw is enabled
                        # (key is guaranteed not in canonical_fields by the dedup guard above)
                        if store_site_raw:
                            site_raw_dict[key] = value
                            audit['site_raw_written'].append(key)
                    else:
                        ses_dict[key] = value
                        audit['fields_written'].append(key)

                if site_raw_dict:
                    ses_dict[site_raw_prefix] = site_raw_dict

                audit['match_status'] = 'updated'
                if replace:
                    session.replace_info(ses_dict)
                else:
                    session.update_info(ses_dict)
            else:
                audit['match_status'] = 'not_found'

        except Exception as e:
            audit['match_status'] = f'error: {e}'

        return audit

    replace = True
    audit_rows = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(process_row, row, replace)
            for _, row in csv_data.iterrows()
        ]
        for future in as_completed(futures):
            result = future.result()
            print(f"{result['match_status']}: subject={result['subject_id']} session={result['session_id']}")
            audit_rows.append(result)

    # Write reconciliation / audit CSV
    audit_path = "/flywheel/v0/output/reconciliation_report.csv"
    audit_fieldnames = [
        'subject_id', 'session_id', 'match_status',
        'fields_written', 'canonical_empty',
        'canonical_not_in_csv', 'pre_existing', 'site_raw_written',
    ]
    with open(audit_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=audit_fieldnames)
        writer.writeheader()
        for r in audit_rows:
            writer.writerow({
                'subject_id':         r['subject_id'],
                'session_id':         r['session_id'],
                'match_status':       r['match_status'],
                'fields_written':     '; '.join(r['fields_written']),
                'canonical_empty':    '; '.join(r['canonical_empty']),
                'canonical_not_in_csv': '; '.join(canonical_not_in_csv),
                'pre_existing':       '; '.join(r['pre_existing']),
                'site_raw_written':   '; '.join(r['site_raw_written']),
            })
    print(f"Reconciliation report written to {audit_path}")
    print("All sessions updated from CSV.")

    return 0  # all is well
