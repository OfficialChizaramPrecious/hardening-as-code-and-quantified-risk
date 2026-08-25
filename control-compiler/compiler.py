import argparse
import hashlib
import json
from pathlib import Path

import yaml
import jsonschema


REQUIRED_FIELDS = {
    "id",
    "finding",
    "scanner_ref",
    "verified_baseline",
    "desired_state",
    "verify_precheck",
    "change",
    "rollback",
    "acceptance_test",
    "expected_scanner_effect",
}


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Remediation file must contain an object")

    return data


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_against_schema(data, schema):
    jsonschema.validate(instance=data, schema=schema)


def validate_remediations(remediations):
    if not isinstance(remediations, list):
        raise ValueError("'remediations' must be a list")

    seen = set()

    for remediation in remediations:
        if not isinstance(remediation, dict):
            raise ValueError("Each remediation must be an object")

        missing = REQUIRED_FIELDS - remediation.keys()

        if missing:
            raise ValueError(
                f"{remediation.get('id', 'UNKNOWN')}: "
                f"missing fields: {', '.join(sorted(missing))}"
            )

        remediation_id = remediation["id"]

        if remediation_id in seen:
            raise ValueError(
                f"Duplicate remediation ID: {remediation_id}"
            )

        seen.add(remediation_id)

        if not remediation_id.startswith("HR-"):
            raise ValueError(
                f"Invalid remediation ID: {remediation_id}"
            )


def build_reason_codes(remediation):
    """
    Reason codes are derived from declared control metadata.
    They do not alter the source remediation design.
    """

    codes = ["DECLARED_REMEDIATION"]

    if remediation.get("planted_defect") is True:
        codes.append("PLANTED_DEFECT")

    if remediation.get("service_conflict") is True:
        codes.append("SERVICE_CONFLICT")

    return codes


def build_dependencies(remediation):
    """
    Preserve explicitly declared dependencies if a future compatible
    remediation source provides them. Current remediation schema does
    not require a dependency field, so the current controls compile
    with an empty dependency list.
    """

    dependencies = remediation.get("dependencies", [])

    if dependencies is None:
        return []

    if not isinstance(dependencies, list):
        raise ValueError(
            f"{remediation['id']}: dependencies must be a list"
        )

    return dependencies


def compile_control(remediation, sequence):
    """
    Convert one declarative remediation into the portable compiled
    control representation.

    The original remediation information is retained so the generated
    plan remains traceable to lab/remediations.yml.
    """

    return {
        "sequence": sequence,
        "id": remediation["id"],
        "finding": remediation["finding"],

        "reason_codes": build_reason_codes(remediation),

        "preconditions": [
            remediation["verify_precheck"]
        ],

        "exact_change": remediation["change"],

        "handler": remediation.get("handler", ""),

        "validation": [
            remediation["acceptance_test"]
        ],

        "rollback": remediation["rollback"],

        "dependencies": build_dependencies(remediation),

        "desired_state": remediation["desired_state"],

        "verified_baseline": remediation["verified_baseline"],

        "scanner_reference": remediation["scanner_ref"],

        "source": remediation.get("source"),

        "service_risk": remediation.get("service_risk", ""),

        "parameters": remediation.get("parameters", {}),

        "expected_scanner_effect": remediation[
            "expected_scanner_effect"
        ],
    }


def compile_plan(remediations):
    compiled_controls = []

    for sequence, remediation in enumerate(remediations, start=1):
        compiled_controls.append(
            compile_control(remediation, sequence)
        )

    return {
        "schema_version": "1.0",
        "compiler": "GRC-A4-hardening-compiler",
        "plan_type": "declarative-hardening-plan",
        "execution_model": (
            "ordered-precheck-change-validation-rollback"
        ),
        "remediation_count": len(compiled_controls),
        "remediations": compiled_controls,
    }


def calculate_sha256(path):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compile GRC-A4 declarative hardening "
            "remediations into an ordered plan."
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default="lab/remediations.yml",
    )

    parser.add_argument(
        "-s",
        "--schema",
        default="control-schema/remediation.schema.json",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="control-compiler/compiled-plan.json",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    schema_path = Path(args.schema)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Remediation file not found: {input_path}"
        )

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}"
        )

    data = load_yaml(input_path)
    schema = load_schema(schema_path)

    # First prove that the source file satisfies the versioned schema.
    validate_against_schema(data, schema)

    remediations = data.get("remediations", [])

    # Additional compiler-level checks.
    validate_remediations(remediations)

    compiled = compile_plan(remediations)

    # Add provenance information without changing the source file.
    compiled["source"] = {
        "file": str(input_path).replace("\\", "/"),
        "sha256": calculate_sha256(input_path),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(compiled, f, indent=2)
        f.write("\n")

    print(
        f"COMPILE PASSED: "
        f"{len(remediations)} remediations compiled"
    )

    print(
        "Schema validation: PASSED"
    )

    print(
        f"Source SHA-256: "
        f"{compiled['source']['sha256']}"
    )

    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()