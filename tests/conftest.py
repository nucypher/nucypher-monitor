import os
import sqlite3
import tempfile

import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture(scope='function')
def sqlite_db_conn():
    db_conn = Mock()
    db_conn.__enter__ = db_conn
    db_conn.__exit__ = db_conn

    sqlite3.connect = MagicMock(return_value=db_conn)

    yield db_conn


@pytest.fixture(scope="function")
def tempfile_path():
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
