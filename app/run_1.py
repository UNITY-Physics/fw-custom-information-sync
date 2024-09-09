"""First run of gear with no inputs, gathers labels for subjects, sessions, and custom inforamation for session"""

import logging

import flywheel
import pandas as pd
import csv
from datetime import datetime

log = logging.getLogger(__name__)

# Function to write headers and rows to CSV
def write_csv(filename, all_fieldnames, rows):
    with open(filename, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_first_stage_no_inputs(context, destination):
    """Run the first stage of the gear with no inputs.

    Args:
        context (flywheel_gear_toolkit.GearToolkitContext): The gear context
        destination (flywheel.Analysis): Where results will be stored

    This stage gathers labels for subjects, sessions, and custom info and saves them to csv files.

    Returns:
        0 [int]: if it gets this far, all is well

    """
    # Prepare a variable to store all fieldnames (headers) that we encounter
    all_fieldnames = ['group_id', 'project_id', 'subject_id', 'session_id']

    # Store all rows to write later
    all_rows = []


    # Get the current timestamp
    current_timestamp = datetime.now()
    # Format the timestamp as a string
    formatted_timestamp = current_timestamp.strftime('%Y-%m-%d %H:%M:%S')

    # File name for the CSV
    filename = (f"/flywheel/v0/work/{destination.label}_{formatted_timestamp}.csv")
    print(f"Saving data to {filename}")

    # container labels
    project = destination.parents["project"]
    group = project.parents["group"]

    # Loop over all sessions in the project
    for session in destination.sessions.iter():
                        print(f"\t\t{session.subject.label}")
                        subject = session.subject
                        print(f"\t\t{session.label}")
                        session = session.reload()

                        # Dictionary from session.info
                        ses_dict = session.info

                        # Add additional info to the dictionary
                        ses_dict['group_id'] = group.label
                        ses_dict['project_id'] = project.label
                        ses_dict['subject_id'] = subject.label
                        ses_dict['session_id'] = session.label

                        # Check for new keys in the ses_dict and update headers
                        new_keys = [key for key in ses_dict.keys() if key not in all_fieldnames]
                        if new_keys:
                            all_fieldnames.extend(new_keys)  # Add any new keys to the fieldnames

                        # Add the row to our collection of rows
                        all_rows.append({key: ses_dict.get(key, '') for key in all_fieldnames})

    # After processing all sessions, write the CSV with updated headers
    write_csv(filename, all_fieldnames, all_rows)

    print(f"Data saved to {filename}")
    return 0  # all is well
