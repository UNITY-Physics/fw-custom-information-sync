"""Main module."""

import logging

from app.run_1 import run_first_stage_no_inputs
from app.run_2 import run_second_stage_with_inputs

log = logging.getLogger(__name__)


def run(context, inputs_provided, df, api_key, site_config_path=None, dry_run=False):
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
        e_code = run_second_stage_with_inputs(
            api_key, run_level, df, site_config_path,
            store_site_raw=context.config.get('store_site_raw', False),
            dry_run=dry_run,
            additional_non_imaging_sessions=context.config.get(
                'additional_non_imaging_sessions', False
            ),
            non_imaging_label_prefix=context.config.get('non_imaging_label_prefix', 'NI'),
            non_imaging_block_if_near_imaging_days=context.config.get(
                'non_imaging_block_if_near_imaging_days', 1
            ),
            non_imaging_require_visit_marker=context.config.get(
                'non_imaging_require_visit_marker', True
            ),
            non_imaging_allow_within_imaging_window_if_explicit=context.config.get(
                'non_imaging_allow_within_imaging_window_if_explicit', False
            ),
            context_group=group,
            context_project_label=project.label,
        )

    return e_code
