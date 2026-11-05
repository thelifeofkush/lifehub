"""Run inside the app container: encrypted consistent SQLite + config backup.

docker compose exec -T lifehub python /app/ops/backup.py
Decrypt with the existing LIFEHUB_ENCRYPTION_KEY kept separately from the VM.
"""
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime, timezone

from cryptography.fernet import Fernet

CONFIG_KEYS = ('TZ', 'DATA_DIR', 'LIFEHUB_USERNAME', 'LIFEHUB_PASSWORD',
               'LIFEHUB_ENCRYPTION_KEY', 'LIFEHUB_PUBLIC_URL', 'PLAID_ENV',
               'PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_SYNC_INTERVAL_SECONDS')


def backup(directory, key, config):
    directory = Path(directory)
    destination = directory / 'backups'
    destination.mkdir(mode=0o700, exist_ok=True)
    name = 'lifehub-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tar.fernet'
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        snapshot = Path(temporary) / 'lifehub.db'
        with closing(sqlite3.connect(directory / 'lifehub.db')) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup integrity check failed.')
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            tar.add(snapshot, arcname='lifehub.db')
            content = json.dumps(config).encode()
            info = tarfile.TarInfo('configuration.json')
            info.size, info.mode = len(content), 0o600
            tar.addfile(info, io.BytesIO(content))
        encrypted = Fernet(key.encode()).encrypt(archive.getvalue())
        path = destination / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(encrypted)
    # Keep at least 30 copies. No deletion until a new backup has succeeded.
    for old in sorted(destination.glob('lifehub-*.tar.fernet'))[:-30]:
        old.unlink()
    return path


if __name__ == '__main__':
    result = backup(os.environ.get('DATA_DIR', '/data'), os.environ['LIFEHUB_ENCRYPTION_KEY'],
                    {key: os.environ[key] for key in CONFIG_KEYS if key in os.environ})
    print('Encrypted backup saved:', result.name)
