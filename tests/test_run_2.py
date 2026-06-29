"""Tests for pure-Python functions in run_2.

All tests here are Flywheel-free: they exercise apply_site_config and
cast_metadata_fields using the Pakistan CSV (.github/unity_final_Pakistan.csv)
as the primary fixture.  The raw CSV file on disk is never modified — tests
work on in-memory copies produced by pd.read_csv().
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta, date
from pathlib import Path

from app.run_2 import (
    apply_site_config,
    cast_metadata_fields,
    _parse_csv_date,
    _parse_label_as_date,
    _derive_row_status,
    _build_source_row_uid,
    _derive_non_imaging_label,
    _to_bool_with_truthy,
    _is_non_imaging_session,
    _find_non_imaging_session_by_uid,
    _find_non_imaging_session_by_label,
    _id_to_str,
)
import math

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

PAKISTAN_CSV = Path(__file__).parent.parent / ".github" / "unity_final_Pakistan.csv"

# Mirrors the Pakistan site config described in copilot-instructions.md
PAKISTAN_SITE_CONFIG = {
    "id_field": "infantid",
    "session_match": "date",
    "session_date_field": "scan_date",
    "session_date_format": "%d/%m/%Y",
    "session_date_tolerance_days": 3,
    "variable_map": {
        "studyTimepoint": "visit",              # rename column
        "childBiologicalSex": "male_child",     # rename column (remapped via value_map)
    },
    "constant_map": {
        "cohortLocation_country": "Pakistan",   # constant for every row
    },
    "value_map": {
        "childBiologicalSex": {"yes": "Male", "no": "Female"},
    },
    "drop_columns": ["momid", "pregid", "study_id", "REMIND_ENROLLMENT_STATUS_TEXT"],
    "site_raw_pattern": "^(gl1|gs1)",
    "site_raw_prefix": "site_raw",
}


@pytest.fixture
def pakistan_df():
    """Fresh DataFrame from the Pakistan CSV — each test gets its own copy."""
    return pd.read_csv(PAKISTAN_CSV)


# ---------------------------------------------------------------------------
# apply_site_config — v1 fallback
# ---------------------------------------------------------------------------

class TestApplySiteConfigNoConfig:

    def test_none_config_returns_df_unchanged(self, pakistan_df):
        result, site_raw_cols = apply_site_config(pakistan_df.copy(), None)
        assert "infantid" in result.columns
        assert site_raw_cols == set()

    def test_none_config_does_not_drop_columns(self, pakistan_df):
        result, _ = apply_site_config(pakistan_df.copy(), None)
        assert result.shape == pakistan_df.shape


# ---------------------------------------------------------------------------
# apply_site_config — id_field
# ---------------------------------------------------------------------------

class TestApplySiteConfigIdField:

    def test_id_field_renamed_to_subject_id(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert "subject_id" in df.columns
        assert "infantid" not in df.columns

    def test_id_field_values_preserved(self, pakistan_df):
        original_ids = pakistan_df["infantid"].tolist()
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert df["subject_id"].tolist() == original_ids

    def test_id_field_skipped_if_subject_id_already_exists(self):
        df = pd.DataFrame({"infantid": ["a"], "subject_id": ["b"]})
        config = {"id_field": "infantid"}
        result, _ = apply_site_config(df.copy(), config)
        # subject_id already present — original value kept, infantid left alone
        assert result["subject_id"].iloc[0] == "b"
        assert "infantid" in result.columns


# ---------------------------------------------------------------------------
# apply_site_config — drop_columns
# ---------------------------------------------------------------------------

class TestApplySiteConfigDropColumns:

    def test_listed_columns_removed(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        for col in PAKISTAN_SITE_CONFIG["drop_columns"]:
            assert col not in df.columns

    def test_unlisted_columns_retained(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert "scan_date" in df.columns   # not in drop_columns
        assert "birth_weight_kg" in df.columns

    def test_nonexistent_drop_column_is_silently_ignored(self, pakistan_df):
        config = {"drop_columns": ["this_column_does_not_exist"]}
        result, _ = apply_site_config(pakistan_df.copy(), config)
        assert result.shape == pakistan_df.shape


# ---------------------------------------------------------------------------
# apply_site_config — variable_map
# ---------------------------------------------------------------------------

class TestApplySiteConfigVariableMap:

    def test_constant_injected_for_every_row(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert "cohortLocation_country" in df.columns
        assert (df["cohortLocation_country"] == "Pakistan").all()

    def test_column_rename_applied(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert "studyTimepoint" in df.columns
        assert "visit" not in df.columns

    def test_renamed_column_value_preserved(self, pakistan_df):
        original_val = pakistan_df["visit"].iloc[0]
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert df["studyTimepoint"].iloc[0] == original_val


# ---------------------------------------------------------------------------
# apply_site_config — value_map
# ---------------------------------------------------------------------------

class TestApplySiteConfigValueMap:

    def test_yes_maps_to_male(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        yes_rows = pakistan_df[pakistan_df["male_child"].str.lower() == "yes"].index
        for i in yes_rows[:10]:  # spot-check first 10
            assert df["childBiologicalSex"].iloc[i] == "Male"

    def test_no_maps_to_female(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        no_rows = pakistan_df[pakistan_df["male_child"].str.lower() == "no"].index
        for i in no_rows[:10]:
            assert df["childBiologicalSex"].iloc[i] == "Female"

    def test_only_canonical_vocabulary_values_present(self, pakistan_df):
        df, _ = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        vals = set(df["childBiologicalSex"].dropna().unique())
        assert vals <= {"Male", "Female"}


# ---------------------------------------------------------------------------
# apply_site_config — unit_map
# ---------------------------------------------------------------------------

class TestApplySiteConfigUnitMap:

    def test_multiply_by_conversion_applied(self):
        df = pd.DataFrame({
            "weight_lbs": [1.0, 2.0],
            "subject_id": ["a", "b"],
        })
        config = {
            "variable_map": {"childTimepointWeight_kgs": "weight_lbs"},
            "unit_map": {
                "childTimepointWeight_kgs": {
                    "source_unit": "lbs",
                    "target_unit": "kg",
                    "conversion": "multiply_by_0.453592",
                }
            },
        }
        result, _ = apply_site_config(df.copy(), config)
        assert abs(result["childTimepointWeight_kgs"].iloc[0] - 0.453592) < 1e-6
        assert abs(result["childTimepointWeight_kgs"].iloc[1] - 0.907184) < 1e-6

    def test_non_numeric_values_become_nan_after_conversion(self):
        df = pd.DataFrame({"weight_lbs": ["N/A"], "subject_id": ["a"]})
        config = {
            "variable_map": {"childTimepointWeight_kgs": "weight_lbs"},
            "unit_map": {
                "childTimepointWeight_kgs": {
                    "source_unit": "lbs",
                    "target_unit": "kg",
                    "conversion": "multiply_by_0.453592",
                }
            },
        }
        import math
        result, _ = apply_site_config(df.copy(), config)
        assert math.isnan(result["childTimepointWeight_kgs"].iloc[0])


# ---------------------------------------------------------------------------
# apply_site_config — site_raw_pattern
# ---------------------------------------------------------------------------

class TestApplySiteConfigSiteRawPattern:

    def test_gl1_gs1_columns_identified(self, pakistan_df):
        _, site_raw_cols = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert len(site_raw_cols) > 0
        for col in site_raw_cols:
            assert col.startswith("gl1") or col.startswith("gs1")

    def test_gl1_gs1_column_count(self, pakistan_df):
        # Pakistan CSV has 294 gl1*/gs1* columns
        _, site_raw_cols = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert len(site_raw_cols) == 294

    def test_non_matching_columns_not_in_site_raw(self, pakistan_df):
        _, site_raw_cols = apply_site_config(pakistan_df.copy(), PAKISTAN_SITE_CONFIG)
        assert "scan_date" not in site_raw_cols
        assert "birth_weight_kg" not in site_raw_cols

    def test_gsed_item_pattern_alias_accepted(self, pakistan_df):
        """Legacy key 'gsed_item_pattern' is interchangeable with 'site_raw_pattern'."""
        config = {k: v for k, v in PAKISTAN_SITE_CONFIG.items() if k != "site_raw_pattern"}
        config["gsed_item_pattern"] = "^(gl1|gs1)"
        _, site_raw_cols = apply_site_config(pakistan_df.copy(), config)
        assert len(site_raw_cols) == 294

    def test_no_pattern_returns_empty_set(self, pakistan_df):
        config = {k: v for k, v in PAKISTAN_SITE_CONFIG.items() if k != "site_raw_pattern"}
        _, site_raw_cols = apply_site_config(pakistan_df.copy(), config)
        assert site_raw_cols == set()


# ---------------------------------------------------------------------------
# cast_metadata_fields
# ---------------------------------------------------------------------------

MINIMAL_TEMPLATE = {
    "childBirthWeight_kgs": 0.0,    # float default → target type float
    "childBiologicalSex": None,     # None default  → target type str
    "studyTimepoint": None,         # None default  → target type str
    "gsed_LongForm_DAZScore": 0.0,  # float default → target type float
}


class TestCastMetadataFields:

    def test_float_string_cast_to_float(self):
        df = pd.DataFrame({"childBirthWeight_kgs": ["1.95"], "subject_id": ["a"]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert result["childBirthWeight_kgs"].iloc[0] == pytest.approx(1.95)

    def test_str_field_preserved(self):
        df = pd.DataFrame({"childBiologicalSex": ["Male"], "subject_id": ["a"]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert result["childBiologicalSex"].iloc[0] == "Male"

    def test_nan_value_becomes_none(self):
        df = pd.DataFrame({"childBirthWeight_kgs": [float("nan")], "subject_id": ["a"]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert result["childBirthWeight_kgs"].iloc[0] is None

    def test_identifier_cols_cast_to_str(self):
        df = pd.DataFrame({"subject_id": [123], "session_id": [456]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert result["subject_id"].iloc[0] == "123"
        assert result["session_id"].iloc[0] == "456"

    def test_numeric_subject_id_strips_dot_zero(self):
        # Pandas reads integer-only CSV columns as float: 1227 → 1227.0
        # str(1227.0) = "1227.0" which won't match a Flywheel label of "1227"
        df = pd.DataFrame({"subject_id": [1227.0, 1213.0]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert result["subject_id"].iloc[0] == "1227"
        assert result["subject_id"].iloc[1] == "1213"

    def test_id_to_str_whole_float(self):
        assert _id_to_str(1227.0) == "1227"

    def test_id_to_str_string_with_dot_zero(self):
        assert _id_to_str("1227.0") == "1227"

    def test_id_to_str_plain_string(self):
        assert _id_to_str("ABC-123") == "ABC-123"

    def test_id_to_str_nan_returns_none(self):
        import math
        assert _id_to_str(float("nan")) is None

    def test_unknown_column_not_in_template_survives(self):
        df = pd.DataFrame({"unknown_col": ["foo"], "subject_id": ["a"]})
        result = cast_metadata_fields(df.copy(), MINIMAL_TEMPLATE)
        assert "unknown_col" in result.columns


# ---------------------------------------------------------------------------
# Date parsing (logic used in session_match='date' mode)
# ---------------------------------------------------------------------------

class TestDateParsing:

    def test_pakistan_format_parses_correctly(self):
        site_date = datetime.strptime("02/01/2025", "%d/%m/%Y").date()
        assert site_date == date(2025, 1, 2)

    def test_iso_format_parses_correctly(self):
        site_date = datetime.strptime("2025-01-02", "%Y-%m-%d").date()
        assert site_date == date(2025, 1, 2)

    def test_wrong_format_raises_value_error(self):
        with pytest.raises(ValueError):
            datetime.strptime("not-a-date", "%d/%m/%Y")

    def test_tolerance_boundary_inclusive(self):
        site_date = date(2025, 1, 2)
        tolerance = timedelta(days=3)
        assert abs((date(2025, 1, 5) - site_date).days) <= tolerance.days   # exactly 3d
        assert abs((date(2024, 12, 30) - site_date).days) <= tolerance.days  # exactly 3d

    def test_outside_tolerance_does_not_match(self):
        site_date = date(2025, 1, 2)
        tolerance = timedelta(days=3)
        assert not (abs((date(2025, 1, 6) - site_date).days) <= tolerance.days)  # 4d away

    def test_zero_tolerance_requires_exact_date(self):
        site_date = date(2025, 1, 2)
        tolerance = timedelta(days=0)
        assert abs((site_date - site_date).days) <= tolerance.days        # same day ✓
        assert not (abs((date(2025, 1, 3) - site_date).days) <= tolerance.days)  # 1d away ✗


class TestParseCsvDate:

    def test_configured_format_used_first(self):
        d, fmt = _parse_csv_date("30/03/2026", "%d/%m/%Y")
        assert d == date(2026, 3, 30)
        assert fmt == "%d/%m/%Y"

    def test_two_digit_year_fallback(self):
        d, fmt = _parse_csv_date("30/03/26", "%d/%m/%Y")
        assert d == date(2026, 3, 30)
        assert fmt == "%d/%m/%y"

    def test_iso_fallback(self):
        d, fmt = _parse_csv_date("2026-03-30", "%d/%m/%Y")
        assert d == date(2026, 3, 30)
        assert fmt == "%Y-%m-%d"

    def test_flywheel_dicom_timestamp_fallback(self):
        # Flywheel DICOM-style timestamp in CSV (mixed with plain dates in same column)
        d, fmt = _parse_csv_date("2026-03-27_14_29_56", "%Y-%m-%d")
        assert d == date(2026, 3, 27)
        assert fmt == "%Y-%m-%d_%H_%M_%S"

    def test_unrecognised_returns_none(self):
        d, fmt = _parse_csv_date("not-a-date", "%d/%m/%Y")
        assert d is None
        assert fmt is None


class TestParseLabelAsDate:

    def test_flywheel_dicom_label(self):
        # Flywheel DICOM-derived label: YYYY-MM-DD_HH_MM_SS
        d = _parse_label_as_date("2026-03-30_15_41_04")
        assert d == date(2026, 3, 30)

    def test_iso_date_label(self):
        d = _parse_label_as_date("2024-01-01")
        assert d == date(2024, 1, 1)

    def test_slash_date_label(self):
        d = _parse_label_as_date("01/06/2025")
        assert d == date(2025, 6, 1)

    def test_primary_format_takes_priority(self):
        # With primary %d/%m/%Y, "01/06/2025" = June 1
        d = _parse_label_as_date("01/06/2025", "%d/%m/%Y")
        assert d == date(2025, 6, 1)

    def test_unparseable_returns_none(self):
        d = _parse_label_as_date("not-a-date")
        assert d is None


class TestDeriveRowStatus:

    def test_updated_maps_to_imaging_matched(self):
        assert _derive_row_status("updated") == "imaging_matched"

    def test_ambiguous_maps_to_imaging_ambiguous(self):
        assert _derive_row_status("ambiguous: 2 sessions") == "imaging_ambiguous"

    def test_not_found_maps_to_imaging_not_found_by_default(self):
        assert _derive_row_status("not_found: no session") == "imaging_not_found"

    def test_not_found_maps_to_non_imaging_ineligible_when_flag_on(self):
        assert (
            _derive_row_status(
                "not_found: no session", additional_non_imaging_sessions=True
            )
            == "non_imaging_ineligible"
        )

    def test_error_maps_to_invalid_row(self):
        assert _derive_row_status("error: bad date") == "invalid_row"

    def test_non_imaging_created_passthrough(self):
        assert _derive_row_status("non_imaging_created") == "non_imaging_created"

    def test_non_imaging_updated_passthrough(self):
        assert _derive_row_status("non_imaging_updated") == "non_imaging_updated"

    def test_non_imaging_blocked_passthrough(self):
        assert (
            _derive_row_status("non_imaging_blocked_near_imaging")
            == "non_imaging_blocked_near_imaging"
        )


class TestNonImagingHelpers:

    def test_source_row_uid_is_deterministic(self):
        uid_a = _build_source_row_uid("proj", "sub-01", "2026-01-15", "home_visit")
        uid_b = _build_source_row_uid("proj", "sub-01", "2026-01-15", "home_visit")
        assert uid_a == uid_b
        assert len(uid_a) == 16

    def test_derive_non_imaging_label_handles_collision(self):
        label = _derive_non_imaging_label(
            "NI",
            "Home Visit",
            date(2026, 1, 15),
            {"NI-home-visit-20260115"},
        )
        assert label == "NI-home-visit-20260115-2"

    def test_derive_non_imaging_label_uses_unknown_token(self):
        label = _derive_non_imaging_label("NI", "", date(2026, 1, 15), set())
        assert label == "NI-unknown-20260115"

    def test_to_bool_with_truthy_values(self):
        assert _to_bool_with_truthy("YES", ["yes", "1"]) is True
        assert _to_bool_with_truthy("no", ["yes", "1"]) is False

    def test_is_non_imaging_session_from_info_marker(self):
        class FakeSession:
            info = {"session_kind": "non_imaging"}

        assert _is_non_imaging_session(FakeSession()) is True

    def test_find_non_imaging_session_by_uid(self):
        class FakeSession:
            def __init__(self, kind, uid):
                self.info = {"session_kind": kind, "source_row_uid": uid}

        sessions = [
            FakeSession("imaging", "aaa"),
            FakeSession("non_imaging", "bbb"),
        ]
        found = _find_non_imaging_session_by_uid(sessions, "bbb")
        assert found is sessions[1]

    def test_find_non_imaging_session_by_uid_ignores_imaging(self):
        class FakeSession:
            def __init__(self, kind, uid):
                self.info = {"session_kind": kind, "source_row_uid": uid}

        sessions = [FakeSession("imaging", "match-me")]
        found = _find_non_imaging_session_by_uid(sessions, "match-me")
        assert found is None

    def test_find_non_imaging_session_by_label_matches_base(self):
        class FakeSession:
            def __init__(self, kind, label):
                self.info = {"session_kind": kind}
                self.label = label

        sessions = [
            FakeSession("imaging", "2026-03-27_14_29_56"),
            FakeSession("non_imaging", "NI-unknown-20260401"),
        ]
        found = _find_non_imaging_session_by_label(
            sessions, "NI", "", date(2026, 4, 1)
        )
        assert found is sessions[1]

    def test_find_non_imaging_session_by_label_matches_suffixed(self):
        """Matches NI-unknown-20260401-2 when base already existed from a prior run."""
        class FakeSession:
            def __init__(self, kind, label):
                self.info = {"session_kind": kind}
                self.label = label

        sessions = [
            FakeSession("non_imaging", "NI-unknown-20260401-2"),
        ]
        found = _find_non_imaging_session_by_label(
            sessions, "NI", "", date(2026, 4, 1)
        )
        assert found is sessions[0]

    def test_find_non_imaging_session_by_label_ignores_imaging(self):
        class FakeSession:
            def __init__(self, kind, label):
                self.info = {"session_kind": kind}
                self.label = label

        sessions = [FakeSession("imaging", "NI-unknown-20260401")]
        found = _find_non_imaging_session_by_label(
            sessions, "NI", "", date(2026, 4, 1)
        )
        assert found is None


# ---------------------------------------------------------------------------
# null_sentinel — cast_metadata_fields preserves sentinel through type casting
# ---------------------------------------------------------------------------

class TestNullSentinel:

    def test_sentinel_preserved_through_float_cast(self):
        """Sentinel in a float field must survive type casting as the sentinel string."""
        df = pd.DataFrame({"childGestation_weeks": ["NULL", "34.0"], "subject_id": ["a", "b"]})
        template = {"childGestation_weeks": 0.0}
        result = cast_metadata_fields(df.copy(), template, null_sentinel="NULL")
        assert result["childGestation_weeks"].iloc[0] == "NULL"
        assert result["childGestation_weeks"].iloc[1] == pytest.approx(34.0)

    def test_sentinel_preserved_through_bool_cast(self):
        """Sentinel in a bool field must not be coerced to False."""
        df = pd.DataFrame({"mriCollectedAtTimepoint": ["NULL", "true"], "subject_id": ["a", "b"]})
        template = {}
        field_types = {"mriCollectedAtTimepoint": "bool"}
        result = cast_metadata_fields(df.copy(), template, field_types=field_types, null_sentinel="NULL")
        assert result["mriCollectedAtTimepoint"].iloc[0] == "NULL"
        assert result["mriCollectedAtTimepoint"].iloc[1] is True

    def test_sentinel_preserved_for_str_field(self):
        """Sentinel in a str field survives (str cast of 'NULL' is 'NULL', but must match)."""
        df = pd.DataFrame({"childBiologicalSex": ["NULL", "Male"], "subject_id": ["a", "b"]})
        template = {"childBiologicalSex": None}
        result = cast_metadata_fields(df.copy(), template, null_sentinel="NULL")
        assert result["childBiologicalSex"].iloc[0] == "NULL"
        assert result["childBiologicalSex"].iloc[1] == "Male"

    def test_nan_not_confused_with_sentinel(self):
        """Genuine NaN must still become missing (None/NaN), not be treated as the sentinel."""
        df = pd.DataFrame({"childGestation_weeks": [float("nan"), "NULL"], "subject_id": ["a", "b"]})
        template = {"childGestation_weeks": 0.0}
        result = cast_metadata_fields(df.copy(), template, null_sentinel="NULL")
        assert pd.isna(result["childGestation_weeks"].iloc[0])
        assert result["childGestation_weeks"].iloc[1] == "NULL"

    def test_no_sentinel_config_preserves_existing_behaviour(self):
        """Without null_sentinel, 'NULL' string in a float field becomes None (unchanged)."""
        df = pd.DataFrame({"childGestation_weeks": ["NULL"], "subject_id": ["a"]})
        template = {"childGestation_weeks": 0.0}
        result = cast_metadata_fields(df.copy(), template)  # no null_sentinel
        assert result["childGestation_weeks"].iloc[0] is None

    def test_sentinel_preserved_through_unit_map_conversion(self):
        """Sentinel must survive multiply_by unit conversion in apply_site_config."""
        df = pd.DataFrame({
            "length_cm": ["NULL", "50.0"],
            "subject_id": ["a", "b"],
        })
        config = {
            "variable_map": {"childBirthLength_inches": "length_cm"},
            "unit_map": {
                "childBirthLength_inches": {
                    "source_unit": "cm",
                    "target_unit": "inches",
                    "conversion": "multiply_by_0.393701",
                }
            },
            "null_sentinel": "NULL",
        }
        result, _ = apply_site_config(df.copy(), config)
        assert result["childBirthLength_inches"].iloc[0] == "NULL"
        assert abs(float(result["childBirthLength_inches"].iloc[1]) - 19.685) < 0.01

    def test_sentinel_unknown_column_preserved(self):
        """Sentinel in a column not in the template must also be preserved."""
        df = pd.DataFrame({"some_unknown_col": ["NULL", "foo"], "subject_id": ["a", "b"]})
        template = {}
        result = cast_metadata_fields(df.copy(), template, null_sentinel="NULL")
        assert result["some_unknown_col"].iloc[0] == "NULL"
        assert result["some_unknown_col"].iloc[1] == "foo"
