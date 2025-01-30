import flywheel
import os
import csv
import json

# Flywheel connection test
# Get the API key from the environment
api_key = os.environ.get('FW_CLI_API_KEY') 
fw = flywheel.Client(api_key=api_key)
print(f"Logged in as {fw.get_current_user().email}")

# File name for the CSV
filename = "output_with_id_timestamp.csv"

# Prepare a variable to store all fieldnames (headers) that we encounter
all_fieldnames = ['group_id', 'project_id', 'subject_id', 'session_id']

# Function to write headers and rows to CSV
def write_csv(filename, all_fieldnames, rows):
    with open(filename, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

groups = fw.groups()
# Store all rows to write later
all_rows = []

# Loop over each group
for group in groups:
    if group.label == 'dev':
        print(f"id: {group.id:12} label: {group.label}:")
        print("--------------------------------------")
        # Get all projects in each group
        projects = group.projects()
        # Loop over all projects and print
        for project in projects:
            if project.label == 'ISMRM_UNITY_DEMO':
                print(f"\t{project.label}")
                print("\t----------------------")
                for session in project.sessions.iter():
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