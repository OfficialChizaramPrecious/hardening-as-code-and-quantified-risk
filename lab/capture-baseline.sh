#!/usr/bin/env bash
set -euo pipefail

out="${1:?output directory}"
mkdir -p "$out"
date -u +%FT%TZ > "$out/captured-at.txt"
uname -a > "$out/uname.txt"
cat /etc/os-release > "$out/os-release.txt"
ss -H -lntup > "$out/listeners.txt"
systemctl list-unit-files --state=enabled --no-pager > "$out/enabled-services.txt"
sshd -T > "$out/sshd-effective.txt"
sysctl -a > "$out/sysctl.txt" 2> "$out/sysctl.stderr"
stat --printf '%n,%a,%U,%G\n' /srv/netforge-service/index.html > "$out/file-permissions.csv"
find "$out" -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > "$out/manifest.sha256"
