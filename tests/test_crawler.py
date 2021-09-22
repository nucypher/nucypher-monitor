import os
import sqlite3
from unittest.mock import MagicMock, patch

import maya
import monitor
import pytest
from monitor.crawler import CrawlerStorage, Crawler
from monitor.db import CrawlerStorageClient
from nucypher.blockchain.economics import StandardTokenEconomics
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import datetime_to_period
from nucypher.network.middleware import RestMiddleware
from tests.utilities import (
    create_random_mock_node,
    create_random_mock_node_status,
    create_specific_mock_state,
    MockContractAgency)

IN_MEMORY_FILEPATH = ':memory:'
DB_TABLES = [CrawlerStorage.NODE_DB_NAME, CrawlerStorage.STATE_DB_NAME, CrawlerStorage.TEACHER_DB_NAME]


#
# CrawlerStorage tests.
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
    node_storage = CrawlerStorage(db_filepath=IN_MEMORY_FILEPATH)
    assert node_storage.db_filepath == IN_MEMORY_FILEPATH


def test_storage_db_table_init(sqlite_connection):
    node_storage = CrawlerStorage(db_filepath=IN_MEMORY_FILEPATH)

    verify_all_db_tables_exist(sqlite_connection)


def test_storage_store_node_status(sqlite_connection):
    node_storage = CrawlerStorage(db_filepath=IN_MEMORY_FILEPATH)

    node_status = create_random_mock_node_status()

    # Store node data
    node_storage.store_node_status(node_status)

    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_node_matches(node_status, row)

    # update node timestamp value and store
    new_now = node_status.timestamp.add(hours=1)
    worker_address = '0xabcdef'
    updated_node = node_status._replace(timestamp=new_now, worker_address=worker_address)

    # ensure same item gets updated
    node_storage.store_node_status(updated_node)
    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerStorage.NODE_DB_NAME}").fetchall()
    assert len(result) == 1  # node data is updated not added
    for row in result:
        verify_mock_node_matches(updated_node, row)


def test_storage_store_fleet_state(sqlite_connection):
    node_storage = CrawlerStorage(db_filepath=IN_MEMORY_FILEPATH)

    state = create_specific_mock_state()

    # Store state data
    node_storage.store_fleet_state(state)

    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        verify_mock_state_matches_row(state, row)

    # update state
    new_now = state.timestamp.add(minutes=5)
    updated_state = state._replace(timestamp=new_now)
    node_storage.store_fleet_state(updated_state)

    # ensure same item gets updated
    result = sqlite_connection.execute(f"SELECT * FROM {CrawlerStorage.STATE_DB_NAME}").fetchall()
    assert len(result) == 1  # state data is updated not added
    for row in result:
        verify_mock_state_matches_row(updated_state, row)


def test_storage_store_current_retrieval(sqlite_connection):
    node_storage = CrawlerStorage(db_filepath=IN_MEMORY_FILEPATH)

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

    node_storage = CrawlerStorage(db_filepath=tempfile_path)
    del node_storage

    assert not os.path.exists(tempfile_path)  # db file deleted


#
# Crawler tests.
#

def create_crawler(db_filepath: str = IN_MEMORY_FILEPATH):
    registry = InMemoryContractRegistry()
    middleware = RestMiddleware()
    crawler = Crawler(domain='ibex',  # TODO: Needs Cleanup
                      network_middleware=middleware,
                      registry=registry,
                      start_learning_now=True,
                      learn_on_same_thread=False,
                      db_filepath=db_filepath
                      )
    return crawler


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
def test_crawler_stop_before_start(get_agent, get_economics):
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler()

    crawler.stop()
    assert not crawler.is_running


@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_start_then_stop(get_agent):
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler()
    try:
        crawler.start()
        assert crawler.is_running
    finally:
        crawler.stop()

    assert not crawler.is_running

@pytest.mark.skip("stopping a started crawler is not stopping the thread; ctrl-c needed")
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_learn_no_teacher(get_agent, tempfile_path):
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler(db_filepath=tempfile_path)
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

    assert not crawler.is_running


@pytest.mark.skip()
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_learn_about_teacher(get_agent, tempfile_path):
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    crawler = create_crawler(db_filepath=tempfile_path)
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

    assert not crawler.is_running


@pytest.mark.skip()
@patch.object(monitor.crawler.EconomicsFactory, 'get_economics', autospec=True)
@patch.object(monitor.crawler.ContractAgency, 'get_agent', autospec=True)
def test_crawler_learn_about_nodes(get_agent, get_economics, tempfile_path):
    staking_agent = MagicMock(autospec=True)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    token_economics = StandardTokenEconomics()
    get_economics.return_value = token_economics

    crawler = create_crawler(db_filepath=tempfile_path)
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
    finally:
        crawler.stop()

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
    result = db_conn.execute(f"SELECT checksum_address from {CrawlerStorage.TEACHER_DB_NAME}").fetchall()
    assert len(result) == 1
    for row in result:
        assert expected_teacher_checksum == row[0]


def verify_mock_node_matches(node_status, row):
    assert len(row) == 6

    assert node_status.staker_address == row[0], 'staker address matches'
    assert node_status.rest_url == row[1], 'rest url matches'
    assert str(node_status.nickname) == row[2], 'nickname matches'
    assert node_status.timestamp.iso8601() == row[3], 'new now timestamp matches'
    assert node_status.last_learned_from.iso8601() == row[4], 'last seen matches'
    assert "?" == row[5], 'fleet state icon matches'


def verify_mock_state_matches_row(state, row):
    assert len(row) == 5

    assert str(state.nickname) == row[0], 'nickname matches'
    assert state.nickname.characters[0].symbol == row[1], 'symbol matches'
    assert state.nickname.characters[0].color_hex == row[2], 'color hex matches'
    assert state.nickname.characters[0].color_name == row[3], 'color matches'
    assert state.timestamp.rfc3339() == row[4], 'updated timestamp matches'  # ensure timestamp in rfc3339
