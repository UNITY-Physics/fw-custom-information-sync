"""Parser module to parse gear config.json."""

import logging
import pandas as pd

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
    ses = gear_context.get_input_path("session_info")

    if ses:
        ses_df = pd.read_csv(ses)
        log.info(f"Loaded {ses}")
        inputs_provided = True
    else:
        ses_df = None
        log.info("Session spreadsheet not provided")
        inputs_provided = False

    return inputs_provided, ses_df
