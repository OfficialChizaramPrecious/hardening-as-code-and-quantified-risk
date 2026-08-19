#!/usr/bin/env bash
#
# Provisioning for the Stage 8 assessment host.
#
# Installs every tool the lifecycle, acceptance suite, and scans depend on.
# The technical assessment contract states that manual preparation absent from
# the runbook is treated as a reproduction failure, so nothing here may be done
# by hand.
#
# Run once on a freshly built host, before lifecycle.sh:
#   bash /project/provision.sh
#
# Idempotent: safe to run repeatedly.

set -euo pipefail

ANSIBLE_POSIX_VERSION="1.5.4"
PROJECT=/project

echo "=== Stage 8 provisioning $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

echo "--- scanner tooling ---"
sudo dnf install -y openscap-scanner scap-security-guide

echo "--- EPEL and Lynis ---"
sudo dnf install -y epel-release
sudo dnf install -y lynis

echo "--- automation ---"
sudo dnf install -y ansible-core python3-pip

echo "--- host test framework ---"
pip3 install --user pytest pytest-testinfra

echo "--- ansible collections (pinned) ---"
ansible-galaxy collection install "ansible.posix:${ANSIBLE_POSIX_VERSION}" --force

echo "--- ansible configuration ---"
# /project is a VirtualBox synced folder and is world-writable, so Ansible
# refuses to read ansible.cfg from it unless ANSIBLE_CONFIG is set explicitly.
if ! grep -q 'ANSIBLE_CONFIG' "${HOME}/.bashrc"; then
  echo "export ANSIBLE_CONFIG=${PROJECT}/ansible.cfg" >> "${HOME}/.bashrc"
fi
export ANSIBLE_CONFIG="${PROJECT}/ansible.cfg"

echo
echo "=== installed versions ==="
cat /etc/os-release | grep PRETTY_NAME
rpm -q openscap-scanner scap-security-guide lynis ansible-core python3-pip
oscap --version | head -1
lynis show version
ansible --version | head -1
python3 -m pytest --version
ansible-galaxy collection list ansible.posix 2>/dev/null | tail -2

echo
echo "=== provisioning complete ==="