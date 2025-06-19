"""Second run of gear with inputs and doing renaming"""

import logging
import flywheel
import csv
import ast
import yaml

log = logging.getLogger(__name__)


import pandas as pd
import ast

from concurrent.futures import ThreadPoolExecutor, as_completed

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

    csv_data = pd.DataFrame(csv_data)
    csv_data = cast_metadata_fields(csv_data, metadata_template)

    def process_row(row):
        try:
            group_id = row['group_id']
            project_id = row['project_id']
            subject_id = row['subject_id']
            session_id = row['session_id']

            group = fw.lookup(group_id)
            project = group.projects.find_first(f'label={project_id}')
            subject = project.subjects.find_first(f'label={subject_id}')
            session = subject.sessions.find_first(f'label={session_id}')

            if session:
                session = session.reload()
                ses_dict = session.info

                for key, value in row.items():
                    if key not in ['group_id', 'project_id', 'subject_id', 'session_id']:
                        if value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip() != '':
                            ses_dict[key] = value

                session.update_info(ses_dict)
                return f"Updated session {session_id} for subject {subject_id} in project {project_id}"
            else:
                return f"Session {session_id} not found for subject {subject_id} in project {project_id}"
        
        except Exception as e:
            return f"Error processing row for session {row.get('session_id')}: {e}"

    # Use ThreadPoolExecutor to parallelize
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_row, row) for _, row in csv_data.iterrows()]
        
        for future in as_completed(futures):
            print(future.result())

    
    print("All sessions updated from CSV.")

    return 0  # all is well
