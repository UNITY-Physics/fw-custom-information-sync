"""Helpers for normalizing session info before replace_info calls."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def _clean_value(value):
    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, Mapping):
        return {str(key): _clean_value(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_clean_value(item) for item in value]

    return value


def clean_session(session_info):
    """Return a replace_info-safe copy of session metadata.

    The helper is intentionally conservative because historical versions of this
    gear updated session info without any cleaning step. Missing session info is
    treated as an empty mapping.
    """

    if session_info is None:
        return {}

    if not isinstance(session_info, Mapping):
        raise TypeError("session_info must be a mapping or None")

    return {str(key): _clean_value(value) for key, value in session_info.items()}