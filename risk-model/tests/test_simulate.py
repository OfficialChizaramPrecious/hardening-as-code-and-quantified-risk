"""Tests for the Monte Carlo risk simulation.

No published fixture exercises the simulation path, so every property the
contract specifies is asserted here directly: seed derivation, draw count,
draw order, the inherent and residual arithmetic, percentile method, currency
rounding, determinism, and the overlay's uncertainty sensitivity test.

The evidence marker used below is a test value, not the assigned one. The
module under test takes the marker as an argument precisely so that no
participant identifier is embedded in implementation logic.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from simulate import (
    DRAW_COUNT,
    PROJECT_CODE,
    REPORTED_PERCENTILES,
    SENSITIVITY_FACTOR,
    canonical_order,
    derive_seed,
    make_generator,
    portfolio_totals,
    round_results,
    run_sensitivity,
    scale_loss_ranges,
    simulate_row,
    simulate_rows,
)

TEST_MARKER = "TEST-MARKER-0001"
OTHER_MARKER = "TEST-MARKER-0002"

# A small draw count keeps the suite fast where the contract's 50,000 is not
# the property under test. Tests that assert the pinned count say so.
FAST_DRAWS = 4_000


def make_row(identifier: str = "RX-1", **overrides) -> dict:
    """A well-formed risk row for simulation tests."""
    row = {
        "risk_id": identifier,
        "asset_id": "AX-1",
        "freq_min": 0.2,
        "freq_mode": 1.0,
        "freq_max": 3.0,
        "loss_min": 10_000.0,
        "loss_mode": 50_000.0,
        "loss_max": 200_000.0,
        "control_min": 0.2,
        "control_max": 0.6,
        "dependency_multiplier": 1.0,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------
# Seed derivation
# --------------------------------------------------------------------------


def test_seed_matches_independent_recomputation():
    """Recompute the contract's derivation by hand and compare.

    This is the only check that can catch a wrong slice width, wrong byte
    order, or a wrong separator, because no published fixture covers seeding.
    """
    digest = hashlib.sha256(f"{TEST_MARKER}:{PROJECT_CODE}".encode("utf-8")).digest()
    expected = int.from_bytes(digest[:8], byteorder="big", signed=False)
    assert derive_seed(TEST_MARKER) == expected


def test_seed_uses_the_first_eight_bytes_not_the_last():
    digest = hashlib.sha256(f"{TEST_MARKER}:{PROJECT_CODE}".encode("utf-8")).digest()
    assert derive_seed(TEST_MARKER) != int.from_bytes(digest[-8:], "big")


def test_seed_is_big_endian_not_little():
    digest = hashlib.sha256(f"{TEST_MARKER}:{PROJECT_CODE}".encode("utf-8")).digest()
    assert derive_seed(TEST_MARKER) != int.from_bytes(digest[:8], "little")


def test_seed_is_an_unsigned_64_bit_value():
    seed = derive_seed(TEST_MARKER)
    assert 0 <= seed < 2**64


def test_seed_is_deterministic_for_a_marker():
    assert derive_seed(TEST_MARKER) == derive_seed(TEST_MARKER)


def test_different_markers_derive_different_seeds():
    assert derive_seed(TEST_MARKER) != derive_seed(OTHER_MARKER)


def test_project_code_participates_in_the_seed():
    assert derive_seed(TEST_MARKER) != derive_seed(TEST_MARKER, "OTHER-CODE")


@pytest.mark.parametrize("marker", ["", "   ", None, 12345])
def test_invalid_marker_is_rejected(marker):
    with pytest.raises(ValueError):
        derive_seed(marker)


def test_project_code_is_the_published_value():
    """Guard: the seed string is published; a silent change breaks every result."""
    assert PROJECT_CODE == "GRC-A4"


# --------------------------------------------------------------------------
# Draw count and draw order
# --------------------------------------------------------------------------


def test_draw_count_is_pinned_at_fifty_thousand():
    assert DRAW_COUNT == 50_000


def test_simulation_uses_the_pinned_draw_count_by_default():
    result = simulate_row(make_row(), make_generator(TEST_MARKER))
    assert result["draws"] == 50_000


def test_draw_order_is_frequency_then_loss_then_control():
    """Reconstruct the stream by hand in contract order and compare exactly.

    All three variables consume one generator, so any reordering shifts every
    number downstream. Reproducing the sequence is the only way to prove the
    order is right.
    """
    row = make_row()
    result = simulate_row(row, make_generator(TEST_MARKER), FAST_DRAWS)

    generator = make_generator(TEST_MARKER)
    frequency = generator.triangular(
        row["freq_min"], row["freq_mode"], row["freq_max"], FAST_DRAWS
    )
    loss = generator.triangular(
        row["loss_min"], row["loss_mode"], row["loss_max"], FAST_DRAWS
    )
    control = generator.uniform(row["control_min"], row["control_max"], FAST_DRAWS)

    inherent = frequency * loss * row["dependency_multiplier"]
    residual = inherent * (1.0 - control)

    assert result["inherent"]["mean"] == float(inherent.mean())
    assert result["residual"]["mean"] == float(residual.mean())


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------


def test_inherent_equals_frequency_times_loss_times_dependency():
    """With a near-fixed loss and a known triangular mean, the product is
    analytically predictable: triangular(0, 1, 2) has mean 1."""
    row = make_row(
        freq_min=0.0,
        freq_mode=1.0,
        freq_max=2.0,
        loss_min=100.0,
        loss_mode=100.0001,
        loss_max=100.0002,
        dependency_multiplier=2.0,
    )
    result = simulate_row(row, make_generator(TEST_MARKER))
    assert result["inherent"]["mean"] == pytest.approx(200.0, rel=0.02)


def test_residual_applies_one_minus_control_exactly():
    """A degenerate control range makes the relationship exact, not statistical."""
    row = make_row(control_min=0.5, control_max=0.5)
    result = simulate_row(row, make_generator(TEST_MARKER))
    assert result["residual"]["mean"] == pytest.approx(
        result["inherent"]["mean"] * 0.5, rel=1e-12
    )


def test_zero_control_leaves_residual_equal_to_inherent():
    row = make_row(control_min=0.0, control_max=0.0)
    result = simulate_row(row, make_generator(TEST_MARKER))
    assert result["residual"]["mean"] == pytest.approx(
        result["inherent"]["mean"], rel=1e-12
    )


def test_full_control_drives_residual_to_zero():
    row = make_row(control_min=1.0, control_max=1.0)
    result = simulate_row(row, make_generator(TEST_MARKER))
    assert result["residual"]["mean"] == pytest.approx(0.0, abs=1e-9)


def test_dependency_multiplier_scales_inherent_linearly():
    single = simulate_row(
        make_row(dependency_multiplier=1.0), make_generator(TEST_MARKER), FAST_DRAWS
    )
    double = simulate_row(
        make_row(dependency_multiplier=2.0), make_generator(TEST_MARKER), FAST_DRAWS
    )
    assert double["inherent"]["mean"] == pytest.approx(
        single["inherent"]["mean"] * 2, rel=1e-12
    )


def test_mean_reduction_is_inherent_minus_residual():
    result = simulate_row(make_row(), make_generator(TEST_MARKER), FAST_DRAWS)
    assert result["mean_reduction"] == pytest.approx(
        result["inherent"]["mean"] - result["residual"]["mean"], rel=1e-12
    )


def test_residual_never_exceeds_inherent_for_valid_control():
    result = simulate_row(make_row(), make_generator(TEST_MARKER), FAST_DRAWS)
    assert result["residual"]["mean"] <= result["inherent"]["mean"]


# --------------------------------------------------------------------------
# Percentiles
# --------------------------------------------------------------------------


def test_reported_percentiles_are_p50_and_p90():
    assert REPORTED_PERCENTILES == (50, 90)


def test_summary_exposes_mean_p50_and_p90():
    result = simulate_row(make_row(), make_generator(TEST_MARKER), FAST_DRAWS)
    assert set(result["inherent"]) == {"mean", "p50", "p90"}
    assert set(result["residual"]) == {"mean", "p50", "p90"}


def test_percentiles_use_numpy_default_linear_method():
    row = make_row()
    result = simulate_row(row, make_generator(TEST_MARKER), FAST_DRAWS)

    generator = make_generator(TEST_MARKER)
    frequency = generator.triangular(
        row["freq_min"], row["freq_mode"], row["freq_max"], FAST_DRAWS
    )
    loss = generator.triangular(
        row["loss_min"], row["loss_mode"], row["loss_max"], FAST_DRAWS
    )
    generator.uniform(row["control_min"], row["control_max"], FAST_DRAWS)
    inherent = frequency * loss * row["dependency_multiplier"]

    assert result["inherent"]["p90"] == float(np.percentile(inherent, 90))


def test_p90_is_at_least_p50():
    result = simulate_row(make_row(), make_generator(TEST_MARKER), FAST_DRAWS)
    assert result["inherent"]["p90"] >= result["inherent"]["p50"]


# --------------------------------------------------------------------------
# Determinism and ordering
# --------------------------------------------------------------------------


def test_repeated_runs_produce_identical_results():
    rows = [make_row("RX-1"), make_row("RX-2")]
    first = simulate_rows(rows, TEST_MARKER, FAST_DRAWS)
    second = simulate_rows(rows, TEST_MARKER, FAST_DRAWS)
    assert first == second


def test_results_are_invariant_to_input_row_ordering():
    """Staff run the hidden fixture with different ordering."""
    rows = [make_row("RX-1"), make_row("RX-2", loss_mode=70_000.0)]
    forward = simulate_rows(rows, TEST_MARKER, FAST_DRAWS)
    backward = simulate_rows(list(reversed(rows)), TEST_MARKER, FAST_DRAWS)
    assert forward == backward


def test_canonical_order_sorts_by_risk_id():
    rows = [make_row("RX-9"), make_row("RX-1"), make_row("RX-5")]
    assert [r["risk_id"] for r in canonical_order(rows)] == ["RX-1", "RX-5", "RX-9"]


def test_a_different_marker_changes_the_results():
    rows = [make_row()]
    assert simulate_rows(rows, TEST_MARKER, FAST_DRAWS) != simulate_rows(
        rows, OTHER_MARKER, FAST_DRAWS
    )


def test_simulation_does_not_mutate_input_rows():
    rows = [make_row("RX-1"), make_row("RX-2")]
    before = [dict(r) for r in rows]
    simulate_rows(rows, TEST_MARKER, FAST_DRAWS)
    assert rows == before


# --------------------------------------------------------------------------
# Reporting and rounding
# --------------------------------------------------------------------------


def test_rounding_is_applied_only_at_the_reporting_boundary():
    results = simulate_rows([make_row()], TEST_MARKER, FAST_DRAWS)
    rounded = round_results(results)
    value = rounded[0]["inherent"]["mean"]
    assert round(value, 2) == value


def test_rounding_does_not_alter_the_underlying_results():
    results = simulate_rows([make_row()], TEST_MARKER, FAST_DRAWS)
    snapshot = results[0]["inherent"]["mean"]
    round_results(results)
    assert results[0]["inherent"]["mean"] == snapshot


def test_portfolio_totals_sum_the_means():
    results = simulate_rows(
        [make_row("RX-1"), make_row("RX-2")], TEST_MARKER, FAST_DRAWS
    )
    totals = portfolio_totals(results)
    expected = sum(r["inherent"]["mean"] for r in results)
    assert totals["inherent_mean_annual_loss"] == pytest.approx(expected, abs=0.01)
    assert totals["rows_simulated"] == 2


def test_portfolio_totals_do_not_sum_percentiles():
    """Percentiles are not additive; summing them would overstate tail risk."""
    results = simulate_rows([make_row()], TEST_MARKER, FAST_DRAWS)
    totals = portfolio_totals(results)
    assert not any(key.startswith("p") for key in totals)


def test_portfolio_reduction_is_inherent_minus_residual():
    results = simulate_rows([make_row("RX-1")], TEST_MARKER, FAST_DRAWS)
    totals = portfolio_totals(results)
    difference = (
        totals["inherent_mean_annual_loss"] - totals["residual_mean_annual_loss"]
    )
    assert totals["mean_reduction"] == pytest.approx(difference, abs=0.01)


# --------------------------------------------------------------------------
# Uncertainty sensitivity test (private overlay requirement)
# --------------------------------------------------------------------------


def test_sensitivity_factor_is_thirty_percent():
    """Guard: the overlay sets the band at 30%."""
    assert SENSITIVITY_FACTOR == 0.30


def test_scaling_moves_the_whole_loss_triple():
    scaled = scale_loss_ranges([make_row()], 0.30)[0]
    base = make_row()
    for field in ("loss_min", "loss_mode", "loss_max"):
        assert scaled[field] == pytest.approx(base[field] * 1.30)


def test_scaling_preserves_the_min_mode_max_relationship():
    scaled = scale_loss_ranges([make_row()], -0.30)[0]
    assert scaled["loss_min"] <= scaled["loss_mode"] <= scaled["loss_max"]


def test_scaling_leaves_frequency_and_control_untouched():
    """The overlay scopes the test to annual-loss ranges specifically."""
    base = make_row()
    scaled = scale_loss_ranges([base], 0.30)[0]
    for field in (
        "freq_min",
        "freq_mode",
        "freq_max",
        "control_min",
        "control_max",
        "dependency_multiplier",
    ):
        assert scaled[field] == base[field]


def test_scaling_does_not_mutate_the_source_rows():
    rows = [make_row()]
    before = [dict(r) for r in rows]
    scale_loss_ranges(rows, 0.30)
    assert rows == before


def test_scaling_rejects_a_factor_that_would_invert_the_range():
    with pytest.raises(ValueError):
        scale_loss_ranges([make_row()], -1.5)


def test_sensitivity_reports_low_base_and_high_cases():
    output = run_sensitivity([make_row()], TEST_MARKER, draws=FAST_DRAWS)
    assert set(output["cases"]) == {"low", "base", "high"}
    assert output["factor"] == SENSITIVITY_FACTOR


def test_sensitivity_cases_move_with_the_band():
    output = run_sensitivity([make_row()], TEST_MARKER, draws=FAST_DRAWS)
    low = output["cases"]["low"]["totals"]["inherent_mean_annual_loss"]
    base = output["cases"]["base"]["totals"]["inherent_mean_annual_loss"]
    high = output["cases"]["high"]["totals"]["inherent_mean_annual_loss"]
    assert low < base < high
    assert low / base == pytest.approx(0.70, rel=1e-6)
    assert high / base == pytest.approx(1.30, rel=1e-6)


def test_sensitivity_is_deterministic():
    rows = [make_row()]
    first = run_sensitivity(rows, TEST_MARKER, draws=FAST_DRAWS)
    second = run_sensitivity(rows, TEST_MARKER, draws=FAST_DRAWS)
    assert first == second


# --------------------------------------------------------------------------
# Guard tests
# --------------------------------------------------------------------------


def test_simulation_source_contains_no_case_identifiers():
    """Anti-shortcut guard: hard-coded case identifiers cap the project score."""
    source = (Path(__file__).resolve().parent.parent / "simulate.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        r"\bT-[A-Z]\b",
        r"\bVF-\d{3}\b",
        r"\bP-RISK-\d{2}\b",
        r"\bUBI-A8-[0-9A-F]",
        r"\bR-\d{3}\b",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, source), f"identifier matching {pattern} in source"


def test_numpy_is_the_pinned_major_minor_version():
    """The PCG64 stream is version-sensitive; 2.1.x is pinned by the contract."""
    assert np.__version__.startswith("2.1.")