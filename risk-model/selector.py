"""Treatment portfolio selection for the Stage 8 quantitative risk model.

The risk-model contract requires the selector to choose exactly three options
whose total cost does not exceed the supplied budget and whose dependencies
are satisfied, optimising the sum of mean annual residual-loss reduction. If
two portfolios differ by less than one cent, the lexicographically smaller
ordered treatment-ID list wins.

This module is deliberately separate from the simulation engine. The published
fixtures supply `mean_reduction` per treatment directly and never exercise the
Monte Carlo path, so selection must be reachable through its own documented
interface with pre-computed reductions.

No rule here refers to a specific treatment, risk, asset or finding
identifier. Identifiers are data, never control flow.

Note: this module is named `selector`, not `select`, because `select` is a
Python standard library module and would be shadowed by that filename.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_EVEN
from itertools import combinations
from typing import Any, Iterable, Sequence

# Two portfolios whose objective values differ by less than this are treated as
# tied, and resolved by the lexicographic rule instead.
TIE_TOLERANCE = Decimal("0.01")

DEFAULT_REQUIRED_COUNT = 3

SELECTION_ERROR_CODES: tuple[str, ...] = (
    "MISSING_TREATMENT_FIELD",
    "NON_NUMERIC_TREATMENT_FIELD",
    "DUPLICATE_TREATMENT_ID",
    "NEGATIVE_COST",
    "UNKNOWN_DEPENDENCY",
    "SELF_DEPENDENCY",
    "INVALID_BUDGET",
    "INVALID_REQUIRED_COUNT",
)

REQUIRED_TREATMENT_FIELDS: tuple[str, ...] = ("id", "cost", "mean_reduction")


class TreatmentSelectionError(ValueError):
    """Raised when treatment input violates the selection contract."""

    def __init__(self, errors: Sequence["SelectionError"]) -> None:
        self.errors = list(errors)
        summary = "; ".join(f"{e.code} at {e.locator}" for e in self.errors)
        super().__init__(f"{len(self.errors)} selection error(s): {summary}")


@dataclass(frozen=True)
class SelectionError:
    """A single input violation, tied to an exact location."""

    code: str
    locator: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _is_number(value: Any) -> bool:
    """True for real numeric values. Booleans are rejected deliberately."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, Decimal))


def _to_decimal(value: Any) -> Decimal:
    """Convert a numeric input to Decimal without inheriting float noise."""
    return Decimal(str(value))


def round_currency(value: Decimal | float) -> float:
    """Round a currency figure to two places using round-half-even.

    The contract rounds only final currency outputs, so this is applied at the
    reporting boundary rather than during accumulation.
    """
    quantised = _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return float(quantised)


def _locator(index: int, treatment: dict[str, Any]) -> str:
    """Identify a treatment by position, appending its id when usable."""
    identifier = treatment.get("id")
    if isinstance(identifier, str) and identifier.strip():
        return f"treatment[{index}]({identifier})"
    return f"treatment[{index}]"


def validate_treatments(
    treatments: Sequence[dict[str, Any]],
    budget: Any,
    required_count: int = DEFAULT_REQUIRED_COUNT,
) -> list[SelectionError]:
    """Validate the selection inputs. Returns every violation found."""
    errors: list[SelectionError] = []

    if not _is_number(budget) or budget < 0:
        errors.append(
            SelectionError(
                code="INVALID_BUDGET",
                locator="budget",
                detail=f"budget must be a non-negative number, got {budget!r}",
            )
        )

    if (
        not isinstance(required_count, int)
        or isinstance(required_count, bool)
        or required_count < 1
    ):
        errors.append(
            SelectionError(
                code="INVALID_REQUIRED_COUNT",
                locator="required_treatment_count",
                detail=f"required count must be a positive integer, got {required_count!r}",
            )
        )

    seen: dict[str, int] = {}
    for index, treatment in enumerate(treatments):
        loc = _locator(index, treatment)

        for field in REQUIRED_TREATMENT_FIELDS:
            if field not in treatment or treatment[field] is None:
                errors.append(
                    SelectionError(
                        code="MISSING_TREATMENT_FIELD",
                        locator=loc,
                        detail=f"required field '{field}' is absent or null",
                    )
                )

        for field in ("cost", "mean_reduction"):
            value = treatment.get(field)
            if value is not None and not _is_number(value):
                errors.append(
                    SelectionError(
                        code="NON_NUMERIC_TREATMENT_FIELD",
                        locator=loc,
                        detail=f"'{field}' must be numeric, got {type(value).__name__}",
                    )
                )

        cost = treatment.get("cost")
        if _is_number(cost) and cost < 0:
            errors.append(
                SelectionError(
                    code="NEGATIVE_COST",
                    locator=loc,
                    detail=f"cost cannot be negative, got {cost}",
                )
            )

        identifier = treatment.get("id")
        if isinstance(identifier, str) and identifier.strip():
            if identifier in seen:
                errors.append(
                    SelectionError(
                        code="DUPLICATE_TREATMENT_ID",
                        locator=loc,
                        detail=f"first defined at treatment[{seen[identifier]}]",
                    )
                )
            else:
                seen[identifier] = index

    known_ids = set(seen)
    for index, treatment in enumerate(treatments):
        loc = _locator(index, treatment)
        identifier = treatment.get("id")
        for dependency in treatment.get("dependencies") or []:
            if dependency == identifier:
                errors.append(
                    SelectionError(
                        code="SELF_DEPENDENCY",
                        locator=loc,
                        detail="a treatment cannot depend on itself",
                    )
                )
            elif dependency not in known_ids:
                errors.append(
                    SelectionError(
                        code="UNKNOWN_DEPENDENCY",
                        locator=loc,
                        detail=f"dependency '{dependency}' is not a supplied treatment",
                    )
                )

    return errors


def _dependencies_satisfied(
    portfolio: Sequence[dict[str, Any]], selected_ids: frozenset[str]
) -> bool:
    """A portfolio is valid only if every dependency of every member is inside it.

    Dependencies are read from the data, never matched against a literal.
    """
    for treatment in portfolio:
        for dependency in treatment.get("dependencies") or []:
            if dependency not in selected_ids:
                return False
    return True


def select_portfolio(
    treatments: Iterable[dict[str, Any]],
    budget: Any,
    required_count: int = DEFAULT_REQUIRED_COUNT,
) -> dict[str, Any]:
    """Choose exactly `required_count` treatments maximising mean reduction.

    Returns a result mapping with the selected IDs in sorted order, the total
    cost, the achieved mean reduction, and a validation status. Raises
    TreatmentSelectionError if the inputs violate the contract.

    Selection enumerates every candidate combination. With a required count of
    three this is exact and fast, and unlike a greedy ratio heuristic it cannot
    be defeated by dependency chains.
    """
    treatments = list(treatments)

    errors = validate_treatments(treatments, budget, required_count)
    if errors:
        raise TreatmentSelectionError(errors)

    budget_dec = _to_decimal(budget)

    # Sorting by id first makes enumeration order deterministic, so the
    # lexicographic tie-break is reproducible regardless of input ordering.
    ordered = sorted(treatments, key=lambda t: t["id"])

    best_ids: list[str] | None = None
    best_cost = Decimal("0")
    best_reduction = Decimal("0")

    for portfolio in combinations(ordered, required_count):
        total_cost = sum((_to_decimal(t["cost"]) for t in portfolio), Decimal("0"))
        if total_cost > budget_dec:
            continue

        selected_ids = frozenset(t["id"] for t in portfolio)
        if not _dependencies_satisfied(portfolio, selected_ids):
            continue

        reduction = sum(
            (_to_decimal(t["mean_reduction"]) for t in portfolio), Decimal("0")
        )
        candidate_ids = sorted(selected_ids)

        if best_ids is None:
            best_ids, best_cost, best_reduction = candidate_ids, total_cost, reduction
            continue

        difference = reduction - best_reduction
        if difference >= TIE_TOLERANCE:
            best_ids, best_cost, best_reduction = candidate_ids, total_cost, reduction
        elif abs(difference) < TIE_TOLERANCE and candidate_ids < best_ids:
            best_ids, best_cost, best_reduction = candidate_ids, total_cost, reduction

    if best_ids is None:
        return {
            "selected_treatment_ids": [],
            "total_cost": 0.0,
            "mean_reduction": 0.0,
            "validation": "infeasible",
        }

    return {
        "selected_treatment_ids": best_ids,
        "total_cost": round_currency(best_cost),
        "mean_reduction": round_currency(best_reduction),
        "validation": "valid",
    }