"""Shared fixtures for the host acceptance suite.

These tests read host state directly through testinfra. They deliberately do
not re-run Ansible: the point is to verify the outcome independently of the
tool that produced it. A test that re-ran the playbook would only prove the
playbook agrees with itself.

Run against the host under test:

    cd /project
    python3 -m pytest molecule-or-testinfra/ -v \
        --junitxml=service-results.xml

Fixture scoping note: testinfra's `host` fixture is module scoped, so any
fixture that depends on it must be module scoped or narrower. Fixtures that
only read files from disk are session scoped, since they never touch the host.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path("/project")
SERVICE_CONTRACT = PROJECT_ROOT / "lab" / "service-contract.yml"
REMEDIATION_DESIGN = PROJECT_ROOT / "lab" / "remediations.yml"
DECLARED_CONFIG = PROJECT_ROOT / "lab" / "before" / "declared-config.json"
BASELINE_DIR = PROJECT_ROOT / "lab" / "before"

# Read from the running service rather than asserted as a literal: the tests
# check that the host serves the marker it was built with, and that it is not
# baseline.sh's fallback placeholder.
MARKER_PREFIX = "synthetic-service-marker="
MARKER_FALLBACK = "STAFF-MUST-REPLACE"

# Kernel parameters the hardening role manages.
MANAGED_SYSCTL_KEYS = (
    "net.ipv4.conf.all.accept_redirects",
    "net.ipv4.conf.default.accept_redirects",
    "net.ipv4.conf.all.send_redirects",
    "net.ipv4.conf.default.send_redirects",
    "kernel.randomize_va_space",
    "net.ipv4.tcp_syncookies",
)

HARDENED_SYSCTL_VALUES = {
    "net.ipv4.conf.all.accept_redirects": "0",
    "net.ipv4.conf.default.accept_redirects": "0",
    "net.ipv4.conf.all.send_redirects": "0",
    "net.ipv4.conf.default.send_redirects": "0",
    "kernel.randomize_va_space": "2",
    "net.ipv4.tcp_syncookies": "1",
}

HARDENING_SYSCTL_FILE = "/etc/sysctl.d/60-netforge-hardening.conf"
WEB_INDEX = "/srv/netforge-service/index.html"
SSH_DROPIN = "/etc/ssh/sshd_config.d/90-netforge-baseline.conf"
LIMITS_FILE = "/etc/security/limits.d/90-netforge-baseline.conf"
LOGIN_DEFS = "/etc/login.defs"


# ---------------------------------------------------------------------------
# File-backed fixtures - session scoped, no host access
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def service_contract() -> dict:
    """The declared service contract issued with the assignment."""
    with SERVICE_CONTRACT.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope="session")
def remediation_design() -> dict:
    """The remediation design, so tests and design cannot drift apart."""
    with REMEDIATION_DESIGN.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope="session")
def declared_config() -> dict:
    """Which baseline facts are compared, and which are excluded as volatile."""
    with DECLARED_CONFIG.open(encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Host-backed fixtures - module scoped, because testinfra's host fixture is
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sshd_effective(host) -> str:
    """Effective sshd configuration.

    sshd -T requires root, so this runs under sudo. Reading the effective
    configuration rather than the file is deliberate: it is what the service
    contract checks, and it accounts for drop-in files.
    """
    result = host.run("sudo sshd -T")
    assert result.rc == 0, f"sshd -T failed: {result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def sysctl_values(host) -> dict:
    """Runtime values for every kernel parameter the role manages."""
    values = {}
    for key in MANAGED_SYSCTL_KEYS:
        result = host.run("sysctl -n %s", key)
        values[key] = result.stdout.strip() if result.rc == 0 else None
    return values


@pytest.fixture(scope="module")
def firewalld_state(host) -> dict:
    """Trusted-zone interfaces and external-zone rich rules."""
    trusted = host.run("sudo firewall-cmd --zone=trusted --list-interfaces")
    rich = host.run("sudo firewall-cmd --zone=public --list-rich-rules")
    return {
        "trusted_interfaces": trusted.stdout.split() if trusted.rc == 0 else [],
        "public_rich_rules": [
            line.strip()
            for line in (rich.stdout.strip().splitlines() if rich.rc == 0 else [])
            if line.strip()
        ],
    }


@pytest.fixture(scope="module")
def listening_sockets(host) -> set:
    """Listening sockets as protocol and address:port only.

    PID and file-descriptor fields are discarded. They change on every process
    restart and on every reboot, including the snapshot restore performed
    during the unattended lifecycle, so raw ss output cannot be compared.
    """
    result = host.run("sudo ss -tulpn")
    assert result.rc == 0, f"ss failed: {result.stderr}"

    sockets = set()
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 5:
            sockets.add(f"{fields[0]} {fields[4]}")
    return sockets