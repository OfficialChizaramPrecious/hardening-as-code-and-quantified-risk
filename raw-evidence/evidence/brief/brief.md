# GRC Advanced 4: Host Hardening and Business Risk

## Window and scoring

Monday 09:00 WAT to Friday 18:10 WAT. No revision. Recorded defense. 100 points: baseline integrity 15,
remediation and service safety 25, measurable delta 15, risk analysis 25,
investment/deferral judgment 10, defense 10.

## Supported host paths

Use the assigned fresh Debian 12 or Rocky Linux 9 VM. Run Lynis from a recorded
release. Install OpenSCAP and the distribution's SCAP Security Guide content,
list available profiles, and choose the profile specified in the private
assignment. Do not run a guessed `--profile cis` against a wildcard path. Record
the exact data-stream path and profile ID.

## Required work

1. Baseline the host, application acceptance test, packages, listening ports,
   Lynis output, and OpenSCAP result.
2. Select at least eight findings. For each, record risk, dependency, exact
   change, rollback, and expected control effect.
3. Apply changes one at a time, rerun service tests, and record regressions.
4. Re-scan with the same profile and compare like for like.
5. Combine host findings with the provided vulnerability scan into a risk
   register. Fund exactly three treatments under the supplied budget.

Automated scan output is evidence input, not a certification. ALE estimates
must show uncertain inputs and ranges.

## Automation and quantitative tests

Implement the hardening and rollback as Ansible roles. The unattended sequence
must run baseline tests, apply, second apply, service tests, rollback, baseline
hash verification, reapply, and final scan. The second apply must report zero
changes. Rollback must restore declared configuration and service hashes. One
scanner item is a false positive and one remediation conflicts with the service
until correctly parameterized; the acceptance suite must distinguish both.

Implement the risk calculation as a tested program with explicit asset
criticality, control effectiveness, loss ranges, dependencies, and residual
risk inputs. It may not branch on supplied finding IDs. It must match published
calculation fixtures and a hidden asset/budget fixture. At least eight expected
security deltas must occur with zero service regressions. During defense, staff
select one Ansible role change for implementation, rollback, and retest.

## Mission interface and handoff

- **You receive:** signed Debian/Rocky baselines, scan data, service contract, treatment budget, risk fixtures, and Stage 7 findings.
- **You build:** portable hardening automation, rollback, evidence collection, and quantified treatment selection connected to audited findings.
- **You prove:** security deltas and service preservation separately, with before/after locators and no branching on supplied finding IDs.
- **You hand forward:** residual risks, implemented/declined treatments, evidence deltas, owners, and accepted limitations for Stage 9 governance.
