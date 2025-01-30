"""Parser module to parse gear config.json."""

import logging

from flywheel_gear_toolkit import GearToolkitContext
from pandas import DataFrame

log = logging.getLogger(__name__)


def load_inputs(
    gear_context: GearToolkitContext,
) -> tuple[bool, DataFrame ]:
    """Read provided input csv files and return dataframes.

    The user provides new custom information for sessions in the input csv files.
    If csv missing, the corresponding dataframe will be None and gear will generate csv with existing information.

    Returns:
         inputs_provided [bool]: true if any input csv file is provided
         ses_df  [dataframe]: session spreadsheet
    """
    api_key = gear_context.get_input("api-key").get("key")

    df = gear_context.get_input_path("session_info")

    if df:
        log.info(f"Loaded {df}")
        inputs_provided = True
    else:
        log.info("Session spreadsheet not provided")
        inputs_provided = False

    return api_key, inputs_provided, df
