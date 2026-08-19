"""Proof that the identified false positive was deliberately left unremediated.

The brief requires the acceptance suite to distinguish the false positive from
the service conflict. Both look like unaddressed scanner failures from the
outside; they are different judgments and the suite must say so.

HR-FP-001 - package_nginx_removed
    The rule's own rationale is conditional: "If there is no need to make the
    web server software available, removing it provides a safeguard against
    its activation." On this host service-contract.yml requires nginx serving
    on 8080, and disabling it is a listed forbidden regression. The premise
    fails, so the rule does not apply. No parameterisation resolves it, which
    is what distinguishes it from HR-011.

Without these tests, a reviewer cannot tell a considered deferral from an
incomplete implementation.
"""

from __future__ import annotations

from pathlib import Path

FALSE_POSITIVE_EVIDENCE = Path("/project/before/false-positive-analysis.txt")
HARDENING_DEFAULTS = Path("/project/hardening-role/defaults/main.yml")
HARDENING_TASKS = Path("/project/hardening-role/tasks/main.yml")


# ---------------------------------------------------------------------------
# The design records the decision
# ---------------------------------------------------------------------------


def test_design_declares_exactly_one_false_positive(remediation_design):
    """One scanner item is expected to be a false positive."""
    assert len(remediation_design["false_positives"]) == 1


def test_false_positive_is_marked_not_remediated(remediation_design):
    entry = remediation_design["false_positives"][0]
    assert entry["disposition"] == "NOT REMEDIATED"


def test_false_positive_records_the_rule_rationale(remediation_design):
    """The argument rests on the rule's own stated condition, not on the
    inconvenience of remediating it."""
    entry = remediation_design["false_positives"][0]
    assert entry.get("rule_rationale"), "no rule rationale recorded"
    assert "no need" in entry["rule_rationale"].lower()


def test_false_positive_explains_why_parameterisation_cannot_resolve_it(
    remediation_design,
):
    """This is the distinction from the service-conflict control, where
    correct parameters do resolve the conflict."""
    entry = remediation_design["false_positives"][0]
    assert entry.get("why_no_parameterisation"), "no parameterisation analysis"


def test_false_positive_expects_to_remain_failing(remediation_design):
    """The after-scan must still show this rule failing. A reviewer comparing
    before and after needs to know that was intended."""
    entry = remediation_design["false_positives"][0]
    assert "fail" in entry["expected_after_scan"].lower()


def test_false_positive_evidence_file_exists():
    """The analysis must be a submitted artefact, not only a design note."""
    assert FALSE_POSITIVE_EVIDENCE.exists()
    content = FALSE_POSITIVE_EVIDENCE.read_text(encoding="utf-8")
    assert "package_nginx_removed" in content
    assert "service-contract.yml" in content


# ---------------------------------------------------------------------------
# The host state matches the decision
# ---------------------------------------------------------------------------


def test_false_positive_nginx_still_installed(host):
    """The decisive assertion. If a later change removed nginx to satisfy the
    scanner, this fails - and so would the declared service."""
    assert host.package("nginx").is_installed


def test_nginx_still_serving_after_all_remediations(host):
    """The reason the rule does not apply: the web server is needed."""
    result = host.run("curl --fail --silent http://127.0.0.1:8080/")
    assert result.rc == 0
    assert "synthetic-service-marker=" in result.stdout


def test_hardening_role_never_removes_nginx():
    """The role declares the intent explicitly rather than leaving it implied
    by absence, so a reader can see the decision in code."""
    defaults = HARDENING_DEFAULTS.read_text(encoding="utf-8")
    assert "netforge_remove_nginx: false" in defaults


def test_no_task_removes_the_nginx_package():
    """Guard against a future edit quietly adding a package-removal task."""
    tasks = HARDENING_TASKS.read_text(encoding="utf-8").lower()
    assert "state: absent" not in tasks or "nginx" not in tasks, (
        "a task may remove the nginx package"
    )


# ---------------------------------------------------------------------------
# The service conflict is a different judgment
# ---------------------------------------------------------------------------


def test_service_conflict_was_resolved_not_deferred(remediation_design, firewalld_state):
    """HR-011 was applied with parameters, unlike the false positive which was
    not applied at all. The suite must distinguish the two outcomes."""
    conflict = next(
        e for e in remediation_design["remediations"] if e.get("service_conflict")
    )
    assert conflict.get("parameters"), "service-conflict control has no parameters"
    assert "lo" in firewalld_state["trusted_interfaces"], (
        "service-conflict control not actually applied"
    )