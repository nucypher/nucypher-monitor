import os
from unittest.mock import MagicMock, patch

from influxdb import InfluxDBClient
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.cli import actions
from nucypher.config.storages import SQLiteForgetfulNodeStorage
from nucypher.network.middleware import RestMiddleware

from monitor.crawler import CrawlerNodeStorage, Crawler
from monitor.db import CrawlerNodeMetadataDBClient
from tests.utilities import (
    create_random_mock_node,
    create_specific_mock_node,
    create_specific_mock_state,
    verify_mock_node_matches,
    verify_mock_state_matches
)

IN_MEMORY_FILEPATH = ':memory:'
DB_TABLES = [CrawlerNodeStorage.NODE_DB_NAME, CrawlerNodeStorage.STATE_DB_NAME, CrawlerNodeStorage.TEACHER_DB_NAME]


#
# CrawlerNodeStorage tests.
#
def verify_all_db_tables_exist(db_conn, expect_present=True):
    # check tables created
    result = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if not expect_present:
        assert len(result) == 0
    else:
        for row in result:
            assert row[0] in DB_TABLES


def verify_all_db_tables(db_conn, expect_empty=True):
    for table in DB_TABLES:
        result = db_conn.execute(f"SELECT * FROM {table}").fetchall()
        if expect_empty:
            assert len(result) == 0
        else:
            assert len(result) > 0


def verify_current_teacher(db_conn, expected_teacher_checksum):
    result = db_conn.execute(f"SELECT checksum_address from {CrawlerNodeStorage.TEACHER_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        assert expected_teacher_checksum == row[0]


def test_storage_init():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)
    assert node_storage.db_filepath == IN_MEMORY_FILEPATH
    assert not node_storage.federated_only
    assert CrawlerNodeStorage._name != SQLiteForgetfulNodeStorage._name


def test_storage_db_table_init():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    verify_all_db_tables_exist(node_storage.db_conn)


def test_storage_initialize():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    node_storage.initialize()  # re-initialize
    verify_all_db_tables_exist(node_storage.db_conn)


def test_storage_store_node_metadata_store():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    node = create_specific_mock_node()

    # Store node data
    node_storage.store_node_metadata(node=node)

    result = node_storage.db_conn.execute(f"SELECT * FROM {CrawlerNodeStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_node_matches(node, row)

    # update node timestamp value and store
    new_now = node.timestamp.add(hours=1)
    worker_address = '0xabcdef'
    updated_node = create_specific_mock_node(timestamp=new_now, worker_address=worker_address)

    # ensure same item gets updated
    node_storage.store_node_metadata(node=updated_node)
    result = node_storage.db_conn.execute(f"SELECT * FROM {CrawlerNodeStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1  # node data is updated not added
    for row in result:
        verify_mock_node_matches(updated_node, row)


def test_storage_store_state_metadata_store():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    state = create_specific_mock_state()

    # Store state data
    node_storage.store_state_metadata(state=state)

    result = node_storage.db_conn.execute(f"SELECT * FROM {CrawlerNodeStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_state_matches(state, row)

    # update state
    new_now = state.updated.add(minutes=5)
    new_color = 'red'
    new_color_hex = '4F3D21'
    symbol = '%'
    updated_state = create_specific_mock_state(updated=new_now, color=new_color, color_hex=new_color_hex, symbol=symbol)
    node_storage.store_state_metadata(state=updated_state)

    # ensure same item gets updated
    result = node_storage.db_conn.execute(f"SELECT * FROM {CrawlerNodeStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1  # state data is updated not added
    for row in result:
        verify_mock_state_matches(updated_state, row)


def test_storage_store_current_retrieval():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum=teacher_checksum)
    # check current teacher
    verify_current_teacher(node_storage.db_conn, teacher_checksum)

    # update current teacher
    updated_teacher_checksum = '0x987654321'
    node_storage.store_current_teacher(teacher_checksum=updated_teacher_checksum)
    # check current teacher
    verify_current_teacher(node_storage.db_conn, updated_teacher_checksum)


def test_storage_deletion(tempfile_path):
    assert os.path.exists(tempfile_path)

    node_storage = CrawlerNodeStorage(db_filepath=tempfile_path)
    del node_storage

    assert not os.path.exists(tempfile_path)  # db file deleted


def test_storage_db_clear():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)
    verify_all_db_tables_exist(node_storage.db_conn)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=state)

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(node_storage.db_conn, expect_empty=False)

    # clear tables
    node_storage.clear()

    # db tables should have been cleared
    verify_all_db_tables(node_storage.db_conn, expect_empty=True)


def test_storage_db_clear_only_metadata_not_certificates():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=state)

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(node_storage.db_conn, expect_empty=False)

    # clear metadata tables
    node_storage.clear(metadata=True, certificates=False)

    # db tables should have been cleared
    verify_all_db_tables(node_storage.db_conn, expect_empty=True)


def test_storage_db_clear_not_metadata():
    node_storage = CrawlerNodeStorage(db_filepath=IN_MEMORY_FILEPATH)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=state)

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(node_storage.db_conn, expect_empty=False)

    # only clear certificates data
    node_storage.clear(metadata=False, certificates=True)

    # db tables should not have been cleared
    verify_all_db_tables(node_storage.db_conn, expect_empty=False)


#
# Crawler tests.
#
@patch.object(ContractAgency, 'get_agent')
def test_crawler_init(get_agent):
    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler()

    # crawler not yet started
    assert not crawler.is_running


@patch.object(ContractAgency, 'get_agent')
@patch.object(InfluxDBClient, '__new__')
def test_crawler_stop_before_start(new_influx_db, get_agent):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler()

    crawler.stop()

    mock_influxdb_client.close.assert_not_called()  # db only initialized when crawler is started
    assert not crawler.is_running


@patch.object(ContractAgency, 'get_agent')
@patch.object(InfluxDBClient, '__new__')
def test_crawler_start_then_stop(new_influx_db, get_agent):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
        mock_influxdb_client.close.assert_not_called()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@patch.object(ContractAgency, 'get_agent')
@patch.object(InfluxDBClient, '__new__')
def test_crawler_start_blockchain_db_not_present(new_influx_db, get_agent):
    mock_influxdb_client = MagicMock()
    mock_influxdb_client.get_list_database.return_value = [{'name': 'db1'},
                                                           {'name': 'db2'},
                                                           {'name': 'db3'}]
    new_influx_db.return_value = mock_influxdb_client

    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
        mock_influxdb_client.close.assert_not_called()

        # ensure table existence check run
        mock_influxdb_client.get_list_database.assert_called_once()
        # db created since not present
        mock_influxdb_client.create_database.assert_called_once_with(Crawler.BLOCKCHAIN_DB_NAME)
        mock_influxdb_client.create_retention_policy.assert_called_once()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@patch.object(ContractAgency, 'get_agent')
@patch.object(InfluxDBClient, '__new__')
def test_crawler_start_blockchain_db_already_present(new_influx_db, get_agent):
    mock_influxdb_client = MagicMock()
    mock_influxdb_client.get_list_database.return_value = [{'name': 'db1'},
                                                           {'name': f'{Crawler.BLOCKCHAIN_DB_NAME}'},
                                                           {'name': 'db3'}]
    new_influx_db.return_value = mock_influxdb_client

    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
        mock_influxdb_client.close.assert_not_called()

        # ensure table existence check run
        mock_influxdb_client.get_list_database.assert_called_once()
        # db not created since not present
        mock_influxdb_client.create_database.assert_not_called()
        mock_influxdb_client.create_retention_policy.assert_not_called()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@patch.object(ContractAgency, 'get_agent')
@patch.object(InfluxDBClient, '__new__')
def test_crawler_start_learning(new_influx_db, get_agent, tempfile_path):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    staking_agent = MagicMock()
    get_agent.return_value = staking_agent

    crawler = create_crawler(node_db_filepath=tempfile_path, refresh_rate=2)
    node_db_client = CrawlerNodeMetadataDBClient(db_filepath=tempfile_path)
    try:
        crawler.start()
        assert crawler.is_running

        crawler.learn_from_teacher_node()

        current_teacher_checksum = node_db_client.get_current_teacher_checksum()
        assert current_teacher_checksum is not None

        known_nodes = node_db_client.get_known_nodes_metadata()
        assert len(known_nodes) > 0
        assert current_teacher_checksum in known_nodes

        random_node = create_random_mock_node(generate_certificate=True)
        crawler.remember_node(node=random_node, force_verification_check=False, record_fleet_state=True)
        known_nodes = node_db_client.get_known_nodes_metadata()
        assert len(known_nodes) > 0
        assert random_node.checksum_address in known_nodes

        previous_states = node_db_client.get_previous_states_metadata()
        assert len(previous_states) > 0
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


def create_crawler(node_db_filepath: str = IN_MEMORY_FILEPATH, refresh_rate: int = Crawler.DEFAULT_REFRESH_RATE):
    registry = InMemoryContractRegistry()
    middleware = RestMiddleware()
    teacher_nodes = actions.load_seednodes(None,
                                           teacher_uris=['https://discover.nucypher.network:9151'],
                                           min_stake=0,
                                           federated_only=False,
                                           network_domains={'goerli'},
                                           network_middleware=middleware)

    crawler = Crawler(domains={'goerli'},
                      network_middleware=middleware,
                      known_nodes=teacher_nodes,
                      registry=registry,
                      start_learning_now=True,
                      learn_on_same_thread=False,
                      blockchain_db_host='localhost',
                      blockchain_db_port=8086,
                      refresh_rate=refresh_rate,
                      node_db_filepath=node_db_filepath
                      )
    return crawler
