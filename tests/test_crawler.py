import os
import sqlite3
from unittest.mock import MagicMock, patch

import maya
import monitor
import pytest
from monitor.crawler import CrawlerNodeStorage, Crawler, SQLiteForgetfulNodeStorage
from monitor.db import CrawlerStorageClient
from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.economics import StandardTokenEconomics
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import datetime_to_period
from nucypher.cli import actions
from nucypher.network.middleware import RestMiddleware
from tests.utilities import (
    create_random_mock_node,
    create_specific_mock_node,
    create_specific_mock_state,
    MockContractAgency)

IN_MEMORY_FILEPATH = ':memory:'
DB_TABLES = [CrawlerNodeStorage.NODE_DB_NAME, CrawlerNodeStorage.STATE_DB_NAME, CrawlerNodeStorage.TEACHER_DB_NAME]


#
# CrawlerNodeStorage tests.
#
@pytest.fixture(scope='function')
def sqlite_connection(monkeypatch):
    db_conn = sqlite3.connect(IN_MEMORY_FILEPATH)

    def patch_connect(*args, **kwargs):
        return db_conn

    monkeypatch.setattr(sqlite3, 'connect', patch_connect)
    yield db_conn
    db_conn.close()


def test_storage_init():
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)
    assert node_storage.db_filepath == IN_MEMORY_FILEPATH
    assert not node_storage.federated_only
    assert CrawlerNodeStorage._name != SQLiteForgetfulNodeStorage._name


def test_storage_db_table_init(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    verify_all_db_tables_exist(sqlite_connection)


def test_storage_initialize(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    node_storage.initialize()  # re-initialize
    verify_all_db_tables_exist(sqlite_connection)


def test_storage_store_node_metadata(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    node = create_specific_mock_node()

    # Store node data
    node_storage.store_node_metadata(node=node)

    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerNodeStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_node_matches(node, row)

    # update node timestamp value and store
    new_now = node.timestamp.add(hours=1)
    worker_address = '0xabcdef'
    updated_node = create_specific_mock_node(timestamp=new_now, worker_address=worker_address)

    # ensure same item gets updated
    node_storage.store_node_metadata(node=updated_node)
    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerNodeStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1  # node data is updated not added
    for row in result:
        verify_mock_node_matches(updated_node, row)


def test_storage_store_state_metadata(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    state = create_specific_mock_state()

    # Store state data
    node_storage.store_state_metadata(state=FleetSensor.abridged_state_details(state))

    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerNodeStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_state_matches_row(state, row)

    # update state
    new_now = state.updated.add(minutes=5)
    new_color = 'red'
    new_color_hex = '4F3D21'
    symbol = '%'
    updated_state = create_specific_mock_state(updated=new_now, color=new_color, color_hex=new_color_hex, symbol=symbol)
    node_storage.store_state_metadata(state=FleetSensor.abridged_state_details(updated_state))

    # ensure same item gets updated
    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerNodeStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1  # state data is updated not added
    for row in result:
        verify_mock_state_matches_row(updated_state, row)


def test_storage_store_current_retrieval(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum=teacher_checksum)
    # check current teacher
    verify_current_teacher(sqlite_connection, teacher_checksum)

    # update current teacher
    updated_teacher_checksum = '0x987654321'
    node_storage.store_current_teacher(teacher_checksum=updated_teacher_checksum)
    # check current teacher
    verify_current_teacher(sqlite_connection, updated_teacher_checksum)


def test_storage_deletion(tempfile_path):
    assert os.path.exists(tempfile_path)

    node_storage = CrawlerNodeStorage(storage_filepath=tempfile_path)
    del node_storage

    assert not os.path.exists(tempfile_path)  # db file deleted


def test_storage_db_clear(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)
    verify_all_db_tables_exist(sqlite_connection)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=FleetSensor.abridged_state_details(state))

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(sqlite_connection, expect_empty=False)

    # clear tables
    node_storage.clear()

    # db tables should have been cleared
    verify_all_db_tables(sqlite_connection, expect_empty=True)


def test_storage_db_clear_only_metadata_not_certificates(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=FleetSensor.abridged_state_details(state))

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(sqlite_connection, expect_empty=False)

    # clear metadata tables
    node_storage.clear(metadata=True, certificates=False)

    # db tables should have been cleared
    verify_all_db_tables(sqlite_connection, expect_empty=True)


def test_storage_db_clear_not_metadata(sqlite_connection):
    node_storage = CrawlerNodeStorage(storage_filepath=IN_MEMORY_FILEPATH)

    # store some data
    node = create_random_mock_node()
    node_storage.store_node_metadata(node=node)

    state = create_specific_mock_state()
    node_storage.store_state_metadata(state=FleetSensor.abridged_state_details(state))

    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum)

    verify_all_db_tables(sqlite_connection, expect_empty=False)

    # only clear certificates data
    node_storage.clear(metadata=False, certificates=True)

    # db tables should not have been cleared
    verify_all_db_tables(sqlite_connection, expect_empty=False)


#
# Crawler tests.
#

def create_crawler(node_db_filepath: str = IN_MEMORY_FILEPATH):
    registry = InMemoryContractRegistry()
    middleware = RestMiddleware()
    crawler = Crawler(domain='ibex',  # TODO: Needs Cleanup
                      network_middleware=middleware,
                      registry=registry,
                      start_learning_now=True,
                      learn_on_same_thread=False,
                      influx_host='localhost',  # TODO: Needs Cleanup
                      influx_port=8086,  # TODO: Needs Cleanup
                      node_storage_filepath=node_db_filepath
                      )
    return crawler


def configure_mock_staking_agent(staking_agent, tokens, current_period, initial_period,
                                 terminal_period, last_active_period):
    staking_agent.owned_tokens.return_value = tokens
    staking_agent.get_locked_tokens.return_value = tokens

    staking_agent.get_current_period.return_value = current_period
    staking_agent.get_all_stakes.return_value = [(initial_period, terminal_period, tokens)]
    staking_agent.get_last_committed_period.return_value = last_active_period


@patch.object(monitor.crawler.EconomicsFactory, 'get_economics', autospec=True)
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_init(get_agent, get_economics):
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler()

    # crawler not yet started
    assert not crawler.is_running


@patch.object(monitor.crawler.EconomicsFactory, 'get_economics', autospec=True)
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_stop_before_start(new_influx_db, get_agent, get_economics):
    mock_influxdb_client = new_influx_db.return_value

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler()

    crawler.stop()

    new_influx_db.assert_not_called()  # db only initialized when crawler is started
    mock_influxdb_client.close.assert_not_called()  # just to be sure
    assert not crawler.is_running


@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_start_then_stop(new_influx_db, get_agent):
    mock_influxdb_client = new_influx_db.return_value

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
        mock_influxdb_client.close.assert_not_called()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@patch.object(monitor.crawler.EconomicsFactory, 'get_economics', autospec=True)
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_start_no_influx_db_connection(get_agent, get_economics):
    staking_agent = MagicMock(spec=StakingEscrowAgent, autospec=True)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler()
    try:
        with pytest.raises(ConnectionError):
            crawler.start()
    finally:
        crawler.stop()


@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_start_blockchain_db_not_present(new_influx_db, get_agent):
    mock_influxdb_client = new_influx_db.return_value
    mock_influxdb_client.get_list_database.return_value = [{'name': 'db1'},
                                                           {'name': 'db2'},
                                                           {'name': 'db3'}]

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
        mock_influxdb_client.close.assert_not_called()

        # ensure table existence check run
        mock_influxdb_client.get_list_database.assert_called_once()
        # db created since not present
        mock_influxdb_client.create_database.assert_called_once_with(Crawler.INFLUX_DB_NAME)
        mock_influxdb_client.create_retention_policy.assert_called_once()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_start_blockchain_db_already_present(new_influx_db, get_agent):
    mock_influxdb_client = new_influx_db.return_value
    mock_influxdb_client.get_list_database.return_value = [{'name': 'db1'},
                                                           {'name': f'{Crawler.INFLUX_DB_NAME}'},
                                                           {'name': 'db3'}]

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

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


@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_learn_no_teacher(new_influx_db, get_agent, tempfile_path):
    mock_influxdb_client = new_influx_db.return_value

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler(node_db_filepath=tempfile_path)
    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)
    try:
        crawler.start()
        assert crawler.is_running

        # learn about teacher
        crawler.learn_from_teacher_node()

        known_nodes = node_db_client.get_known_nodes_metadata()
        assert len(known_nodes) == 0

        current_teacher_checksum = node_db_client.get_current_teacher_checksum()
        assert current_teacher_checksum is None
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@pytest.mark.skip()
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_learn_about_teacher(new_influx_db, get_agent, tempfile_path):
    mock_influxdb_client = new_influx_db.return_value

    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler(node_db_filepath=tempfile_path)
    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)
    try:
        crawler.start()
        assert crawler.is_running

        # learn about teacher
        crawler.learn_from_teacher_node()

        current_teacher_checksum = node_db_client.get_current_teacher_checksum()
        assert current_teacher_checksum is not None

        known_nodes = node_db_client.get_known_nodes_metadata()
        assert len(known_nodes) > 0
        assert current_teacher_checksum in known_nodes
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


@pytest.mark.skip()
@patch.object(monitor.crawler.EconomicsFactory, 'get_economics', autospec=True)
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
@patch('monitor.crawler.InfluxDBClient', autospec=True)
def test_crawler_learn_about_nodes(new_influx_db, get_agent, get_economics, tempfile_path):
    mock_influxdb_client = new_influx_db.return_value
    mock_influxdb_client.write_points.return_value = True

    # TODO: issue with use of `agent.blockchain` causes spec=StakingEscrowAgent not to be specified in MagicMock
    # Get the following - AttributeError: Mock object has no attribute 'blockchain'
    staking_agent = MagicMock(autospec=True)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler(node_db_filepath=tempfile_path)
    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)
    try:
        crawler.start()
        assert crawler.is_running

        for i in range(0, 5):
            random_node = create_random_mock_node(generate_certificate=True)
            crawler.remember_node(node=random_node, record_fleet_state=True)
            known_nodes = node_db_client.get_known_nodes_metadata()
            assert len(known_nodes) > i
            assert random_node.checksum_address in known_nodes

            previous_states = node_db_client.get_previous_states_metadata()
            assert len(previous_states) > i

            # configure staking agent for blockchain calls
            tokens = NU(int(15000 + i*2500), 'NU').to_nunits()
            current_period = datetime_to_period(maya.now(), token_economics.seconds_per_period)
            initial_period = current_period - i
            terminal_period = current_period + (i+50)
            last_active_period = current_period - i
            staking_agent.get_worker_from_staker.side_effect = \
                lambda staker_address: crawler.node_storage.get(federated_only=False,
                                                                checksum_address=staker_address).worker_address

            configure_mock_staking_agent(staking_agent=staking_agent,
                                         tokens=tokens,
                                         current_period=current_period,
                                         initial_period=initial_period,
                                         terminal_period=terminal_period,
                                         last_active_period=last_active_period)

            # run crawler callable
            crawler._learn_about_nodes()

            # ensure data written to influx table
            mock_influxdb_client.write_points.assert_called_once()

            # expected db row added
            write_points_call_args_list = mock_influxdb_client.write_points.call_args_list
            influx_db_line_protocol_statement = str(write_points_call_args_list[0][0])

            expected_arguments = [f'staker_address={random_node.checksum_address}',
                                  f'worker_address="{random_node.worker_address}"',
                                  f'stake={float(NU.from_nunits(tokens).to_tokens())}',
                                  f'locked_stake={float(NU.from_nunits(tokens).to_tokens())}',
                                  f'current_period={current_period}i',
                                  f'last_confirmed_period={last_active_period}i',
                                  f'work_orders={len(random_node.work_orders())}i']
            for arg in expected_arguments:
                assert arg in influx_db_line_protocol_statement, \
                    f"{arg} in {influx_db_line_protocol_statement} for iteration {i}"

            mock_influxdb_client.reset_mock()
    finally:
        crawler.stop()

    mock_influxdb_client.close.assert_called_once()
    assert not crawler.is_running


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


def verify_mock_node_matches(node, row):
    assert len(row) == 6

    assert node.checksum_address == row[0], 'staker address matches'
    assert node.rest_url() == row[1], 'rest url matches'
    assert node.nickname == row[2], 'nickname matches'
    assert node.timestamp.iso8601() == row[3], 'new now timestamp matches'
    assert node.last_seen.iso8601() == row[4], 'last seen matches'
    assert "?" == row[5], 'fleet state icon matches'


def verify_mock_state_matches_row(state, row):
    assert len(row) == 5

    assert state.nickname == row[0], 'nickname matches'
    assert state.metadata[0][1] == row[1], 'symbol matches'
    assert state.metadata[0][0]['hex'] == row[2], 'color hex matches'
    assert state.metadata[0][0]['color'] == row[3], 'color matches'
    assert state.updated.rfc3339() == row[4], 'updated timestamp matches'  # ensure timestamp in rfc3339
