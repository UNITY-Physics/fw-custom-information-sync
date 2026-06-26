"""First run of gear with no inputs, gathers labels for subjects, sessions, and custom inforamation for session"""

import logging
import shutil

import flywheel
import pandas as pd
import csv
from datetime import datetime
import yaml 
from utils.clean_session_info import clean_session

log = logging.getLogger(__name__)

# Function to write headers and rows to CSV
def write_csv(filename, all_fieldnames, rows):
    with open(filename, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_first_stage_no_inputs(context, destination, project):
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

    # #Add the custom information keys to the fieldnames
    # with open(f"/flywheel/v0/utils/metadata_fields.yaml", 'r') as file:
    #     metadata = yaml.safe_load(file)

    # CDE = metadata["metadata_template"]

    with open(f"/flywheel/v0/utils/cde_template.yaml", 'r') as file:
        metadata = yaml.safe_load(file)

    demographics_cde = metadata['Demographics']
    ses_cde = metadata['SES']
    cognitive_cde = metadata['Cognitive']
    clinical_cde = metadata.get('Clinical', {})
    derived_cde = metadata.get('Derived', {})

    CDE = demographics_cde | ses_cde | cognitive_cde | clinical_cde | derived_cde

    for field in CDE:
        all_fieldnames.append(field)

    with open("/flywheel/v0/utils/old_new_harmonization.yaml", 'r') as file:
        harmonization_map = yaml.safe_load(file)

    # Store all rows to write later
    all_rows = []
    failed_sessions = 0


    # Get the current timestamp
    current_timestamp = datetime.now()
    # Format the timestamp as a string
    formatted_timestamp = current_timestamp.strftime('%Y-%m-%d_%H-%M-%S')

    # File name for the CSV
    filename = (f"/flywheel/v0/output/{project.label}_session-information.csv")
    print(f"Saving data to {filename}")

    # container labels
    print(f"Destination container: {destination.label}")
    group = project.parents["group"]
    print(f"Group: {group}")

    # Loop over all sessions in the project
    for session in project.sessions():
        try:
            print(f"\t\t{session.subject.label}")
            subject = session.subject
            subject = subject.reload()
            if subject.type != "Phantom":
                print(f"\t\t{session.label}")
                session = session.reload()

                # Dictionary from session.info
                ses_dict = session.info
                for key, _ in CDE.items():
                    if key in ses_dict:
                        continue
                    else:
                        ses_dict[key] = None

                ses_dict = clean_session(ses_dict, harmonization_map=harmonization_map, defaults_template=CDE)
                session.replace_info(ses_dict)

                ses_dict['group_id'] = group
                ses_dict['project_id'] = project.label
                ses_dict['subject_id'] = subject.label
                ses_dict['session_id'] = session.label

                new_keys = [key for key in ses_dict.keys() if key not in all_fieldnames]
                if new_keys:
                    all_fieldnames.extend(new_keys)

                all_rows.append({key: ses_dict.get(key, None) for key in all_fieldnames})
        except Exception as e:
            log.error("Failed to process session %s: %s", getattr(session, 'label', 'unknown'), e)
            failed_sessions += 1

    # After processing all sessions, write the CSV with updated headers
    write_csv(filename, all_fieldnames, all_rows)

    print(f"Data saved to {filename}")
    if failed_sessions:
        print(f"WARNING: {failed_sessions} session(s) failed to process — check logs above.")

    # Optionally write the site config template to output
    if context.config.get('download_site_config_template', False):
        template_src = "/flywheel/v0/utils/site_config_template.yaml"
        template_dst = "/flywheel/v0/output/site_config_template.yaml"
        shutil.copy(template_src, template_dst)
        print(f"Site config template written to {template_dst}")

    return 1 if failed_sessions else 0


