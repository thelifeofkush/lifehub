import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from contextlib import closing

from cryptography.fernet import Fernet, InvalidToken
from ops.backup import backup


class BackupTests(unittest.TestCase):
    def test_encrypted_backup_restores_consistent_database_and_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            with closing(sqlite3.connect(Path(folder)/'lifehub.db')) as conn:
                conn.execute('CREATE TABLE sample (value TEXT)')
                conn.execute("INSERT INTO sample VALUES ('private test record')")
                conn.commit()
            key=Fernet.generate_key().decode()
            path=backup(folder,key,{'PLAID_SECRET':'private-test-secret'})
            encrypted=path.read_bytes()
            self.assertNotIn(b'private test record',encrypted)
            self.assertNotIn(b'private-test-secret',encrypted)
            with self.assertRaises(InvalidToken):
                Fernet(Fernet.generate_key()).decrypt(encrypted)
            with tarfile.open(fileobj=io.BytesIO(Fernet(key.encode()).decrypt(encrypted))) as archive:
                self.assertEqual(set(archive.getnames()),{'lifehub.db','configuration.json'})
                config=json.load(archive.extractfile('configuration.json'))
                self.assertEqual(config['PLAID_SECRET'],'private-test-secret')
                restored=Path(folder)/'restore.db'
                restored.write_bytes(archive.extractfile('lifehub.db').read())
            with closing(sqlite3.connect(restored)) as conn:
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(conn.execute('SELECT value FROM sample').fetchone()[0],'private test record')
