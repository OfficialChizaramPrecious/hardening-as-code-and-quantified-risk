"""Tests for treatment portfolio selection.

The published fixtures exercise one behaviour only: unconstrained optimisation
with empty dependency lists and no ties. The contract also requires dependency
handling, budget boundaries, and tie-breaking, and the hidden transfer fixture
is described as using different identifiers, ordering, values, and edge
conditions. Everything the published set leaves untested is covered here with
locally constructed fixtures.

Treatment identifiers used in local fixtures are invented for the test and
carry no meaning; the selector never branches on them.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from selector import (
    DEFAULT_REQUIRED_COUNT,
    SELECTION_ERROR_CODES,
    TIE_TOLERANCE,
    TreatmentSelectionError,
    round_currency,
    select_portfolio,
    validate_treatments,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "input" / "public-fixtures.json"


def load_fixtures() -> list[dict]:
    """Published calculation fixtures, as issued in the assigned pack."""
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["fixtures"]


def make(identifier: str, cost: float, reduction: float, dependencies=None) -> dict:
    """Build a treatment record for a locally constructed fixture."""
    return {
        "id": identifier,
        "cost": cost,
        "mean_reduction": reduction,
        "dependencies": list(dependencies or []),
    }


# --------------------------------------------------------------------------
# Published fixtures: the documented interface
# --------------------------------------------------------------------------


def test_fixture_file_is_present_and_parses():
    assert FIXTURE_PATH.exists(), f"published fixtures not found at {FIXTURE_PATH}"
    assert len(load_fixtures()) > 0


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f["case_id"])
def test_published_fixture_is_reproduced(fixture):
    """Every published case must match on all four reported values."""
    result = select_portfolio(
        fixture["treatments"],
        fixture["budget"],
        fixture["required_treatment_count"],
    )
    expected = fixture["expected"]
    assert result["selected_treatment_ids"] == expected["selected_treatment_ids"]
    assert result["total_cost"] == expected["total_cost"]
    assert result["mean_reduction"] == expected["mean_reduction"]
    assert result["validation"] == expected["validation"]


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f["case_id"])
def test_published_fixture_selects_exactly_the_required_count(fixture):
    result = select_portfolio(
        fixture["treatments"], fixture["budget"], fixture["required_treatment_count"]
    )
    assert len(result["selected_treatment_ids"]) == fixture["required_treatment_count"]


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f["case_id"])
def test_published_fixture_stays_within_budget(fixture):
    result = select_portfolio(
        fixture["treatments"], fixture["budget"], fixture["required_treatment_count"]
    )
    assert result["total_cost"] <= fixture["budget"]


def test_selection_is_stable_under_input_reordering():
    """Staff run the hidden fixture with different ordering; results must not move."""
    fixture = load_fixtures()[0]
    forward = select_portfolio(
        fixture["treatments"], fixture["budget"], fixture["required_treatment_count"]
    )
    reversed_input = select_portfolio(
        list(reversed(fixture["treatments"])),
        fixture["budget"],
        fixture["required_treatment_count"],
    )
    assert forward == reversed_input


def test_repeated_runs_return_identical_results():
    """Determinism: selection carries no state between calls."""
    fixture = load_fixtures()[0]
    args = (fixture["treatments"], fixture["budget"], fixture["required_treatment_count"])
    assert select_portfolio(*args) == select_portfolio(*args)


# --------------------------------------------------------------------------
# Dependencies: untested by any published fixture
# --------------------------------------------------------------------------


def test_dependency_pulls_its_prerequisite_into_the_portfolio():
    """A greedy pick by reduction would take B, C, D and be invalid: B needs A."""
    treatments = [
        make("TL-1", 1000, 100),
        make("TL-2", 1000, 900, ["TL-1"]),
        make("TL-3", 1000, 500),
        make("TL-4", 1000, 400),
    ]
    result = select_portfolio(treatments, 3000)
    assert result["selected_treatment_ids"] == ["TL-1", "TL-2", "TL-3"]


def test_treatment_is_skipped_when_its_dependency_cannot_be_afforded():
    """High-value option is unreachable because its prerequisite breaks the budget."""
    treatments = [
        make("TL-1", 9000, 10),
        make("TL-2", 500, 9000, ["TL-1"]),
        make("TL-3", 500, 300),
        make("TL-4", 500, 200),
        make("TL-5", 500, 100),
    ]
    result = select_portfolio(treatments, 1600)
    assert "TL-2" not in result["selected_treatment_ids"]
    assert result["selected_treatment_ids"] == ["TL-3", "TL-4", "TL-5"]


def test_dependency_chain_is_honoured_end_to_end():
    """C depends on B, B depends on A: selecting C requires all three."""
    treatments = [
        make("TL-1", 100, 10),
        make("TL-2", 100, 20, ["TL-1"]),
        make("TL-3", 100, 5000, ["TL-2"]),
        make("TL-4", 100, 900),
        make("TL-5", 100, 900),
    ]
    result = select_portfolio(treatments, 300)
    assert result["selected_treatment_ids"] == ["TL-1", "TL-2", "TL-3"]


def test_multiple_dependencies_all_must_be_present():
    """A treatment needing two prerequisites drags both into the portfolio."""
    treatments = [
        make("TL-1", 100, 10),
        make("TL-2", 100, 10),
        make("TL-3", 100, 500, ["TL-1", "TL-2"]),
        make("TL-4", 100, 60),
        make("TL-5", 100, 60),
    ]
    result = select_portfolio(treatments, 1000)
    assert result["selected_treatment_ids"] == ["TL-1", "TL-2", "TL-3"]


def test_empty_dependency_list_and_absent_key_behave_identically():
    with_empty = [make("TL-1", 10, 5), make("TL-2", 10, 5), make("TL-3", 10, 5)]
    without_key = [
        {"id": t["id"], "cost": t["cost"], "mean_reduction": t["mean_reduction"]}
        for t in with_empty
    ]
    assert select_portfolio(with_empty, 100) == select_portfolio(without_key, 100)


# --------------------------------------------------------------------------
# Budget boundaries
# --------------------------------------------------------------------------


def test_portfolio_costing_exactly_the_budget_is_accepted():
    """The contract says cost must not exceed budget, so equality is valid."""
    treatments = [make("TL-1", 50, 1), make("TL-2", 50, 1), make("TL-3", 50, 1)]
    result = select_portfolio(treatments, 150)
    assert result["validation"] == "valid"
    assert result["total_cost"] == 150.0


def test_portfolio_one_unit_over_budget_is_rejected():
    treatments = [make("TL-1", 50, 1), make("TL-2", 50, 1), make("TL-3", 50, 1)]
    assert select_portfolio(treatments, 149)["validation"] == "infeasible"


def test_cheaper_portfolio_wins_only_on_reduction_not_on_cost():
    """The objective is reduction, not savings: a costlier, better portfolio wins."""
    treatments = [
        make("TL-1", 10, 1),
        make("TL-2", 10, 1),
        make("TL-3", 10, 1),
        make("TL-4", 90, 500),
    ]
    result = select_portfolio(treatments, 200)
    assert "TL-4" in result["selected_treatment_ids"]


def test_infeasible_budget_returns_status_rather_than_raising():
    treatments = [make("TL-1", 100, 1), make("TL-2", 100, 1), make("TL-3", 100, 1)]
    result = select_portfolio(treatments, 10)
    assert result["validation"] == "infeasible"
    assert result["selected_treatment_ids"] == []
    assert result["mean_reduction"] == 0.0


def test_too_few_treatments_to_fill_the_portfolio_is_infeasible():
    treatments = [make("TL-1", 10, 1), make("TL-2", 10, 1)]
    assert select_portfolio(treatments, 10_000)["validation"] == "infeasible"


def test_zero_budget_is_valid_input_and_yields_infeasible():
    treatments = [make("TL-1", 1, 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    assert select_portfolio(treatments, 0)["validation"] == "infeasible"


def test_zero_cost_treatments_fit_a_zero_budget():
    treatments = [make("TL-1", 0, 5), make("TL-2", 0, 4), make("TL-3", 0, 3)]
    result = select_portfolio(treatments, 0)
    assert result["validation"] == "valid"
    assert result["total_cost"] == 0.0


# --------------------------------------------------------------------------
# Tie-breaking
# --------------------------------------------------------------------------


def test_exact_tie_resolves_to_lexicographically_smaller_id_list():
    treatments = [
        make("TL-Z", 100, 50),
        make("TL-A", 100, 50),
        make("TL-M", 100, 50),
        make("TL-B", 100, 50),
    ]
    result = select_portfolio(treatments, 1000)
    assert result["selected_treatment_ids"] == ["TL-A", "TL-B", "TL-M"]


def test_sub_cent_difference_is_treated_as_a_tie():
    """A half-cent advantage does not beat the lexicographic rule."""
    treatments = [
        make("TL-Z", 10, 50.000),
        make("TL-A", 10, 50.005),
        make("TL-M", 10, 10),
        make("TL-B", 10, 10),
    ]
    result = select_portfolio(treatments, 100)
    assert result["selected_treatment_ids"] == ["TL-A", "TL-B", "TL-Z"]


def test_difference_of_one_cent_is_not_a_tie():
    """At exactly one cent the objective decides, not the identifier ordering.

    {TL-A, TL-B, TL-C} is lexicographically smaller, but {TL-A, TL-B, TL-Z}
    is better by exactly one cent, which is the threshold. The objective wins.
    """
    treatments = [
        make("TL-A", 10, 1.00),
        make("TL-B", 10, 1.00),
        make("TL-C", 10, 1.00),
        make("TL-Z", 10, 1.01),
    ]
    result = select_portfolio(treatments, 1000)
    assert result["selected_treatment_ids"] == ["TL-A", "TL-B", "TL-Z"]


def test_tie_tolerance_is_one_cent():
    """Guard: the published rule is one cent; a silent change would break grading."""
    assert TIE_TOLERANCE == Decimal("0.01")


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def test_duplicate_treatment_id_is_rejected():
    treatments = [make("TL-1", 1, 1), make("TL-1", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "DUPLICATE_TREATMENT_ID" in [e.code for e in excinfo.value.errors]


def test_unknown_dependency_reference_is_rejected():
    treatments = [
        make("TL-1", 1, 1, ["TL-ABSENT"]),
        make("TL-2", 1, 1),
        make("TL-3", 1, 1),
    ]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "UNKNOWN_DEPENDENCY" in [e.code for e in excinfo.value.errors]


def test_self_dependency_is_rejected():
    treatments = [
        make("TL-1", 1, 1, ["TL-1"]),
        make("TL-2", 1, 1),
        make("TL-3", 1, 1),
    ]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "SELF_DEPENDENCY" in [e.code for e in excinfo.value.errors]


def test_negative_cost_is_rejected():
    treatments = [make("TL-1", -5, 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "NEGATIVE_COST" in [e.code for e in excinfo.value.errors]


@pytest.mark.parametrize("budget", [-1, "1000", None, True])
def test_invalid_budget_is_rejected(budget):
    treatments = [make("TL-1", 1, 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, budget)
    assert "INVALID_BUDGET" in [e.code for e in excinfo.value.errors]


@pytest.mark.parametrize("count", [0, -1, 2.5, "3"])
def test_invalid_required_count_is_rejected(count):
    treatments = [make("TL-1", 1, 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100, count)
    assert "INVALID_REQUIRED_COUNT" in [e.code for e in excinfo.value.errors]


@pytest.mark.parametrize("field", ["id", "cost", "mean_reduction"])
def test_missing_required_treatment_field_is_rejected(field):
    treatment = make("TL-1", 1, 1)
    del treatment[field]
    treatments = [treatment, make("TL-2", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "MISSING_TREATMENT_FIELD" in [e.code for e in excinfo.value.errors]


def test_non_numeric_cost_is_rejected():
    treatments = [make("TL-1", "free", 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    with pytest.raises(TreatmentSelectionError) as excinfo:
        select_portfolio(treatments, 100)
    assert "NON_NUMERIC_TREATMENT_FIELD" in [e.code for e in excinfo.value.errors]


def test_validation_reports_every_violation_at_once():
    treatments = [
        make("TL-1", -5, 1, ["TL-ABSENT"]),
        make("TL-1", 1, 1),
        make("TL-3", 1, 1),
    ]
    errors = validate_treatments(treatments, -100)
    codes = {e.code for e in errors}
    assert {
        "NEGATIVE_COST",
        "UNKNOWN_DEPENDENCY",
        "DUPLICATE_TREATMENT_ID",
        "INVALID_BUDGET",
    } <= codes


# --------------------------------------------------------------------------
# Currency rounding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (2.345, 2.34),   # half-even rounds down to the even digit
        (2.355, 2.36),   # half-even rounds up to the even digit
        (0.125, 0.12),
        (0.135, 0.14),
        (19200, 19200.00),
    ],
)
def test_currency_rounding_is_half_even(value, expected):
    assert round_currency(value) == expected


def test_reduction_is_rounded_only_at_the_reporting_boundary():
    """Sub-cent components accumulate before rounding, not after."""
    treatments = [
        make("TL-1", 1, 0.004),
        make("TL-2", 1, 0.004),
        make("TL-3", 1, 0.004),
    ]
    result = select_portfolio(treatments, 100)
    assert result["mean_reduction"] == 0.01


# --------------------------------------------------------------------------
# Guard tests
# --------------------------------------------------------------------------


def test_default_required_count_is_three():
    assert DEFAULT_REQUIRED_COUNT == 3


def test_every_emitted_code_is_declared():
    treatments = [
        make("TL-1", -5, 1, ["TL-ABSENT", "TL-1"]),
        make("TL-1", "x", None),
        make("TL-3", 1, 1),
    ]
    for error in validate_treatments(treatments, "bad", 0):
        assert error.code in SELECTION_ERROR_CODES


def test_selector_source_contains_no_case_identifiers():
    """Anti-shortcut guard: hard-coded case identifiers cap the project score."""
    source = (Path(__file__).resolve().parent.parent / "selector.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        r"\bT-[A-Z]\b",
        r"\bVF-\d{3}\b",
        r"\bP-RISK-\d{2}\b",
        r"\bUBI-A8-[0-9A-F]",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, source), f"identifier matching {pattern} in source"


def test_input_is_not_mutated_by_selection():
    treatments = [make("TL-1", 1, 1), make("TL-2", 1, 1), make("TL-3", 1, 1)]
    before = json.dumps(treatments, sort_keys=True)
    select_portfolio(treatments, 100)
    assert json.dumps(treatments, sort_keys=True) == before