"""Second run of gear with inputs and doing renaming"""

import logging
import flywheel
import csv
import ast
import yaml

log = logging.getLogger(__name__)


import pandas as pd
import ast

metadata_template = {
    "age_at_scan_months": 0,
    "gestational_age_weeks": 0,
    "sex_at_birth": None,
    "birth_weight_kg": 0,
    "birth_length_cm": 0,
    "birth_hc_cm": 0,

    "family_size_at_scan": 0,
    "num_children_in_family": 0,
    "num_children_in_household": 0,
    "num_adults_in_household": 0,

    "birth_order": 0,
    "current_height_cm": 0,
    "current_weight_kg": 0,
    "current_hc_cm": 0,
    "country_of_birth": None,
    "city_of_birth": None,
    "child_ethnicity": None,
    "child_race": None,
    "child_religion": None,
    "child_caste": None,

    "maternal_age_at_birth": 0,
    "maternal_education_years": 0,

    "father_owns_cellphone": False,
    "mother_owns_cellphone": False,
    "child_health_group": [],
    "gsed_composite_score": 0,
    "gsed_psychosocial_score": 0,
    "gsed_daz": 0
}

import pandas as pd
import ast

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
    for col in df.columns:
        if col in template:
            example = template[col]
            if isinstance(example, bool):
                target_type = bool
            elif isinstance(example, int):
                target_type = int
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


def run_second_stage_with_inputs(api_key, run_level, df):
    """Since input csv files were provided, update labels where new ones were given.

    Args:
        client (flywheel.Client): A flywheel client
        run_level (str): the level at which the gear is running: 'project' or 'subject'
        ses_df (pd.DataFrame): dataframe of sessions
        dry_run (bool): If True, do not make any changes just show what would have been.

    Returns:
        int: 0 if all is well, 1 if there is an error
    """
   
    fw = flywheel.Client(api_key=api_key)

    with open(f"/flywheel/v0/utils/metadata_fields.yaml", 'r') as file:
        metadata = yaml.safe_load(file)

    metadata_template = metadata["metadata_template"]

    print(f"Reading CSV at {run_level} level")
    # Read the CSV file with the updated data

    print(f"Reading CSV file {df}")

    with open(df, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        csv_data = [row for row in reader]


    df = cast_metadata_fields(df, metadata_template)

    # Loop over each row in the CSV to update Flywheel session info
    for row in csv_data:
        group_id = row['group_id']
        project_id = row['project_id']
        subject_id = row['subject_id']
        session_id = row['session_id']

        # Locate the session in Flywheel using group_id, project_id, subject_id, session_id
        group = fw.lookup(group_id)
        project = group.projects.find_first(f'label={project_id}')
        subject = project.subjects.find_first(f'label={subject_id}')
        session = subject.sessions.find_first(f'label={session_id}')

        if session:
            # Reload session to get the latest info
            session = session.reload()

            # Update ses_dict with the values from the CSV row
            ses_dict = session.info

            # Loop through the row's keys and update ses_dict
            for key, value in row.items():
                if key not in ['group_id', 'project_id', 'subject_id', 'session_id']:
                    # Update or add the value in ses_dict, if the value is not empty
                    if value:
                        ses_dict[key] = value

            # Update session info in Flywheel with the modified ses_dict
            session.update_info(ses_dict)
            print(f"Updated session {session_id} for subject {subject_id} in project {project_id}")
        else:
            print(f"Session {session_id} not found for subject {subject_id} in project {project_id}")

    print("All sessions updated from CSV.")

    return 0  # all is well
