#!/usr/bin/env bash
set -euo pipefail

platform="${1:?debian or rocky}"
marker="${NETFORGE_MARKER:-UBI-A8-STAFF-MUST-REPLACE}"
if [ "$platform" = debian ]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx openssh-server auditd chrony python3
  nginx_user=www-data
else
  dnf install -y nginx openssh-server audit chrony python3 policycoreutils-python-utils
  nginx_user=nginx
fi

install -d -m 0755 /srv/netforge-service
printf '%s\n' "synthetic-service-marker=$marker" > /srv/netforge-service/index.html
cat > /etc/nginx/conf.d/netforge.conf <<'EOF'
server {
  listen 8080;
  server_name _;
  root /srv/netforge-service;
  location / { try_files $uri $uri/ =404; }
}
EOF
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
chown -R "$nginx_user":"$nginx_user" /srv/netforge-service

# Deliberate baseline defects. Candidate remediation must preserve the service.
printf '%s\n' 'PermitRootLogin yes' 'PasswordAuthentication yes' > /etc/ssh/sshd_config.d/90-netforge-baseline.conf
chmod 0666 /srv/netforge-service/index.html
printf '%s\n' '* soft core unlimited' > /etc/security/limits.d/90-netforge-baseline.conf
sysctl -w net.ipv4.conf.all.accept_redirects=1
systemctl enable --now nginx sshd auditd chronyd 2>/dev/null || systemctl enable --now nginx ssh auditd chrony

cat > /usr/local/sbin/netforge-service-contract <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
curl --fail --silent http://127.0.0.1:8080/ | grep -F 'synthetic-service-marker='
systemctl is-active nginx
systemctl is-active auditd
systemctl is-active chronyd 2>/dev/null || systemctl is-active chrony
EOF
chmod 0755 /usr/local/sbin/netforge-service-contract
printf '%s\n' "$platform" > /var/lib/netforge-platform
