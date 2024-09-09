"""Module to test get_inputs.py"""

from os import chdir
from pathlib import Path

from flywheel_gear_toolkit import GearToolkitContext

from app.get_inputs import load_inputs
from tests.utils_for_testing import change_path_for_testing

FWV0 = Path.cwd()


def test_load_inputs_no_inputs_works(capfd, print_captured, search_stdout_contains):
    """Test load_inputs with no inputs."""

    with GearToolkitContext(input_args=list(), log_metadata=False) as gear_context:
        gear_context.init_logging()

    inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

    captured = capfd.readouterr()
    print_captured(captured)

    assert search_stdout_contains(captured, "Log level is", "INFO")
    assert inputs_provided is False
    assert acq_df is None


def test_load_inputs_with_inputs_works(capfd, print_captured, search_stdout_contains):
    """Test load_inputs with inputs.

    This test simulates a running gear by using the config.json file, and he input and
    output directories in a "running gear directory" that is a subdirectory of the tests/gears
    directory.  To do this, the current working directory is changed to the running gear
    directory and this requires that the path to config.json and the paths to the inputs
    in config.json need to be changed to be found relative to the running gear directory.
    After the tests, the current working directory is restored to the original directory.
    """

    chdir(FWV0 / "tests/gears/parser")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        change_path_for_testing(gear_context, config_path)

    inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

    captured = capfd.readouterr()
    print_captured(captured)

    assert search_stdout_contains(captured, "Log level is", "DEBUG")
    assert inputs_provided is True
    assert gear_context.config.get("debug") is True
    assert gear_context.config.get("dry_run") is False

    chdir(FWV0)  # get back to where we once belonged


def test_load_inputs_not_all_works(capfd, print_captured, search_stdout_contains):
    """Test load_inputs with inputs."""

    chdir(FWV0 / "tests/gears/some_inputs")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        change_path_for_testing(gear_context, config_path)

    inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

    captured = capfd.readouterr()
    print_captured(captured)

    assert search_stdout_contains(captured, "Subject spreadsheet", "not provided")
    assert search_stdout_contains(captured, "Log level is", "INFO")
    assert inputs_provided is True
    assert gear_context.config.get("debug") is False
    assert gear_context.config.get("dry_run") is False

    chdir(FWV0)  # get back to where we once belonged
