# Test file for run_1.py

import tempfile
from os import chdir
from pathlib import Path

import pandas as pd
import pytest
from flywheel_gear_toolkit import GearToolkitContext

from app.run_1 import (
    get_container_labels,
    run_first_stage_no_inputs,
    save_csv_with_empty_column,
)
from tests.utils_for_testing import check_for_fw_key

FWV0 = Path.cwd()


def test_get_container_labels_works():
    """Test get_container_labels on a real project on latest.sse.flywheel.io.

    This test will be skipped if you are not logged in to latest and if the
    destination project does not exist.  This test is used for initial development
    because it returns actual platform data that can be used to create additional
    tests that don't need to involve a real project on an existing instance.
    """

    err, api_key = check_for_fw_key("latest.")
    if err != "ok":
        pytest.skip(err)

    chdir(FWV0 / "tests/gears/dest_on_latest")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        destination = gear_context.client.get_analysis(gear_context.destination["id"])
        sub, ses, acq = get_container_labels(gear_context.client, destination)

    assert (
        str(sub["subject.label"].iloc[0]) == "1"
    ), "The first item in column 'subject.label' is not the expected value"
    assert (
        str(ses["session.label"].iloc[0]) == "Session 1"
    ), "The first item in column 'session.label' is not the expected value"
    assert (
        str(acq["acquisition.label"].iloc[5]) == "dMRI_dir98_AP"
    ), "The fifth item in column 'acquisition.label' is not the expected value"

    chdir(FWV0)  # get back to where we once belonged


EXPECTED = "acquisition.label,New acquisition.label\nT1w_MPR,\nrfMRI_REST_AP_Run1,\nrfMRI_REST_PA_Run2_SBRef,\n"


def test_save_csv_works():
    """Test save_csv_with_empty_column with inputs."""

    file_name = "acquisitions.csv"
    df = pd.DataFrame(
        {
            "acquisition.label": [
                "T1w_MPR",
                "rfMRI_REST_AP_Run1",
                "rfMRI_REST_PA_Run2_SBRef",
            ]
        }
    )
    with tempfile.TemporaryDirectory() as tmpdirname:
        save_csv_with_empty_column(df, "New acquisition.label", tmpdirname, file_name)

        with open(f"{tmpdirname}/{file_name}", "r") as ff:
            actual = ff.read()

    assert actual == EXPECTED


def test_run_first_stage_works():
    """Test get_container_labels on a real project on latest.sse.flywheel.io.

    This test will be skipped if you are not logged in to latest and if the
    destination project does not exist.  This test is used for initial development
    because it returns actual platform data that can be used to create additional
    tests that don't need to involve a real project on an existing instance.
    """

    err, api_key = check_for_fw_key("latest.")
    if err != "ok":
        pytest.skip(err)

    chdir(FWV0 / "tests/gears/dest_on_latest")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        # This writes csv files into the output directory that can be used to create tests
        destination = gear_context.client.get_analysis(gear_context.destination["id"])
        run_first_stage_no_inputs(gear_context, destination)

    chdir(FWV0)  # get back to where we once belonged
