"""Tests for the run_2 module."""

from os import chdir
from pathlib import Path

from flywheel_gear_toolkit import GearToolkitContext

from app.get_inputs import load_inputs
from app.run_2 import run_second_stage_with_inputs
from tests.utils_for_testing import change_path_for_testing

FWV0 = Path.cwd()


def test_run_second_stage_detects_empty(capfd, print_captured):
    """Test run_second_stage_with_inputs when the input csv files have no new labels."""

    chdir(FWV0 / "tests/gears/empty")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        change_path_for_testing(gear_context, config_path)

        inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

        # This writes csv files into the output directory that can be used to create tests
        hierarchy = {
            "acquisition": None,
            "group": "scien",
            "project": "648cc74a97d3eefa3964ab3b",
            "session": None,
            "subject": None,
        }
        e_code = run_second_stage_with_inputs(
            gear_context, "project", hierarchy, acq_df, ses_df, sub_df, False
        )

    captured = capfd.readouterr()
    print_captured(captured)

    assert e_code == 1, "The return code is not 1"

    chdir(FWV0)  # get back to where we once belonged


def test_run_second_stage_one_missing(capfd, print_captured):
    """Test run_second_stage_with_inputs when the input csv files have no new labels."""

    chdir(FWV0 / "tests/gears/some_inputs")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        change_path_for_testing(gear_context, config_path)

        inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

        # This writes csv files into the output directory that can be used to create tests
        hierarchy = {
            "acquisition": None,
            "group": "scien",
            "project": "648cc74a97d3eefa3964ab3b",
            "session": None,
            "subject": None,
        }
        e_code = run_second_stage_with_inputs(
            gear_context, "project", hierarchy, acq_df, ses_df, sub_df, False
        )

    captured = capfd.readouterr()
    print_captured(captured)

    assert e_code == 1, "The return code is not 1"

    chdir(FWV0)  # get back to where we once belonged
