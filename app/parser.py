"""Parser module to parse gear config.json."""

from typing import Tuple

from flywheel_gear_toolkit import GearToolkitContext


def parse_config(
    gear_context: GearToolkitContext,
) -> Tuple[str, str]:
    """get configuration settings from gear context.

    Args:
        gear_context (GearToolkitContext): The gear context

    Returns:
        dry_run (bool): True if the gear should not actually do anything, just report what it would do
    """
    # debug = gear_context.config.get("debug")   this is only used for logging, not needed in gear
    dry_run = gear_context.config.get("dry_run")

    return dry_run
