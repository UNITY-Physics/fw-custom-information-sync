"""Utilities that are called inside tests."""

import json
from pathlib import Path


def check_for_fw_key(instance):
    """Check if the user is logged in to the expected instance. Return error message if not.

    Args:
        instance (str): Part of the Flywheel instance name.

    Returns:
        result (str): Error message or "ok"
        api_key (str): API key or None
    """

    user_json = Path.home() / ".config/flywheel/user.json"

    api_key = None

    if not user_json.exists():
        result = f"{str(user_json)} file not found."
        return result, api_key

    # Check API key is present:
    with open(user_json, "r", encoding="utf8") as f:
        j = json.load(f)
    if "key" not in j or not j["key"]:
        result = f"No API key available in {str(user_json)}"
    elif instance not in j["key"]:
        result = f"Looking for {instance} but API key is for {j['key'].split(':')[0]}"

    else:
        result = "ok"  # (no error) means user is logged in to expected instance
        api_key = j["key"]

    return result, api_key


def change_path_for_testing(gear_context, config_path):
    """Change the path in the gear context from /flywheel/v0 to wherever we are running (for testing)

    Args:
        gear_context (GearToolkitContext): The gear context
        config_path (Path): The path to the gear's config.json
    """
    for name in ["subjects", "sessions", "acquisitions"]:
        if name in gear_context.config_json["inputs"]:
            ending = gear_context.config_json["inputs"][name]["location"]["path"].split(
                "/"
            )[3:]
            gear_context.config_json["inputs"][name]["location"]["path"] = str(
                config_path / Path(*ending)
            )
