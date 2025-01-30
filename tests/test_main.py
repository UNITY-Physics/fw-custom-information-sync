"""Module to test main.py"""

from unittest.mock import patch

import flywheel
from flywheel_gear_toolkit import GearToolkitContext

from app.main import run


class Context:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.destination = {"id": "aex", "type": "acquisition"}


def test_run_no_inputs_works(sdk_mock):
    """Make sure first stage gets run when no inputs are provided.

    Args:
        sdk_mock (mock): a mock for all functions of the flywheel SDK provided by the gear toolkit
    """

    context = GearToolkitContext(input_args=list())
    sdk_mock.get_analysis.return_value = flywheel.Analysis(
        label="test",
        parent={"id": "aex", "type": "project"},
        parents={"group": "scien", "project": "Nate-BIDS-pre-curate"},
    )
    sdk_mock.get_project.return_value = flywheel.Project(label="Nate-BIDS-pre-curate")

    with patch(
        "fw_gear_relabel_container.main.run_first_stage_no_inputs"
    ) as mock_run_first_stage_no_inputs:
        mock_run_first_stage_no_inputs.return_value = 12
        exit_code = run(context, False, None, None, None, False)

    assert exit_code == 12


def test_run_with_inputs(sdk_mock):
    """Make sure second stage gets run when inputs are detected

    Args:
        sdk_mock (mock): a mock for all functions of the flywheel SDK provided by the gear toolkit
    """

    context = GearToolkitContext(input_args=list())
    sdk_mock.get_analysis.return_value = flywheel.Analysis(
        label="test",
        parent={"id": "aex", "type": "project"},
        parents={"group": "scien", "project": "Nate-BIDS-pre-curate"},
    )
    sdk_mock.get_project.return_value = flywheel.Project(label="Nate-BIDS-pre-curate")

    with patch(
        "fw_gear_relabel_container.main.run_second_stage_with_inputs"
    ) as mock_run_second_stage_with_inputs:
        mock_run_second_stage_with_inputs.return_value = 13
        exit_code = run(context, True, None, None, None, False)

    assert exit_code == 13
