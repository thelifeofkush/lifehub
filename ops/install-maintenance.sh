#!/usr/bin/env bash
# Run as root on the Ubuntu cloud VM, after the initial app deployment.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
cd /opt/lifehub
test -f .env
test -f data/lifehub.db
chmod 600 .env
chmod 700 data
install -m 644 ops/systemd/lifehub.service /etc/systemd/system/
for task in health backup; do
  install -m 644 "ops/systemd/lifehub-$task.service" /etc/systemd/system/
  install -m 644 "ops/systemd/lifehub-$task.timer" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable --now docker.service lifehub.service lifehub-health.timer lifehub-backup.timer
systemctl start lifehub-backup.service
echo 'Boot startup, health checks, and daily encrypted backups enabled.'
echo 'Off-VM backup requires OCI bucket configuration; local backups alone do not cover VM loss.'
