#!/usr/bin/env bash
# Run only on the new Ubuntu cloud server, with sudo.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
source /etc/os-release
if [[ "$ID" != ubuntu ]]; then echo 'This setup targets Ubuntu.' >&2; exit 1; fi
apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# Official Tailscale installer; download to a file so a failed download cannot
# silently execute a partial pipeline.
installer=$(mktemp)
trap 'rm -f "$installer"' EXIT
curl -fsSL https://tailscale.com/install.sh -o "$installer"
sh "$installer"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now docker tailscaled
echo 'Docker, Tailscale, and Ubuntu unattended security updates are installed.'
echo 'Automatic OS reboots and automatic application code deployments are not enabled.'
