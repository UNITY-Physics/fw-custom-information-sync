import flywheel
import os
import csv

# Flywheel connection test
# Get the API key from the environment
api_key = os.environ.get('FW_CLI_API_KEY') 
fw = flywheel.Client(api_key=api_key)
print(f"Logged in as {fw.get_current_user().email}")

# File name for the updated CSV
filename = "output_with_id_timestamp.csv"

# Read the CSV file with the updated data
with open(filename, mode='r', newline='') as file:
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