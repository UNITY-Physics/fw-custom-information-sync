"""Delete a project and all of its subjects.

The developer may want to delete a project that was created for testing purposes and then modified.
This script allows starting over.
"""

import argparse
import sys

import flywheel

fw = flywheel.Client()


def delete_subjects(proj_id):
    """Delete all subjects in a project.

    Args:
        proj_id (str): The project id
    """
    for session in fw.get_project_subjects(proj_id):
        fw.delete_subject(session.id)


def main():
    """Delete a project and all of its subjects.

    After finding the project, the user is prompted to confirm the deletion.
    Optionally, the user may just delete the subjects and keep the project.
    """
    project = fw.lookup(f"{args.group}/{args.project}")

    print(f"Deleting project {project.label}, confirm (y/N): ")
    confirm = input()

    if confirm and confirm == "y":
        delete_subjects(project.id)
        if not args.data_only:
            fw.delete_project(project.id)
    else:
        print("exiting")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete a Dummy Project")
    parser.add_argument("--group", help="Group")
    parser.add_argument("--project", help="Project")
    parser.add_argument(
        "--data-only",
        help="Only delete subjects, not project container",
        action="store_true",
    )

    args = parser.parse_args()
    main()
