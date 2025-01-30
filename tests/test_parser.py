"""Test the configuration parser module."""

from os import chdir
from pathlib import Path

from flywheel_gear_toolkit import GearToolkitContext

from app.parser import parse_config

FWV0 = Path.cwd()


def test_parse_config_works():
    """Test parse_config with a valid config file."""

    chdir(FWV0 / "tests/gears/parser")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        dry_run = parse_config(gear_context)

    assert gear_context.config.get("debug") is True
    assert dry_run is False

    chdir(FWV0)  # get back to where we once belonged
