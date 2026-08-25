#!/usr/bin/env bash
#
# Unattended lifecycle for Stage 8.
#
# Runs the sequence the brief requires, without intervention:
#
#   baseline tests -> apply -> second apply -> service tests
#   -> rollback -> baseline verification -> reapply -> final scan
#
# The transcript is written to idempotence.log. The second apply must report
# changed=0, and every service check must stay green throughout.
#
# Prerequisites are checked before any stage runs. An earlier version reported
# PASS on stages that could not execute because ansible was absent, which is
# worse than failing: it produced a log that looked green.
#
# Usage, on a provisioned host:
#   bash /project/provision.sh     # once, if not already provisioned
#   bash /project/lifecycle.sh
#
# Exit codes:
#   0  every stage passed
#   1  a stage failed; see the log for the first failure
#   2  a prerequisite is missing; nothing was run

set -uo pipefail

PROJECT=/project
LOG="${PROJECT}/idempotence.log"
CONTRACT=/usr/local/sbin/netforge-service-contract
BASELINE_SSHD="${PROJECT}/before/sshd-effective.txt"
ROLLBACK_SSHD=/tmp/sshd-after-rollback.txt

export ANSIBLE_CONFIG="${PROJECT}/ansible.cfg"

FAILURES=0

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

banner() {
  {
    echo
    echo "==============================================================="
    echo "STAGE: $1"
    echo "TIME:  $(stamp)"
    echo "==============================================================="
  } | tee -a "$LOG"
}

record() { echo "$*" | tee -a "$LOG"; }

fail() {
  record "RESULT: FAIL - $*"
  FAILURES=$((FAILURES + 1))
}

pass() { record "RESULT: PASS - $*"; }

# ---------------------------------------------------------------------------
# Prerequisite gate - run before anything else
# ---------------------------------------------------------------------------

missing=0
check_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "MISSING PREREQUISITE: $1 not found" >&2
    missing=$((missing + 1))
  fi
}
check_file() {
  if [ ! -e "$1" ]; then
    echo "MISSING PREREQUISITE: $1 not found" >&2
    missing=$((missing + 1))
  fi
}

check_command ansible-playbook
check_command python3
check_command curl
check_file "$CONTRACT"
check_file "$BASELINE_SSHD"
check_file "${PROJECT}/site.yml"
check_file "${PROJECT}/rollback.yml"

if ! python3 -m pytest --version >/dev/null 2>&1; then
  echo "MISSING PREREQUISITE: pytest not importable" >&2
  missing=$((missing + 1))
fi

if ! ansible-doc ansible.posix.sysctl >/dev/null 2>&1; then
  echo "MISSING PREREQUISITE: ansible.posix collection not installed" >&2
  missing=$((missing + 1))
fi

if [ "$missing" -gt 0 ]; then
  echo >&2
  echo "${missing} prerequisite(s) missing. Run: bash ${PROJECT}/provision.sh" >&2
  echo "No lifecycle stage was executed." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

run_contract() {
  if sudo "$CONTRACT" >>"$LOG" 2>&1; then
    pass "service contract exit 0"
  else
    fail "service contract did not pass"
  fi
}

# Runs a playbook, appends full output to the log, and echoes the number of
# changed tasks from the recap. Echoes "unknown" if no recap was produced,
# which callers treat as a failure rather than ignoring.
changed_count() {
  local playbook="$1"
  local out rc
  out="$(cd "$PROJECT" && ansible-playbook "$playbook" 2>&1)"
  rc=$?
  echo "$out" >>"$LOG"
  if [ "$rc" -ne 0 ]; then
    echo "unknown"
    return 1
  fi
  echo "$out" | sed -n 's/.*changed=\([0-9]\+\).*/\1/p' | head -1
}

is_number() { [[ "$1" =~ ^[0-9]+$ ]]; }

# ---------------------------------------------------------------------------

: >"$LOG"
record "Stage 8 unattended lifecycle"
record "Started:  $(stamp)"
record "Host:     $(hostname)"
record "OS:       $(sed -n 's/^PRETTY_NAME="\(.*\)"$/\1/p' /etc/os-release)"
record "Marker:   $(curl --fail --silent http://127.0.0.1:8080/ 2>/dev/null || echo UNAVAILABLE)"
record "Ansible:  $(ansible --version | head -1)"
record "Pytest:   $(python3 -m pytest --version 2>&1 | head -1)"
record "Baseline: ${BASELINE_SSHD}"

# --- 1. Baseline tests -----------------------------------------------------
banner "1/8 baseline service tests"
run_contract

# --- 2. Apply --------------------------------------------------------------
banner "2/8 apply hardening"
FIRST=$(changed_count site.yml)
record "changed tasks on first apply: ${FIRST}"
if is_number "$FIRST"; then
  pass "apply completed with ${FIRST} changed task(s)"
else
  fail "apply did not produce a recap"
fi

# --- 3. Second apply - idempotence -----------------------------------------
banner "3/8 second apply (idempotence)"
SECOND=$(changed_count site.yml)
record "changed tasks on second apply: ${SECOND}"
if is_number "$SECOND" && [ "$SECOND" -eq 0 ]; then
  pass "second apply reported changed=0"
else
  fail "second apply reported changed=${SECOND}, expected 0"
fi

# --- 4. Service tests on the hardened host ---------------------------------
banner "4/8 service tests (hardened)"
run_contract
if (cd "$PROJECT" && python3 -m pytest tests/ -q >>"$LOG" 2>&1); then
  pass "acceptance suite green on hardened host"
else
  fail "acceptance suite failed on hardened host"
fi

# --- 5. Rollback -----------------------------------------------------------
banner "5/8 rollback"
RB=$(changed_count rollback.yml)
record "changed tasks on rollback: ${RB}"
if is_number "$RB"; then
  pass "rollback completed with ${RB} changed task(s)"
else
  fail "rollback did not produce a recap"
fi

# --- 6. Baseline verification ----------------------------------------------
# Compares the declared stable facts only. sysctl.txt and listeners.txt are
# excluded because neither can hash identically twice on an unmodified host;
# see before/declared-config.json and the volatility evidence files.
#
# The sshd state is captured ONCE and every sshd assertion reads that capture,
# so the diff and the defect check describe the same instant. Re-invoking
# sshd -T can race the rollback's restart handler and report a state that did
# not exist when the diff was taken.
banner "6/8 baseline verification"
sudo sshd -T >"$ROLLBACK_SSHD" 2>/dev/null

if diff -q "$BASELINE_SSHD" "$ROLLBACK_SSHD" >/dev/null; then
  pass "sshd effective config matches the captured baseline exactly"
else
  fail "sshd effective config differs from baseline"
  diff "$BASELINE_SSHD" "$ROLLBACK_SSHD" >>"$LOG" 2>&1
fi

if grep -q "permitrootlogin yes" "$ROLLBACK_SSHD"; then
  pass "baseline sshd defect restored (permitrootlogin yes)"
else
  fail "baseline sshd defect not restored"
  grep -i permitrootlogin "$ROLLBACK_SSHD" >>"$LOG" 2>&1
fi

WEB_MODE=$(stat -c %a /srv/netforge-service/index.html)
record "web content mode after rollback: ${WEB_MODE} (baseline 666)"
if [ "$WEB_MODE" = "666" ]; then
  pass "web content restored to baseline mode"
else
  fail "web content mode is ${WEB_MODE}, baseline was 666"
fi

if [ ! -f /etc/sysctl.d/60-netforge-hardening.conf ]; then
  pass "hardening sysctl declaration removed, as at baseline"
else
  fail "hardening sysctl file still present after rollback"
fi

run_contract

# --- 7. Reapply ------------------------------------------------------------
banner "7/8 reapply"
RE=$(changed_count site.yml)
record "changed tasks on reapply: ${RE}"
if is_number "$RE" && [ "$RE" -gt 0 ]; then
  pass "reapply restored hardening with ${RE} changed task(s)"
else
  fail "reapply reported changed=${RE}, expected a positive count"
fi

RE2=$(changed_count site.yml)
record "changed tasks on second reapply: ${RE2}"
if is_number "$RE2" && [ "$RE2" -eq 0 ]; then
  pass "reapply is idempotent"
else
  fail "reapply second run reported changed=${RE2}, expected 0"
fi
run_contract

# --- 8. Final acceptance suite ---------------------------------------------
banner "8/8 final acceptance suite"
if (cd "$PROJECT" && python3 -m pytest tests/ -q \
      --junitxml="${PROJECT}/service-results.xml" >>"$LOG" 2>&1); then
  pass "acceptance suite green, service-results.xml regenerated"
else
  fail "final acceptance suite failed"
fi

# ---------------------------------------------------------------------------
banner "SUMMARY"
record "Finished:      $(stamp)"
record "Failed stages: ${FAILURES}"
if [ "$FAILURES" -eq 0 ]; then
  record "LIFECYCLE RESULT: PASS"
  exit 0
else
  record "LIFECYCLE RESULT: FAIL"
  exit 1
fi