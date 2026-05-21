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

from app.run_2 import apply_site_config, cast_metadata_fields

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
        "cohortLocation_country": "Pakistan",   # constant for every row
        "studyTimepoint": "visit",              # rename column
        "childBiologicalSex": "male_child",     # rename column (remapped via value_map)
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
