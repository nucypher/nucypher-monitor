import maya
import pytest
import sqlite3
from unittest.mock import Mock, call, ANY, MagicMock

from monitor.crawler import CrawlerNodeStorage

from constant_sorrow.constants import UNKNOWN_FLEET_STATE


#
# Test CrawlerNodeStorage
#

@pytest.fixture(scope='function')
def sqlite_db_conn():
    db_conn = Mock()
    db_conn.__enter__ = db_conn
    db_conn.__exit__ = db_conn

    sqlite3.connect = MagicMock(return_value=db_conn)

    return db_conn


def test_storage_db_table_init(sqlite_db_conn):
    CrawlerNodeStorage()

    expected = [
        f"DROP TABLE IF EXISTS {CrawlerNodeStorage.STATE_DB_NAME}",
        f"DROP TABLE IF EXISTS {CrawlerNodeStorage.TEACHER_DB_NAME}",
        f"CREATE TABLE {CrawlerNodeStorage.STATE_DB_NAME}",
        f"CREATE TABLE {CrawlerNodeStorage.TEACHER_DB_NAME}",
        f"DROP TABLE IF EXISTS {CrawlerNodeStorage.NODE_DB_NAME}",
        f"CREATE TABLE {CrawlerNodeStorage.NODE_DB_NAME}",
    ]

    call_args_list = sqlite_db_conn.execute.call_args_list
    for idx, execute_call in enumerate(call_args_list):
        assert expected[idx] in execute_call[0][0]


def test_storage_db_clear(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    sqlite_db_conn.reset_mock()
    node_storage.clear()

    db_tables = [CrawlerNodeStorage.NODE_DB_NAME, CrawlerNodeStorage.STATE_DB_NAME, CrawlerNodeStorage.TEACHER_DB_NAME]
    for table in db_tables:
        sqlite_db_conn.execute.assert_any_call(f"DELETE FROM {table}")


def test_storage_db_clear_only_metadata_not_certificates(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    sqlite_db_conn.reset_mock()
    node_storage.clear(metadata=True, certificates=False)

    db_tables = [CrawlerNodeStorage.NODE_DB_NAME, CrawlerNodeStorage.STATE_DB_NAME, CrawlerNodeStorage.TEACHER_DB_NAME]
    for table in db_tables:
        sqlite_db_conn.execute.assert_any_call(f"DELETE FROM {table}")


def test_storage_db_clear_not_metadata(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    sqlite_db_conn.reset_mock()
    node_storage.clear(metadata=False, certificates=True)
    sqlite_db_conn.execute.assert_not_called()

    sqlite_db_conn.reset_mock()
    node_storage.clear(metadata=False, certificates=False)
    sqlite_db_conn.execute.assert_not_called()


def test_storage_store_node_metadata(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    node = Mock(fleet_state_nickname_metadata=UNKNOWN_FLEET_STATE)
    node_storage.store_node_metadata(node=node)

    sqlite_db_conn.execute.assert_any_call(f"REPLACE INTO {CrawlerNodeStorage.NODE_DB_NAME} VALUES(?,?,?,?,?,?)", ANY)


def test_storage_store_state_metadata(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    sqlite_db_conn.reset_mock()
    now = maya.now()
    state = MagicMock(updated=now)
    node_storage.store_state_metadata(state=state)

    sqlite_db_conn.execute.assert_any_call(f"REPLACE INTO {CrawlerNodeStorage.STATE_DB_NAME} VALUES(?,?,?,?,?)",
                                    (ANY, ANY, ANY, ANY, now.rfc3339()))  # ensure timestamp in rfc3339


def test_storage_store_current_teacher(sqlite_db_conn):
    node_storage = CrawlerNodeStorage()

    sqlite_db_conn.reset_mock()
    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum=teacher_checksum)

    sqlite_db_conn.execute.assert_any_call(f'REPLACE INTO {CrawlerNodeStorage.TEACHER_DB_NAME} VALUES (?,?)',
                                    (CrawlerNodeStorage.TEACHER_ID, teacher_checksum))
