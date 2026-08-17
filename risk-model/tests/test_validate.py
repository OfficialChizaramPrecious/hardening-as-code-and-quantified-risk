"""Tests for risk-model input validation.

Covers the four categories the technical assessment contract requires:
positive (clean input accepted), negative (each contract rule rejected),
malformed input (absent, null, or wrong-typed fields), and guard tests that
protect properties the grading rules depend on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from validate import (
    ERROR_CODES,
    REQUIRED_RISK_FIELDS,
    RiskModelValidationError,
    assert_valid,
    validate_risk_rows,
)


def codes(errors) -> list[str]:
    """Error codes from a validation result, for concise assertions."""
    return [e.code for e in errors]


# --------------------------------------------------------------------------
# Positive: clean input is accepted
# --------------------------------------------------------------------------


def test_clean_row_produces_no_errors(valid_row, asset_table):
    assert validate_risk_rows([valid_row], asset_table) == []


def test_clean_row_without_asset_table_produces_no_errors(valid_row):
    """The asset table is optional; its absence must not invent errors."""
    assert validate_risk_rows([valid_row]) == []


def test_empty_input_is_accepted(asset_table):
    """No rows means no violations. Emptiness is a modelling concern, not a
    validation error."""
    assert validate_risk_rows([], asset_table) == []


def test_assert_valid_stays_silent_on_clean_input(valid_row, asset_table):
    assert_valid([valid_row], asset_table)  # must not raise


def test_boundary_control_values_are_accepted(valid_row):
    """0 and 1 are inside the contract's inclusive bounds."""
    row = dict(valid_row, control_min=0.0, control_max=1.0)
    assert validate_risk_rows([row]) == []


# --------------------------------------------------------------------------
# Negative: each rule named in the contract is enforced
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"freq_min": 3.0},                      # min above mode
        {"freq_mode": 5.0},                     # mode above max
        {"loss_min": 9000.0},                   # min above mode
        {"loss_mode": 50000.0},                 # mode above max
    ],
)
def test_inverted_triangular_range_is_rejected(valid_row, overrides):
    row = dict(valid_row, **overrides)
    assert "INVERTED_RANGE" in codes(validate_risk_rows([row]))


def test_inverted_control_range_is_rejected(valid_row):
    row = dict(valid_row, control_min=0.8, control_max=0.3)
    assert "INVERTED_RANGE" in codes(validate_risk_rows([row]))


@pytest.mark.parametrize("value", [-0.1, 1.1, 2.0, -5])
def test_control_outside_unit_interval_is_rejected(valid_row, value):
    row = dict(valid_row, control_max=value)
    assert "CONTROL_OUT_OF_BOUNDS" in codes(validate_risk_rows([row]))


@pytest.mark.parametrize("value", [0, 0.0, -1, -0.5])
def test_nonpositive_dependency_multiplier_is_rejected(valid_row, value):
    row = dict(valid_row, dependency_multiplier=value)
    assert "NONPOSITIVE_DEPENDENCY_MULTIPLIER" in codes(validate_risk_rows([row]))


def test_positive_dependency_multiplier_is_accepted(valid_row):
    row = dict(valid_row, dependency_multiplier=0.001)
    assert "NONPOSITIVE_DEPENDENCY_MULTIPLIER" not in codes(validate_risk_rows([row]))


def test_duplicate_risk_ids_are_rejected(valid_row):
    result = codes(validate_risk_rows([valid_row, dict(valid_row)]))
    assert result.count("DUPLICATE_RISK_ID") == 1


def test_duplicate_report_points_at_the_later_row(valid_row):
    errors = validate_risk_rows([valid_row, dict(valid_row)])
    duplicate = next(e for e in errors if e.code == "DUPLICATE_RISK_ID")
    assert duplicate.locator.startswith("row[1]")
    assert "row[0]" in duplicate.detail


def test_three_occurrences_report_two_duplicates(valid_row):
    rows = [valid_row, dict(valid_row), dict(valid_row)]
    assert codes(validate_risk_rows(rows)).count("DUPLICATE_RISK_ID") == 2


def test_distinct_risk_ids_are_accepted(valid_row):
    second = dict(valid_row, risk_id="RISK-SAMPLE-2")
    assert "DUPLICATE_RISK_ID" not in codes(validate_risk_rows([valid_row, second]))


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_asset_id_is_rejected(valid_row, value):
    row = dict(valid_row, asset_id=value)
    assert "MISSING_ASSET_ID" in codes(validate_risk_rows([row]))


def test_unknown_asset_id_is_rejected_when_table_supplied(valid_row, asset_table):
    row = dict(valid_row, asset_id="ASSET-NOT-IN-TABLE")
    result = codes(validate_risk_rows([row], asset_table))
    assert "UNKNOWN_ASSET_ID" in result
    assert "MISSING_ASSET_ID" not in result


def test_unknown_asset_id_is_not_checked_without_a_table(valid_row):
    """Without an asset table there is nothing to check a reference against."""
    row = dict(valid_row, asset_id="ASSET-NOT-IN-TABLE")
    assert "UNKNOWN_ASSET_ID" not in codes(validate_risk_rows([row]))


# --------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", REQUIRED_RISK_FIELDS)
def test_each_required_field_is_reported_when_absent(valid_row, field):
    row = {k: v for k, v in valid_row.items() if k != field}
    errors = [e for e in validate_risk_rows([row]) if e.code == "MISSING_FIELD"]
    assert [e.field for e in errors] == [field]


@pytest.mark.parametrize("field", REQUIRED_RISK_FIELDS)
def test_each_required_field_is_reported_when_null(valid_row, field):
    row = dict(valid_row, **{field: None})
    errors = [e for e in validate_risk_rows([row]) if e.code == "MISSING_FIELD"]
    assert [e.field for e in errors] == [field]


def test_empty_row_reports_every_required_field(valid_row):
    errors = [e for e in validate_risk_rows([{}]) if e.code == "MISSING_FIELD"]
    assert len(errors) == len(REQUIRED_RISK_FIELDS)


@pytest.mark.parametrize("value", ["1000", [1, 2], {"a": 1}])
def test_non_numeric_value_is_rejected(valid_row, value):
    row = dict(valid_row, loss_mode=value)
    assert "NON_NUMERIC" in codes(validate_risk_rows([row]))


def test_boolean_is_not_accepted_as_a_number(valid_row):
    """bool subclasses int in Python; True must not pass as the number 1."""
    row = dict(valid_row, control_min=True)
    assert "NON_NUMERIC" in codes(validate_risk_rows([row]))


def test_degenerate_range_is_rejected(valid_row):
    """numpy triangular requires min < max, so min == max cannot reach a draw."""
    row = dict(valid_row, loss_min=5000.0, loss_mode=5000.0, loss_max=5000.0)
    assert "DEGENERATE_RANGE" in codes(validate_risk_rows([row]))


def test_negative_frequency_is_rejected(valid_row):
    row = dict(valid_row, freq_min=-1.0, freq_mode=0.5, freq_max=2.0)
    assert "NEGATIVE_VALUE" in codes(validate_risk_rows([row]))


def test_malformed_field_does_not_crash_range_checks(valid_row):
    """A non-numeric bound must be reported, not raise a TypeError."""
    row = dict(valid_row, freq_max="not-a-number")
    result = codes(validate_risk_rows([row]))
    assert "NON_NUMERIC" in result


# --------------------------------------------------------------------------
# Guard tests: properties the grading rules depend on
# --------------------------------------------------------------------------


def test_validation_is_exhaustive_not_first_failure_only(valid_row, asset_table):
    """Several independent violations in one row must all be reported."""
    row = dict(
        valid_row,
        freq_min=9.0,               # inverted
        control_max=1.5,            # out of bounds
        dependency_multiplier=0,    # nonpositive
        asset_id="ASSET-ABSENT",    # unknown reference
    )
    result = set(codes(validate_risk_rows([row], asset_table)))
    assert {
        "INVERTED_RANGE",
        "CONTROL_OUT_OF_BOUNDS",
        "NONPOSITIVE_DEPENDENCY_MULTIPLIER",
        "UNKNOWN_ASSET_ID",
    } <= result


def test_every_emitted_code_is_declared(valid_row, asset_table):
    """No rule may emit a code absent from the published ERROR_CODES set."""
    row = dict(
        valid_row,
        freq_min=9.0,
        control_max=1.5,
        dependency_multiplier=0,
        loss_mode="x",
        asset_id="",
    )
    rows = [row, dict(row), {}]
    for error in validate_risk_rows(rows, asset_table):
        assert error.code in ERROR_CODES


def test_locator_is_positional_when_risk_id_is_missing():
    """A row missing risk_id must still be identifiable in the error report."""
    errors = validate_risk_rows([{}])
    assert all(e.locator == "row[0]" for e in errors)


def test_locator_includes_risk_id_when_present(valid_row):
    errors = validate_risk_rows([dict(valid_row, control_max=5.0)])
    assert errors[0].locator == "row[0](RISK-SAMPLE)"


def test_result_is_stable_across_repeated_calls(valid_row, asset_table):
    """Determinism: the same input must yield the same ordered error list."""
    rows = [dict(valid_row, control_max=2.0), {}, dict(valid_row)]
    first = [e.as_dict() for e in validate_risk_rows(rows, asset_table)]
    second = [e.as_dict() for e in validate_risk_rows(rows, asset_table)]
    assert first == second


def test_assert_valid_raises_and_carries_every_error(valid_row):
    row = dict(valid_row, control_max=3.0, dependency_multiplier=-1)
    with pytest.raises(RiskModelValidationError) as excinfo:
        assert_valid([row])
    assert len(excinfo.value.errors) >= 2


def test_validator_source_contains_no_case_identifiers():
    """Anti-shortcut guard.

    The contract forbids branching on supplied identifiers, and hard-coded
    case identifiers cap the project score. This asserts the validator holds
    no literal from the supplied fixtures or the vulnerability export.
    """
    source = (Path(__file__).resolve().parent.parent / "validate.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        r"\bT-[A-Z]\b",        # published treatment ids
        r"\bVF-\d{3}\b",       # vulnerability export finding ids
        r"\bP-RISK-\d{2}\b",   # published fixture case ids
        r"\bUBI-A8-[0-9A-F]",  # evidence marker
    ]
    for pattern in forbidden:
        assert not re.search(pattern, source), f"identifier matching {pattern} in source"


def test_input_is_not_mutated_by_validation(valid_row, asset_table):
    """Validation must be read-only; callers reuse the rows afterwards."""
    row = dict(valid_row, control_max=4.0)
    before = dict(row)
    validate_risk_rows([row], asset_table)
    assert row == before
