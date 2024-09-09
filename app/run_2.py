"""Second run of gear with inputs and doing renaming"""

import logging
import re
import flywheel as fw
import numpy as np
import pandas as pd
import csv

log = logging.getLogger(__name__)


def run_second_stage_with_inputs(client, run_level, hierarchy, df, dry_run):
    """Since input csv files were provided, update labels where new ones were given.

    Args:
        client (flywheel.Client): A flywheel client
        run_level (str): the level at which the gear is running: 'project' or 'subject'
        ses_df (pd.DataFrame): dataframe of sessions
        dry_run (bool): If True, do not make any changes just show what would have been.

    Returns:
        int: 0 if all is well, 1 if there is an error
    """
   
    print(f"Reading CSV at {run_level} level")
    # Read the CSV file with the updated data
    with open(df, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        csv_data = [row for row in reader]

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
