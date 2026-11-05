#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/lifehub
docker compose exec -T lifehub python /app/ops/backup.py
# Optional off-VM copy. Instance-principal policy must be configured first.
# The bucket must be private, with a lifecycle retention policy set in OCI.
if [[ -f /etc/lifehub-backup.conf ]]; then
  source /etc/lifehub-backup.conf
  if [[ -n "${OCI_BACKUP_BUCKET:-}" ]]; then
    latest=$(find /opt/lifehub/data/backups -maxdepth 1 -type f -name 'lifehub-*.tar.fernet' | sort | tail -n 1)
    oci os object put --auth instance_principal --bucket-name "$OCI_BACKUP_BUCKET" \
      --file "$latest" --name "lifehub/$(basename "$latest")" --no-multipart --force >/dev/null
    echo 'Encrypted backup copied to the private OCI bucket.'
  fi
fi
