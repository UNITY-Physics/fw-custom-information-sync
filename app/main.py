"""Main module."""

import logging

from app.run_1 import run_first_stage_no_inputs
from app.run_2 import run_second_stage_with_inputs

log = logging.getLogger(__name__)


def run(context, inputs_provided, ses_df, dry_run):
    """Gather necesary information and run either the first stage (no inputs) or the second stage (with inputs).

    Returns:
        e_code [int]: 0 if all is well, 1 if there is an error
    """

    destination = context.client.get_analysis(context.destination["id"])
    run_level = destination.parent["type"]
    if run_level not in ["project", "subject"]:
        raise RuntimeError(
            f"Cannot run at {run_level} level, please run at"
            " subject or project level"
        )
    hierarchy = destination.parents
    if hierarchy["group"] and hierarchy["project"]:
        group = hierarchy["group"]
        project_id = hierarchy["project"]
    else:
        log.exception("Unable to determine run level and hierarchy, exiting")
        return 1

    project = context.client.get_project(project_id)
    log.info(f"Found project {group}/{project.label}")

    msg = "a single subject" if run_level == "subject" else "the whole project"
    log.info(f"Running on {msg}")

    if not inputs_provided:
        e_code = run_first_stage_no_inputs(context, destination, project)

    else:
        e_code = run_second_stage_with_inputs(context.client, run_level, hierarchy, ses_df, dry_run)

    return e_code
