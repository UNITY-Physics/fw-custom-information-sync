"""A full test of the gear that depends on a real project on latest.sse.flywheel.io."""

from os import chdir
from pathlib import Path

import flywheel
import pytest
from flywheel import ApiException
from flywheel_gear_toolkit import GearToolkitContext

from app.get_inputs import load_inputs
from app.run_1 import run_first_stage_no_inputs
from app.run_2 import run_second_stage_with_inputs
from tests.utils_for_testing import change_path_for_testing, check_for_fw_key

# Save the current working directory because it will be changed and needs to be restored
FWV0 = Path.cwd()

# tests/bin/run.sh explains how to create this project
GROUP = "bids-curation-test"
PROJECT_LABEL = "BIDS_popup_curation"
SUBJECT_LABEL = "IVA_202"

# These are the expected contents of the csv files for the project above.  These were created
# by running test_run_first_stage_works() and then copying the csv files from the output directory
# into the input directory of the simulated gear.  New labels were added to the input csv
# files to set up test_dry_run_second_stage_works().
SUBJECT_LINES = ["subject.label,new subject.label\n", "IVA_202,\n"]
SESSION_LINES = [
    "session.label,new session.label\n",
    "gr-_proj-_ses-1.3.12.2.1107.5.2.43.67025.300000190604153707,\n",
]
ACQUISITION_LINES = [
    "acquisition.label,new acquisition.label\n",
    "AAHead_Scout,\n",
    "AAHead_Scout_MPR_cor,\n",
    "AAHead_Scout_MPR_sag,\n",
    "AAHead_Scout_MPR_tra,\n",
    "Design,\n",
    "EvaSeries_GLM,\n",
    "Mean_&_t-Maps,\n",
    "Pedagogy,\n",
    "PhoenixZIPReport,\n",
    "Resting,\n",
    "StartFMRI,\n",
    "Student feedback,\n",
    "Student work,\n",
    "intermediate t-Map,\n",
    "t1_mprage_short,\n",
    "t2w4radiology,\n",
]


def test_run_first_stage_works_project():
    """Test get_container_labels() on a real project on latest.sse.flywheel.io.

    This test will be skipped if you are not logged in to latest and if the
    destination project does not exist.

    This test simulates a running gear at project level by changing the
    working directory to a folder that has config.json, input/ and output/.
    """

    err, api_key = check_for_fw_key("latest.")
    if err != "ok":
        pytest.skip(err)

    chdir(FWV0 / "tests/gears/popup_on_latest")  # get inside the running gear directory

    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        try:
            project_id = gear_context.client.lookup(f"{GROUP}/{PROJECT_LABEL}").id
        except ApiException as ex:
            err = (
                f"{ex.status} Could not find project {PROJECT_LABEL} in group {GROUP}."
            )
            pytest.skip(err)

        # make a fake destination so the actual project does not have to have one
        destination = flywheel.Analysis(
            label="mocked_analysis",
            parent={"id": project_id, "type": "project"},
            parents={
                "acquisition": None,
                "group": GROUP,
                "project": project_id,
                "session": None,
                "subject": None,
            },
        )

        # This will write csv files into the output directory and they can be used to create
        # test csv files.
        e_code = run_first_stage_no_inputs(gear_context, destination)

    assert e_code == 0, "The return code is not 0"

    # Check that 3 proper output files were generated
    csv_files = list(Path("output").glob("*.csv"))
    assert len(csv_files) == 3, "Did not find 3 csv files"
    lines = list()
    for csv_file in csv_files:
        with open(csv_file, "r") as f:
            lines.append(f.readlines())
    assert lines == [
        SUBJECT_LINES,
        SESSION_LINES,
        ACQUISITION_LINES,
    ], "Some csv file does not have the expected content"

    chdir(FWV0)  # get back to where we once belonged


def test_run_first_stage_works_subject():
    """Test get_container_labels() on a real project on latest.sse.flywheel.io.

    This test will be skipped if you are not logged in to latest and if the
    destination project does not exist.

    This test simulates a running gear at the project level by changing the
    working directory to a folder that has config.json, input/ and output/.
    """

    err, api_key = check_for_fw_key("latest.")
    if err != "ok":
        pytest.skip(err)

    chdir(FWV0 / "tests/gears/popup_on_latest")  # get inside the running gear directory

    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        try:
            project_id = gear_context.client.lookup(f"{GROUP}/{PROJECT_LABEL}").id
        except ApiException as ex:
            err = (
                f"{ex.status} Could not find project {PROJECT_LABEL} in group {GROUP}."
            )
            pytest.skip(err)

        # get subject id to mock parent of subject-level run
        subject_id = gear_context.client.subjects.find(f"label={SUBJECT_LABEL}")[0].id

        # make a fake destination so the actual project does not have to have one
        destination = flywheel.Analysis(
            label="mocked_analysis",
            parent={"id": subject_id, "type": "subject"},
            parents={
                "acquisition": None,
                "group": GROUP,
                "project": project_id,
                "session": None,
                "subject": None,
            },
        )

        # This will write csv files into the output directory and they can be used to create
        # test csv files.
        e_code = run_first_stage_no_inputs(gear_context, destination)

    assert e_code == 0, "The return code is not 0"

    # Check that 3 proper output files were generated
    csv_files = list(Path("output").glob("*.csv"))
    assert len(csv_files) == 3, "Did not find 3 csv files"
    lines = list()
    for csv_file in csv_files:
        with open(csv_file, "r") as f:
            lines.append(f.readlines())
    assert lines == [
        SUBJECT_LINES,
        SESSION_LINES,
        ACQUISITION_LINES,
    ], "Some csv file does not have the expected content"

    chdir(FWV0)  # get back to where we once belonged


def test_dry_run_second_stage_works():
    """Test renaming (dry run) on a real project on latest.sse.flywheel.io.

    This test will be skipped if you are not logged in to latest and if the
    destination project does not exist.

    This test simulates a running gear by changing the working directory to a folder
    that has config.json, input/ and output/.
    """

    err, api_key = check_for_fw_key("latest.")
    if err != "ok":
        pytest.skip(err)

    chdir(FWV0 / "tests/gears/popup_on_latest")  # get inside the running gear directory
    config_path = Path().cwd()
    config_file = config_path / "config.json"
    with GearToolkitContext(config_path=config_file, input_args=list()) as gear_context:
        gear_context.init_logging()

        dry_run = True

        try:
            project_id = gear_context.client.lookup(f"{GROUP}/{PROJECT_LABEL}").id
        except ApiException as ex:
            err = (
                f"{ex.status} Could not find project {PROJECT_LABEL} in group {GROUP}."
            )
            pytest.skip(err)

        # make a fake destination so the actual project does not have to have one
        destination = flywheel.Analysis(
            label="mocked_analysis",
            parent={"id": project_id, "type": "project"},
            parents={
                "acquisition": None,
                "group": GROUP,
                "project": project_id,
                "session": None,
                "subject": None,
            },
        )

        run_level = destination.parent["type"]
        hierarchy = destination.parents

        change_path_for_testing(gear_context, config_path)

        inputs_provided, acq_df, ses_df, sub_df = load_inputs(gear_context)

        e_code = run_second_stage_with_inputs(
            gear_context.client, run_level, hierarchy, acq_df, ses_df, sub_df, dry_run
        )

    assert e_code == 0, "The return code is not 0"

    # because the config has "debug": true, the log file will exist.
    with open("output/job.log", "r") as f:
        lines = f.readlines()

    assert "Dry Run" in lines[5]
    assert "from Resting to func-bold_task-rest-run-01" in lines[5]
    assert (
        "from gr-_proj-_ses-1.3.12.2.1107.5.2.43.67025.300000190604153707 to ses-001"
        in lines[11]
    )
    assert "IVA_202 with new label, code of newSub" in lines[13]

    chdir(FWV0)  # get back to where we once belonged
