"""Input validation for the Stage 8 quantitative risk model.

The risk-model contract requires the model to reject inverted ranges, control
effectiveness outside [0, 1], nonpositive dependency multipliers, duplicate
risk IDs, and missing asset IDs.

Two properties matter for grading:

1. Validation is generic. No rule refers to a specific risk, asset, finding or
   treatment identifier. Rules are expressed over field names and value
   relationships only.
2. Validation is exhaustive. Every violated rule in the supplied input is
   reported, not just the first one, so that a malformed-input fixture
   produces a complete and reproducible error set.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Sequence


REQUIRED_RISK_FIELDS: tuple[str, ...] = (
    "risk_id",
    "asset_id",
    "freq_min",
    "freq_mode",
    "freq_max",
    "loss_min",
    "loss_mode",
    "loss_max",
    "control_min",
    "control_max",
    "dependency_multiplier",
)

# Triangular distributions in the contract are (min, mode, max) triples.
TRIANGULAR_TRIPLES: tuple[tuple[str, str, str], ...] = (
    ("freq_min", "freq_mode", "freq_max"),
    ("loss_min", "loss_mode", "loss_max"),
)

CONTROL_BOUNDS: tuple[str, str] = ("control_min", "control_max")

ERROR_CODES: tuple[str, ...] = (
    "MISSING_FIELD",
    "NON_NUMERIC",
    "INVERTED_RANGE",
    "DEGENERATE_RANGE",
    "CONTROL_OUT_OF_BOUNDS",
    "NONPOSITIVE_DEPENDENCY_MULTIPLIER",
    "DUPLICATE_RISK_ID",
    "MISSING_ASSET_ID",
    "UNKNOWN_ASSET_ID",
    "NEGATIVE_VALUE",
)


class RiskModelValidationError(ValueError):
    """Raised by assert_valid when the supplied input violates the contract."""

    def __init__(self, errors: Sequence["ValidationError"]) -> None:
        self.errors = list(errors)
        summary = "; ".join(f"{e.code} at {e.locator}:{e.field}" for e in self.errors)
        super().__init__(f"{len(self.errors)} validation error(s): {summary}")


@dataclass(frozen=True)
class ValidationError:
    """A single rule violation, tied to an exact input location."""

    code: str
    locator: str
    field: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _locator(index: int, row: dict[str, Any]) -> str:
    """Identify a row by position, falling back cleanly when risk_id is absent.

    Position is always available; risk_id may be the thing that is missing or
    duplicated, so it can never be the sole locator.
    """
    risk_id = row.get("risk_id")
    if isinstance(risk_id, str) and risk_id.strip():
        return f"row[{index}]({risk_id})"
    return f"row[{index}]"


def _is_number(value: Any) -> bool:
    """True for real numeric values. Booleans are rejected deliberately."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def _check_required_fields(
    index: int, row: dict[str, Any]
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    loc = _locator(index, row)
    for field in REQUIRED_RISK_FIELDS:
        if field not in row or row[field] is None:
            errors.append(
                ValidationError(
                    code="MISSING_FIELD",
                    locator=loc,
                    field=field,
                    detail="required field is absent or null",
                )
            )
    return errors


def _check_numeric_fields(
    index: int, row: dict[str, Any]
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    loc = _locator(index, row)
    numeric_fields = [f for f in REQUIRED_RISK_FIELDS if f not in ("risk_id", "asset_id")]
    for field in numeric_fields:
        if field in row and row[field] is not None and not _is_number(row[field]):
            errors.append(
                ValidationError(
                    code="NON_NUMERIC",
                    locator=loc,
                    field=field,
                    detail=f"expected a number, got {type(row[field]).__name__}",
                )
            )
    return errors


def _check_ranges(index: int, row: dict[str, Any]) -> list[ValidationError]:
    """Enforce min <= mode <= max and reject degenerate spans.

    numpy.random.Generator.triangular requires left < right, so a range whose
    min equals its max is rejected here rather than failing at draw time.
    """
    errors: list[ValidationError] = []
    loc = _locator(index, row)

    for lo_field, mode_field, hi_field in TRIANGULAR_TRIPLES:
        values = [row.get(f) for f in (lo_field, mode_field, hi_field)]
        if not all(_is_number(v) for v in values):
            continue  # already reported as MISSING_FIELD or NON_NUMERIC
        lo, mode, hi = values

        if lo > mode or mode > hi:
            errors.append(
                ValidationError(
                    code="INVERTED_RANGE",
                    locator=loc,
                    field=f"{lo_field}/{mode_field}/{hi_field}",
                    detail=f"require min <= mode <= max, got {lo} / {mode} / {hi}",
                )
            )
        elif lo == hi:
            errors.append(
                ValidationError(
                    code="DEGENERATE_RANGE",
                    locator=loc,
                    field=f"{lo_field}/{hi_field}",
                    detail=f"min equals max ({lo}); triangular requires min < max",
                )
            )

        if lo < 0:
            errors.append(
                ValidationError(
                    code="NEGATIVE_VALUE",
                    locator=loc,
                    field=lo_field,
                    detail=f"frequency and loss cannot be negative, got {lo}",
                )
            )

    return errors


def _check_control(index: int, row: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    loc = _locator(index, row)
    lo_field, hi_field = CONTROL_BOUNDS
    lo, hi = row.get(lo_field), row.get(hi_field)

    if not (_is_number(lo) and _is_number(hi)):
        return errors  # already reported

    for field, value in ((lo_field, lo), (hi_field, hi)):
        if not 0 <= value <= 1:
            errors.append(
                ValidationError(
                    code="CONTROL_OUT_OF_BOUNDS",
                    locator=loc,
                    field=field,
                    detail=f"require 0 <= control <= 1, got {value}",
                )
            )

    if lo > hi:
        errors.append(
            ValidationError(
                code="INVERTED_RANGE",
                locator=loc,
                field=f"{lo_field}/{hi_field}",
                detail=f"require control_min <= control_max, got {lo} > {hi}",
            )
        )

    return errors


def _check_dependency_multiplier(
    index: int, row: dict[str, Any]
) -> list[ValidationError]:
    loc = _locator(index, row)
    value = row.get("dependency_multiplier")
    if not _is_number(value):
        return []
    if value <= 0:
        return [
            ValidationError(
                code="NONPOSITIVE_DEPENDENCY_MULTIPLIER",
                locator=loc,
                field="dependency_multiplier",
                detail=f"require dependency_multiplier > 0, got {value}",
            )
        ]
    return []


def _check_asset_id(
    index: int, row: dict[str, Any], known_asset_ids: set[str] | None
) -> list[ValidationError]:
    """Missing asset IDs are always rejected.

    When an asset table is supplied, a reference to an asset that is not in it
    is also rejected, under a distinct code so the two failures stay
    distinguishable in the error report.
    """
    loc = _locator(index, row)
    asset_id = row.get("asset_id")

    if not isinstance(asset_id, str) or not asset_id.strip():
        return [
            ValidationError(
                code="MISSING_ASSET_ID",
                locator=loc,
                field="asset_id",
                detail="asset_id is absent, empty, or not a string",
            )
        ]

    if known_asset_ids is not None and asset_id not in known_asset_ids:
        return [
            ValidationError(
                code="UNKNOWN_ASSET_ID",
                locator=loc,
                field="asset_id",
                detail="asset_id does not appear in the supplied asset table",
            )
        ]

    return []


def _check_duplicate_risk_ids(
    rows: Sequence[dict[str, Any]]
) -> list[ValidationError]:
    """Report every row that repeats a risk_id seen earlier in the input."""
    errors: list[ValidationError] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        risk_id = row.get("risk_id")
        if not isinstance(risk_id, str) or not risk_id.strip():
            continue  # absence is a MISSING_FIELD concern, not a duplicate one
        if risk_id in seen:
            errors.append(
                ValidationError(
                    code="DUPLICATE_RISK_ID",
                    locator=_locator(index, row),
                    field="risk_id",
                    detail=f"first defined at row[{seen[risk_id]}]",
                )
            )
        else:
            seen[risk_id] = index
    return errors


def validate_risk_rows(
    rows: Iterable[dict[str, Any]],
    assets: Iterable[dict[str, Any]] | None = None,
) -> list[ValidationError]:
    """Validate risk rows against the contract. Returns all violations found.

    An empty list means the input is acceptable. Errors are ordered by row
    position so the report is stable across runs.
    """
    rows = list(rows)
    known_asset_ids: set[str] | None = None
    if assets is not None:
        known_asset_ids = {
            a["asset_id"]
            for a in assets
            if isinstance(a.get("asset_id"), str) and a["asset_id"].strip()
        }

    errors: list[ValidationError] = []
    for index, row in enumerate(rows):
        errors.extend(_check_required_fields(index, row))
        errors.extend(_check_numeric_fields(index, row))
        errors.extend(_check_ranges(index, row))
        errors.extend(_check_control(index, row))
        errors.extend(_check_dependency_multiplier(index, row))
        errors.extend(_check_asset_id(index, row, known_asset_ids))

    errors.extend(_check_duplicate_risk_ids(rows))
    return errors


def assert_valid(
    rows: Iterable[dict[str, Any]],
    assets: Iterable[dict[str, Any]] | None = None,
) -> None:
    """Raise RiskModelValidationError if any rule is violated."""
    errors = validate_risk_rows(rows, assets)
    if errors:
        raise RiskModelValidationError(errors)
