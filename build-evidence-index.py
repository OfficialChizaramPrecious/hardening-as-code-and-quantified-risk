"""Generate evidence-index.csv with real hashes computed from the artefacts.

Hashes and collection times are read from the files themselves. Nothing is
placeholdered - if an artefact is missing, the script fails loudly rather than
writing a row that cannot be verified.
"""

import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CLAIMS = [
    ("C-001", "Setup", "The assigned evidence archive was verified against the dashboard SHA-256 before extraction.",
     "raw-evidence/grc-stage-8-shared-b1.tar.gz", "whole file, 11977 bytes",
     "The archive analysed is byte-identical to the one issued for set D5.",
     "Does not prove the contents were interpreted correctly, only that they are unaltered.",
     "high", "The archive could have been re-downloaded after modification.",
     "Retained: the hash matches the dashboard value recorded before extraction."),

    ("C-002", "Baseline", "The OpenSCAP profile was enumerated rather than guessed, and CIS Level 1 Server selected.",
     "before/oscap-info.txt", "Profiles block, id xccdf_org.ssgproject.content_profile_cis_server_l1",
     "The available profile list was read from the installed data stream before selection.",
     "Does not prove Level 1 is the correct choice for every environment, only that the selection was informed.",
     "high", "Running --profile cis would have selected Level 2 Server, visible in the same output.",
     "Retained: the enumerated list shows the bare cis identifier maps to Level 2."),

    ("C-003", "Baseline", "The pre-hardening scan recorded 101 failed and 159 passed rules with zero errors.",
     "before/oscap-results.xml", "rule-result elements, result values fail and pass",
     "The security posture of the host before any remediation was applied.",
     "Does not prove compliance or certification; it is configuration state at one point in time.",
     "high", "A different profile would produce different counts.",
     "Retained: the profile and data stream are pinned and identical in the after-scan."),

    ("C-004", "Baseline", "Lynis independently recorded a hardening index of 66 before remediation.",
     "before/lynis-report.dat", "hardening_index=66",
     "A second, independent tool corroborates the OpenSCAP baseline.",
     "Does not prove the two tools measure the same controls.",
     "medium", "Tool agreement could be coincidental.",
     "Retained as corroboration only; OpenSCAP remains the primary measure."),

    ("C-005", "Baseline", "The web content carried mode 0666 at baseline, a planted world-writable defect.",
     "before/file-permissions.csv", "row for /srv/netforge-service/index.html",
     "The defect HR-003 remediates was present before the role ran.",
     "Does not prove the file was exploited or that mode was the only weakness.",
     "high", "The mode could have been altered between capture and remediation.",
     "Retained: the capture is timestamped and precedes the first apply."),

    ("C-006", "Rollback", "Rollback restores the effective SSH configuration byte-identically to baseline.",
     "before/sshd-effective.txt", "whole file, compared by diff against live sshd -T after rollback",
     "The rollback play returns declared configuration to its recorded baseline state.",
     "Does not prove every host attribute is restored, only the declared comparison set.",
     "high", "A partial restore could coincidentally satisfy a narrow check.",
     "Retained: the comparison is a full-file diff, not a substring match."),

    ("C-007", "Baseline integrity", "sysctl output cannot be hash-compared because it contains values that change on every read.",
     "before/sysctl-volatility-evidence.txt", "two SHA-256 values and the diff of differing keys",
     "Two captures of an unmodified host produce different hashes, naming kernel.random.uuid among the causes.",
     "Does not prove every sysctl key is volatile; six specific keys are named.",
     "high", "The host might have changed between captures.",
     "Retained: the captures were seconds apart with no intervening change, and the diff names only volatile keys."),

    ("C-008", "Baseline integrity", "Listener output cannot be hash-compared because it embeds process identifiers.",
     "before/listeners-volatility-evidence.txt", "two SHA-256 values and the stable projection",
     "ss -tulpn embeds PID and fd values that change on process restart and reboot.",
     "Does not prove the listening ports themselves are unstable; the projection shows they are not.",
     "high", "A service could have restarted between captures.",
     "Retained: the stable projection is identical across both captures."),

    ("C-009", "Baseline integrity", "The rollback comparison set is declared, with volatile artefacts excluded and reasons recorded.",
     "before/declared-config.json", "hash_stable and excluded_from_hash_comparison arrays",
     "Which baseline facts rollback verifies against, and which are excluded.",
     "Does not prove the excluded artefacts are irrelevant, only that they are not hash-comparable.",
     "high", "Excluding artefacts could hide a failed restore.",
     "Retained: each exclusion carries an alternative comparison method."),

    ("C-010", "Judgment", "package_nginx_removed is a false positive on this host and was deliberately not remediated.",
     "before/false-positive-analysis.txt", "rule rationale quotation and service-contract.yml extract",
     "The rule is conditional on the web server not being needed; the service contract requires it.",
     "Does not prove the rule is wrong in general, only that its premise fails here.",
     "high", "The service contract could be satisfied by another web server.",
     "Retained: the contract names the running nginx service and forbids disabling it."),

    ("C-011", "Rollback", "The baseline login banner was recovered from the host, not from the current package.",
     "before/banner-provenance.txt", "comparison of 9.3 host content against rocky-release 9.8 package content",
     "The two sources disagree, and the host state was used.",
     "Does not prove the check-mode diff captured the file perfectly, though it was read by Ansible from the live file.",
     "high", "The newer package could be considered authoritative.",
     "Weakened: the package differs from what this 9.3 host actually carried."),

    ("C-012", "Delta", "The post-hardening scan recorded 86 failed and 174 passed rules with zero errors.",
     "after/oscap-results.xml", "rule-result elements, result values fail and pass",
     "The security posture after the eleven remediations were applied.",
     "Does not prove compliance or certification.",
     "high", "A different scan configuration would invalidate the comparison.",
     "Retained: identical data stream, profile and command as the baseline scan."),

    ("C-013", "Delta", "Fifteen rules moved from fail to pass with zero regressions.",
     "after/delta-reconciliation.txt", "FIXED and REGRESSIONS sections",
     "The measurable effect of the hardening role, rule by rule.",
     "Does not prove the remaining 86 failures are acceptable; two carry documented dispositions and 84 are out of scope.",
     "high", "Rules could have moved for reasons unrelated to the role.",
     "Retained: every fixed rule maps to a designed remediation in lab/remediations.yml."),

    ("C-014", "Delta", "Lynis independently moved from 66 to 70 after remediation.",
     "after/lynis-report.dat", "hardening_index=70",
     "A second tool corroborates the measured improvement.",
     "Does not prove the size of the improvement is significant.",
     "medium", "The index could move for unrelated reasons.",
     "Retained as corroboration only."),

    ("C-015", "Idempotence", "The unattended lifecycle passed all eight stages, with the second apply reporting changed=0.",
     "idempotence.log", "STAGE 3/8 recap and LIFECYCLE RESULT line",
     "The role is idempotent and the full baseline-harden-rollback-reapply cycle completes unattended.",
     "Does not prove idempotence under every possible starting state.",
     "high", "changed=0 could be produced by suppressing change reporting.",
     "Weakened: no task uses changed_when false except a read-only sshd validator."),

    ("C-016", "Service safety", "The host acceptance suite passes 57 tests with zero failures.",
     "service-results.xml", "testsuite element, tests and failures attributes",
     "All four declared service checks and every remediation are verified against live host state.",
     "Does not prove the services behave correctly under load or over time.",
     "high", "Tests could pass by re-running the tool that made the change.",
     "Weakened: the suite reads host state through testinfra and never invokes Ansible."),

    ("C-017", "Risk analysis", "Exactly three treatments were selected under the USD 85,000 budget.",
     "risk-model/output/treatment-selection.json", "selection object, selected_treatment_ids and total_cost",
     "The portfolio produced by the documented optimiser from the submitted inputs.",
     "Does not prove the underlying loss estimates are accurate.",
     "high", "A greedy selection by return per dollar could differ.",
     "Retained: enumeration is exact and cannot be defeated by dependency constraints."),

    ("C-018", "Risk analysis", "The selection is unchanged at both edges of the 30 percent uncertainty band.",
     "risk-model/output/sensitivity.json", "selection_by_case and selection_stable_across_band",
     "The funding decision does not depend on the precision of the loss estimates.",
     "Does not address uneven error across findings, only uniform error.",
     "high", "Stability could be an artefact of a narrow band.",
     "Retained: the band is the 30 percent required by the private overlay."),

    ("C-019", "Risk analysis", "Every risk parameter is derived from the supplied export by a stated rule.",
     "risk-model/input/model-input.json", "rationale field on each risk object",
     "Frequency, loss, control effectiveness and dependency values each trace to evidence in the export.",
     "Does not prove the tiering thresholds are correct, only that they are applied consistently.",
     "medium", "Parameters could have been chosen to produce a desired outcome.",
     "Weakened: the tiers are applied mechanically to export fields, and the sensitivity test shows the ranking is robust."),

    ("C-020", "Decision", "Nine risks are deferred with named owners, acceptance authorities and review triggers.",
     "risk-register.csv", "decision, owner, acceptance_authority and review_trigger columns",
     "Deferral is a recorded decision rather than an omission.",
     "Does not prove the owners have accepted the risks.",
     "high", "Deferral could be a way of avoiding difficult remediations.",
     "Retained: the deferred set includes both CVSS 9.8 findings and excludes none on cost grounds alone."),

    ("C-021", "Remediation", "Every remediation was designed with a precheck verified against the live host before implementation.",
     "lab/remediations.yml", "verify_precheck fields and the design_corrections section",
     "Four design entries were corrected after verification, before any task was written.",
     "Does not prove the corrected designs are complete.",
     "high", "The design could have been written after the fact.",
     "Weakened: the design_corrections section records what was wrong and why."),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def collected(path: Path) -> str:
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


missing = [c[3] for c in CLAIMS if not (ROOT / c[3]).exists()]
if missing:
    print("MISSING ARTEFACTS - nothing written:", file=sys.stderr)
    for m in missing:
        print("  ", m, file=sys.stderr)
    sys.exit(1)

columns = ["claim_id", "report_section", "claim", "artifact_path", "exact_locator",
           "collection_time_utc", "sha256", "proves", "does_not_prove", "confidence",
           "alternative_considered", "disposition"]

with (ROOT / "evidence-index.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(columns)
    for cid, section, claim, path, locator, proves, not_proves, conf, alt, disp in CLAIMS:
        artefact = ROOT / path
        writer.writerow([cid, section, claim, path, locator, collected(artefact),
                         sha256(artefact), proves, not_proves, conf, alt, disp])

print(f"wrote evidence-index.csv with {len(CLAIMS)} claims, all hashes computed")