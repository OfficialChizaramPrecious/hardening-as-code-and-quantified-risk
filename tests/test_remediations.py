"""One test per remediation in the design.

Each test reads host state directly and asserts the desired state declared in
lab/remediations.yml. Where a remediation carries service risk, the test
asserts both that the control applied AND that the service constraint still
holds - because applying the control at the cost of the service is a failure,
not a partial success.

These tests assume a hardened host. Rollback verification lives in the
lifecycle script, which checks baseline restoration at the point in the cycle
where the host is genuinely rolled back.

Privilege and quoting notes, both learned from real failures:

* testinfra's host.file() runs unprivileged. Root-only paths must be read
  through sudo or they appear absent or unreadable. Two cases here:
  /etc/ssh/sshd_config.d (mode 0700) and the persisted sysctl file, which
  ansible.posix.sysctl creates as 0640 root:root.
* host.run() applies %s substitution, so a command containing a literal
  percent sign (such as stat -c %a) must have its arguments inlined.
"""

from __future__ import annotations

import pytest

from conftest import (
    HARDENED_SYSCTL_VALUES,
    HARDENING_SYSCTL_FILE,
    LIMITS_FILE,
    LOGIN_DEFS,
    WEB_INDEX,
)


def read_root_file(host, path: str) -> str:
    """Read a file that only root can read.

    Used for the sysctl declaration and anything else the hardening role
    creates with restrictive ownership.
    """
    result = host.run("sudo cat %s", path)
    assert result.rc == 0, f"could not read {path}: {result.stderr}"
    return result.stdout


# ---------------------------------------------------------------------------
# Design integrity - the suite must cover what was designed
# ---------------------------------------------------------------------------


def test_design_declares_at_least_eight_remediations(remediation_design):
    """The brief requires at least eight scored remediations."""
    assert len(remediation_design["remediations"]) >= 8


def test_every_remediation_declares_rollback_and_test(remediation_design):
    """Guard: no control may be implemented without a rollback and a test."""
    for entry in remediation_design["remediations"]:
        assert entry.get("rollback"), f"{entry['id']} has no rollback"
        assert entry.get("acceptance_test"), f"{entry['id']} has no acceptance test"


def test_design_records_the_service_conflict(remediation_design):
    """Exactly one control is expected to conflict with the declared service
    until parameterised correctly."""
    conflicts = [
        e for e in remediation_design["remediations"] if e.get("service_conflict")
    ]
    assert len(conflicts) == 1, "expected exactly one service-conflict control"


# ---------------------------------------------------------------------------
# HR-001 / HR-002 - SSH
# ---------------------------------------------------------------------------


def test_sshd_root_login_disabled(sshd_effective):
    """HR-001. Baseline shipped PermitRootLogin yes.

    Asserted against the effective configuration, which is what the service
    contract checks and what actually governs the daemon. The SSG rule for
    this control looks for the setting in a specific filename and therefore
    still reports fail; that disposition is recorded in the delta
    reconciliation as a scanner blind spot rather than a control gap.
    """
    assert "permitrootlogin no" in sshd_effective


def test_sshd_password_auth_disabled(sshd_effective):
    """HR-002. Baseline shipped PasswordAuthentication yes."""
    assert "passwordauthentication no" in sshd_effective


def test_sshd_empty_passwords_disabled(sshd_effective):
    """HR-002. Already correct at the effective level at baseline; the scanner
    rule failed on absence of an explicit declaration."""
    assert "permitemptypasswords no" in sshd_effective


def test_sshd_dropin_exists_and_is_root_only(host):
    """The drop-in carries authentication policy and is tightened to 0600.

    Read through sudo because the containing directory is mode 0700. The path
    is inlined because the stat format string contains a percent sign.
    """
    result = host.run(
        "sudo stat -c %a /etc/ssh/sshd_config.d/90-netforge-baseline.conf"
    )
    assert result.rc == 0, f"drop-in not found: {result.stderr}"
    assert result.stdout.strip() == "600"


def test_sshd_config_is_syntactically_valid(host):
    """A drop-in that templates cleanly but fails sshd's own parser would
    break the service on the next restart."""
    result = host.run("sudo sshd -t")
    assert result.rc == 0, f"sshd config invalid: {result.stderr}"


# ---------------------------------------------------------------------------
# HR-003 - Web content permissions (service conflict, parameterised)
# ---------------------------------------------------------------------------


def test_web_content_not_world_writable(host):
    """HR-003. Baseline shipped mode 0666."""
    index = host.file(WEB_INDEX)
    assert index.exists
    assert not index.mode & 0o002, f"still world-writable: {oct(index.mode)}"


def test_web_content_mode_is_exactly_0644(host):
    assert host.file(WEB_INDEX).mode == 0o644


def test_web_content_owner_preserved(host):
    """The control must not be applied by changing ownership away from the
    service account. That would satisfy the scanner and break the service."""
    assert host.file(WEB_INDEX).user == "nginx"


def test_web_service_still_responds_after_permission_change(host):
    """The paired assertion: control applied AND service intact."""
    result = host.run("curl --fail --silent http://127.0.0.1:8080/")
    assert result.rc == 0
    assert "synthetic-service-marker=" in result.stdout


# ---------------------------------------------------------------------------
# HR-004 - Core dumps
# ---------------------------------------------------------------------------


def test_core_dump_hard_limit_set(host):
    """HR-004. Baseline shipped '* soft core unlimited'."""
    limits = host.file(LIMITS_FILE)
    assert limits.exists
    assert "* hard core 0" in limits.content_string


def test_core_dump_limits_file_ends_with_newline(host):
    """A missing final newline can hide the last directive from parsers that
    read the file line by line."""
    assert host.file(LIMITS_FILE).content_string.endswith("\n")


def test_systemd_coredump_storage_disabled(host):
    result = host.run("grep -E '^Storage=' /etc/systemd/coredump.conf")
    assert result.rc == 0
    assert "none" in result.stdout


def test_systemd_coredump_backtraces_disabled(host):
    result = host.run("grep -E '^ProcessSizeMax=' /etc/systemd/coredump.conf")
    assert result.rc == 0
    assert result.stdout.split("=")[1].strip() == "0"


# ---------------------------------------------------------------------------
# HR-005 to HR-008 - Kernel parameters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,expected", sorted(HARDENED_SYSCTL_VALUES.items()))
def test_kernel_parameter_runtime_value(sysctl_values, key, expected):
    """Runtime value correct for every managed key."""
    assert sysctl_values[key] == expected, (
        f"{key} is {sysctl_values[key]}, expected {expected}"
    )


def test_persisted_sysctl_file_is_root_owned(host):
    """ansible.posix.sysctl creates the declaration as 0640 root:root.

    Recorded explicitly so the mode is an asserted property rather than an
    accident of the module's default, and so the sudo reads below are
    justified rather than a workaround.
    """
    result = host.run("sudo stat -c %a:%U:%G /etc/sysctl.d/60-netforge-hardening.conf")
    assert result.rc == 0, f"persisted sysctl file not found: {result.stderr}"
    assert result.stdout.strip() == "640:root:root"


def test_kernel_parameters_are_persisted(host):
    """HR-007 and HR-008 were already correct at runtime at baseline. The
    finding was that nothing declared them, so they would not survive a reboot
    or a conflicting package default. Persistence is the control."""
    content = read_root_file(host, HARDENING_SYSCTL_FILE)
    for key in HARDENED_SYSCTL_VALUES:
        assert key in content, f"{key} not persisted"


def test_accept_redirects_is_persisted_unlike_baseline(host):
    """baseline.sh set accept_redirects=1 with sysctl -w only, never
    persisting it. The remediation both corrects and persists the value."""
    content = read_root_file(host, HARDENING_SYSCTL_FILE).replace(" ", "")
    assert "net.ipv4.conf.all.accept_redirects=0" in content


# ---------------------------------------------------------------------------
# HR-009 - Banners
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/etc/issue", "/etc/issue.net"])
def test_login_banner_present(host, path):
    """HR-009. Baseline carried only the distro release escapes."""
    banner = host.file(path)
    assert banner.exists
    assert "Authorized use only" in banner.content_string


@pytest.mark.parametrize("path", ["/etc/issue", "/etc/issue.net"])
def test_login_banner_mode(host, path):
    assert host.file(path).mode == 0o644


# ---------------------------------------------------------------------------
# HR-010 - umask
# ---------------------------------------------------------------------------


def test_login_defs_umask(host):
    """HR-010. Baseline was 022."""
    result = host.run("grep -E '^\\s*UMASK' %s", LOGIN_DEFS)
    assert result.rc == 0
    assert "027" in result.stdout


# ---------------------------------------------------------------------------
# HR-011 - Firewalld loopback (service conflict, parameterised)
# ---------------------------------------------------------------------------


def test_loopback_is_trusted(firewalld_state):
    """HR-011, first half. Trusting lo is what keeps the loopback path the
    web check depends on."""
    assert "lo" in firewalld_state["trusted_interfaces"]


def test_spoofed_loopback_traffic_is_dropped(firewalld_state):
    """HR-011, second half.

    The benchmark's remediation places these rules in the trusted zone with a
    destination clause: traffic claiming a loopback SOURCE but carrying a
    non-loopback DESTINATION is dropped. Genuine loopback-to-loopback traffic
    is unaffected, which is why the web check survives.
    """
    rules = " ".join(firewalld_state["trusted_rich_rules"]).lower()
    assert "127.0.0.1" in rules, "no ipv4 loopback rule"
    assert "::1" in rules, "no ipv6 loopback rule"
    assert "destination not address" in rules, "destination clause missing"
    assert "drop" in rules


def test_no_blanket_loopback_drop_in_the_external_zone(firewalld_state):
    """Regression guard.

    An earlier implementation dropped 127.0.0.0/8 in the public zone with no
    destination clause. That is a blanket block rather than an anti-spoofing
    measure, and it left the scanner rule failing. If it reappears, this fails.
    """
    rules = " ".join(firewalld_state["public_rich_rules"])
    assert "127.0.0.0/8" not in rules, "superseded blanket drop rule is back"


def test_firewall_control_did_not_break_loopback(host):
    """The paired assertion. Applying the restriction without the destination
    clause blocks 127.0.0.1 and kills the declared service."""
    result = host.run("curl --fail --silent http://127.0.0.1:8080/")
    assert result.rc == 0, "loopback broken by the firewall control"


def test_firewalld_is_running(host):
    assert host.service("firewalld").is_running