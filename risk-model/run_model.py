"""Entry point for the Stage 8 quantitative risk model.

Pipeline
--------
1. Load the model input and validate it against the JSON schema.
2. Validate every risk row against the published contract rules.
3. Simulate baseline inherent and residual annual loss per risk.
4. Price each treatment by re-simulating its risk with the post-treatment
   control range and taking the difference in mean residual loss.
5. Select exactly the required number of treatments under the budget.
6. Re-run the whole thing at both edges of the uncertainty band and report
   whether the funded portfolio is stable.

Treatment pricing uses common random numbers. Baseline and treated runs share
the same seed and the same canonical row order, and a uniform draw consumes the
same number of stream values whatever its bounds, so the frequency and loss
draws are bit-identical between runs. The difference therefore isolates the
control change instead of mixing in sampling noise.

Nothing in this module branches on a supplied identifier. Risk, asset and
treatment IDs are carried as data and used only for lookup and ordering.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# stdout must be UTF-8 for paths and symbols to survive redirection on Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from selector import select_portfolio  # noqa: E402
from simulate import (  # noqa: E402
    DRAW_COUNT,
    PROJECT_CODE,
    SENSITIVITY_FACTOR,
    portfolio_totals,
    round_results,
    scale_loss_ranges,
    simulate_rows,
)
from validate import assert_valid  # noqa: E402

SCHEMA_PATH = MODULE_DIR / "schemas" / "model-input.schema.json"

# Fields the simulation reads from a risk row.
SIMULATION_FIELDS = (
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


def load_input(path: Path) -> dict[str, Any]:
    """Read the model input file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_against_schema(document: dict[str, Any], schema_path: Path = SCHEMA_PATH) -> None:
    """Validate the input document structure before any modelling."""
    import jsonschema

    with schema_path.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=document, schema=schema)


def simulation_rows(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project risk records onto exactly the fields the simulation consumes."""
    return [{field: risk[field] for field in SIMULATION_FIELDS} for risk in risks]


def treated_rows(
    rows: list[dict[str, Any]], target_risk_id: str, control_min: float, control_max: float
) -> list[dict[str, Any]]:
    """Copy the row set with one risk's control range replaced.

    The row set keeps its membership and ordering so the generator stream is
    consumed identically; only the control bounds move.
    """
    updated: list[dict[str, Any]] = []
    for row in rows:
        if row["risk_id"] == target_risk_id:
            updated.append({**row, "control_min": control_min, "control_max": control_max})
        else:
            updated.append(dict(row))
    return updated


def assert_reductions_are_additive(treatments: list[dict[str, Any]]) -> None:
    """Reject treatment sets whose reductions cannot legitimately be summed.

    Every treatment is priced against the same baseline, so two treatments
    targeting one risk each claim that risk's full reduction. The selector
    optimises the sum of mean reduction, as the contract requires, and that
    objective is only meaningful when the reductions are independent.

    Mutually exclusive options for a single risk must therefore be expressed
    as one chosen treatment in the input, with the alternatives recorded in the
    decision log rather than offered to the optimiser.
    """
    seen: dict[str, str] = {}
    clashes: list[str] = []
    for treatment in treatments:
        risk_id = treatment["risk_id"]
        if risk_id in seen:
            clashes.append(
                f"{treatment['id']} and {seen[risk_id]} both target {risk_id}"
            )
        else:
            seen[risk_id] = treatment["id"]

    if clashes:
        raise ValueError(
            "treatment reductions would not be additive: "
            + "; ".join(clashes)
            + ". Supply at most one treatment per risk."
        )


def price_treatments(
    treatments: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    baseline_by_risk: dict[str, dict[str, Any]],
    evidence_marker: str,
    draws: int,
    project_code: str,
) -> list[dict[str, Any]]:
    """Compute each treatment's mean annual residual-loss reduction.

    Returns records in the selector's documented interface: id, cost,
    mean_reduction, dependencies.
    """
    assert_reductions_are_additive(treatments)

    priced: list[dict[str, Any]] = []

    for treatment in treatments:
        risk_id = treatment["risk_id"]
        if risk_id not in baseline_by_risk:
            raise ValueError(
                f"treatment {treatment['id']!r} targets unknown risk {risk_id!r}"
            )

        candidate_rows = treated_rows(
            rows,
            risk_id,
            float(treatment["treated_control_min"]),
            float(treatment["treated_control_max"]),
        )
        treated = {
            result["risk_id"]: result
            for result in simulate_rows(candidate_rows, evidence_marker, draws, project_code)
        }

        before = baseline_by_risk[risk_id]["residual"]["mean"]
        after = treated[risk_id]["residual"]["mean"]
        reduction = before - after

        priced.append(
            {
                "id": treatment["id"],
                "risk_id": risk_id,
                "cost": treatment["cost"],
                "dependencies": list(treatment.get("dependencies") or []),
                "mean_reduction": reduction,
                "residual_before": before,
                "residual_after": after,
            }
        )

    return priced


def selector_view(priced: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce priced treatments to the selector's documented interface."""
    return [
        {
            "id": t["id"],
            "cost": t["cost"],
            "mean_reduction": t["mean_reduction"],
            "dependencies": t["dependencies"],
        }
        for t in priced
    ]


def run_case(
    risks: list[dict[str, Any]],
    treatments: list[dict[str, Any]],
    budget: float,
    required_count: int,
    evidence_marker: str,
    draws: int,
    project_code: str,
) -> dict[str, Any]:
    """Simulate, price and select for one set of risk parameters."""
    rows = simulation_rows(risks)
    baseline = simulate_rows(rows, evidence_marker, draws, project_code)
    baseline_by_risk = {result["risk_id"]: result for result in baseline}

    priced = price_treatments(
        treatments, rows, baseline_by_risk, evidence_marker, draws, project_code
    )
    selection = select_portfolio(selector_view(priced), budget, required_count)

    return {
        "baseline": round_results(baseline),
        "totals": portfolio_totals(baseline),
        "treatments": priced,
        "selection": selection,
    }


def build_report(
    document: dict[str, Any],
    evidence_marker: str,
    budget: float,
    draws: int,
    factor: float,
) -> dict[str, Any]:
    """Run the base case and both uncertainty edges, and compare selections."""
    risks = document["risks"]
    treatments = document["treatments"]
    required_count = document.get("required_treatment_count", 3)
    project_code = document.get("project", PROJECT_CODE)

    assert_valid(risks, document.get("assets"))

    cases: dict[str, Any] = {}
    for name, case_risks in (
        ("low", scale_loss_ranges(risks, -factor)),
        ("base", risks),
        ("high", scale_loss_ranges(risks, factor)),
    ):
        cases[name] = run_case(
            case_risks,
            treatments,
            budget,
            required_count,
            evidence_marker,
            draws,
            project_code,
        )

    base_selection = cases["base"]["selection"]["selected_treatment_ids"]
    stable = all(
        cases[name]["selection"]["selected_treatment_ids"] == base_selection
        for name in ("low", "high")
    )

    return {
        "schema_version": "1.0",
        "project": project_code,
        "evidence_marker": evidence_marker,
        "parameters": {
            "draws": draws,
            "budget": budget,
            "required_treatment_count": required_count,
            "sensitivity_factor": factor,
        },
        "base_case": cases["base"],
        "sensitivity": {
            "factor": factor,
            "selection_by_case": {
                name: cases[name]["selection"] for name in ("low", "base", "high")
            },
            "totals_by_case": {
                name: cases[name]["totals"] for name in ("low", "base", "high")
            },
            "selection_stable_across_band": stable,
        },
    }


def write_outputs(report: dict[str, Any], output_dir: Path) -> list[Path]:
    """Write machine-readable outputs with stable key ordering."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    artefacts = {
        "risk-model-results.json": {
            "schema_version": report["schema_version"],
            "project": report["project"],
            "parameters": report["parameters"],
            "risks": report["base_case"]["baseline"],
            "totals": report["base_case"]["totals"],
        },
        "treatment-selection.json": {
            "schema_version": report["schema_version"],
            "parameters": report["parameters"],
            "priced_treatments": report["base_case"]["treatments"],
            "selection": report["base_case"]["selection"],
        },
        "sensitivity.json": report["sensitivity"],
    }

    for name, payload in artefacts.items():
        path = output_dir / name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        written.append(path)

    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stage 8 quantitative risk model.")
    parser.add_argument("--input", type=Path, required=True, help="model input JSON")
    parser.add_argument("--output-dir", type=Path, default=MODULE_DIR / "output")
    parser.add_argument("--marker", help="evidence marker; overrides the input file")
    parser.add_argument("--budget", type=float, help="treatment budget; overrides the input file")
    parser.add_argument("--draws", type=int, default=DRAW_COUNT)
    parser.add_argument("--sensitivity-factor", type=float, default=SENSITIVITY_FACTOR)
    parser.add_argument("--skip-schema", action="store_true", help="skip JSON schema validation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    document = load_input(args.input)

    if not args.skip_schema:
        validate_against_schema(document)

    evidence_marker = args.marker or document.get("evidence_marker")
    if not evidence_marker:
        raise SystemExit("evidence marker missing: pass --marker or set it in the input file")

    budget = args.budget if args.budget is not None else document.get("budget")
    if budget is None:
        raise SystemExit("budget missing: pass --budget or set it in the input file")

    report = build_report(
        document, evidence_marker, float(budget), args.draws, args.sensitivity_factor
    )
    written = write_outputs(report, args.output_dir)

    selection = report["base_case"]["selection"]
    print(f"risks simulated      : {report['base_case']['totals']['rows_simulated']}")
    print(f"draws per risk       : {args.draws}")
    print(f"inherent mean ALE    : {report['base_case']['totals']['inherent_mean_annual_loss']:,.2f}")
    print(f"residual mean ALE    : {report['base_case']['totals']['residual_mean_annual_loss']:,.2f}")
    print(f"budget               : {budget:,.2f}")
    print(f"funded treatments    : {', '.join(selection['selected_treatment_ids']) or '(none)'}")
    print(f"portfolio cost       : {selection['total_cost']:,.2f}")
    print(f"modelled reduction   : {selection['mean_reduction']:,.2f}")
    print(f"selection status     : {selection['validation']}")
    print(
        "sensitivity          : "
        f"{'stable' if report['sensitivity']['selection_stable_across_band'] else 'UNSTABLE'} "
        f"at +/-{int(args.sensitivity_factor * 100)}%"
    )
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())