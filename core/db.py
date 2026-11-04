import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def db():
    directory = Path(os.environ.get('DATA_DIR', 'data'))
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / 'lifehub.db', timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
