"""The four declared service checks from service-contract.yml.

These are the constraint the whole hardening effort operates under. Every one
must stay green through apply, rollback, and reapply. A failure here is a
service regression, which the brief treats as a technical completion failure
regardless of how many controls were applied successfully.

The checks are read from the contract file rather than hard-coded, so the tests
cannot drift from the issued requirement.
"""

from __future__ import annotations

import pytest

from conftest import MARKER_PREFIX


def test_contract_file_declares_four_services(service_contract):
    """Guard: the suite must cover every declared check, not a subset."""
    assert len(service_contract["services"]) == 4
    ids = {s["id"] for s in service_contract["services"]}
    assert ids == {"web", "audit", "time", "ssh-effective"}


def test_web_service_serves_the_marker(host, service_contract):
    """Declared check 'web'.

    The response must contain the synthetic service marker. This is the check
    that a naive file-permission or firewall remediation would break.
    """
    check = next(s for s in service_contract["services"] if s["id"] == "web")
    result = host.run(check["command"])
    assert result.rc == 0, f"web check exited {result.rc}: {result.stderr}"
    assert check["required_contains"] in result.stdout


def test_web_marker_is_not_the_staff_placeholder(host):
    """The host must carry the assigned marker, not baseline.sh's fallback.

    baseline.sh falls back to a placeholder when NETFORGE_MARKER is unset, and
    Vagrant shell provisioners do not inherit the host environment. This test
    fails if the passthrough regressed.
    """
    result = host.run("curl --fail --silent http://127.0.0.1:8080/")
    assert result.rc == 0
    assert MARKER_PREFIX in result.stdout
    assert "STAFF-MUST-REPLACE" not in result.stdout


def test_nginx_is_running(host):
    """The web check depends on nginx. Assert the service directly as well, so
    a failure distinguishes 'service down' from 'content wrong'."""
    assert host.service("nginx").is_running


def test_web_content_is_readable_by_the_service_account(host):
    """The permission remediation must leave nginx able to read the content.

    Owner and mode are asserted together: tightening the mode without keeping
    the owner, or vice versa, breaks the declared service.
    """
    index = host.file("/srv/netforge-service/index.html")
    assert index.exists
    assert index.user == "nginx"
    assert index.mode & 0o004, "content is not readable by the service"


def test_web_content_selinux_context(host):
    """SELinux must allow httpd_t to read the content.

    baseline.sh creates the web root outside any standard location without
    setting a context, which returned HTTP 403 until relabelled (DL-004).
    """
    result = host.run("ls -Z /srv/netforge-service/index.html")
    assert result.rc == 0
    assert "httpd_sys_content_t" in result.stdout


def test_audit_daemon_is_active(host, service_contract):
    """Declared check 'audit'. Disabling audit collection is a forbidden
    regression."""
    check = next(s for s in service_contract["services"] if s["id"] == "audit")
    result = host.run(check["command"])
    assert result.rc == check["required_exit"]


def test_time_synchronisation_is_active(host, service_contract):
    """Declared check 'time'. Removing time synchronisation is a forbidden
    regression."""
    check = next(s for s in service_contract["services"] if s["id"] == "time")
    result = host.run(check["command"])
    assert result.rc == check["required_exit"]


def test_sshd_still_listens_on_the_declared_port(sshd_effective, service_contract):
    """Declared check 'ssh-effective'.

    This is why no remediation moves SSH off port 22, even though several
    hardening guides suggest it.
    """
    check = next(s for s in service_contract["services"] if s["id"] == "ssh-effective")
    assert check["required_contains"] in sshd_effective


def test_supplied_contract_script_passes(host):
    """The host also carries baseline.sh's own contract script at
    /usr/local/sbin/netforge-service-contract. It checks nginx explicitly,
    which service-contract.yml does not. Both are asserted."""
    result = host.run("sudo /usr/local/sbin/netforge-service-contract")
    assert result.rc == 0, f"supplied contract script failed: {result.stderr}"


def test_no_new_listening_ports_beyond_baseline(host, declared_config):
    """Forbidden regression: opening a new listening port.

    Compared against the baseline socket projection recorded in
    declared-config.json. Raw ss output is not compared, because it embeds PIDs
    that change on every reboot.
    """
    result = host.run("sudo ss -tulpn")
    assert result.rc == 0

    current = set()
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 5:
            current.add(f"{fields[0]} {fields[4]}")

    baseline = set(declared_config["baseline_listening_sockets"])
    new_ports = current - baseline
    assert not new_ports, f"new listening sockets appeared: {sorted(new_ports)}"