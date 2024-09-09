#!/usr/bin/env python
"""The gear's main run script."""

import logging
import sys

from flywheel_gear_toolkit import GearToolkitContext

# This design with a separate main and parser module
# allows the gear to be publishable and the main interfaces
# to it can then be imported in another project which enables
# chaining multiple gears together.
from app.parser import parse_config
from app.get_inputs import load_inputs
from app.main import run

log = logging.getLogger(__name__)


def main(context: GearToolkitContext) -> None:  # pragma: no cover
    """Parses gear config and run."""

    dry_run = parse_config(context)  # parse config.json

    api_key, inputs_provided, df = load_inputs(context)

    e_code = run(context, inputs_provided, df, api_key)

    sys.exit(e_code)


# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:
        # Set logging level based on `debug` configuration key in gear config.
        gear_context.init_logging()

        main(gear_context)
