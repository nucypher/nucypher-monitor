from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import maya
from influxdb import InfluxDBClient
from maya import MayaDT

from monitor.crawler import CrawlerNodeStorage
from monitor.db import CrawlerNodeMetadataDBClient, CrawlerBlockchainDBClient
from tests.utilities import (
    create_random_mock_node,
    create_random_mock_state,
    convert_node_to_db_row,
    convert_state_to_db_row,
)


#
# CrawlerNodeMetadataDBClient tests
#

def test_node_client_defaults():
    node_db_client = CrawlerNodeMetadataDBClient()
    assert node_db_client._db_filepath == CrawlerNodeStorage.DEFAULT_DB_FILEPATH


def test_node_client_non_defaults():
    temp_db_filepath = "/tmp/test.db"
    node_db_client = CrawlerNodeMetadataDBClient(temp_db_filepath)
    assert node_db_client._db_filepath == temp_db_filepath


def test_node_client_get_node_metadata(tempfile_path):
    # Add some node data
    node_storage = CrawlerNodeStorage(db_filepath=tempfile_path)
    node_1 = create_random_mock_node()
    node_2 = create_random_mock_node()
    node_3 = create_random_mock_node()
    node_4 = create_random_mock_node()
    node_5 = create_random_mock_node()

    node_list = [node_1, node_2, node_3, node_4, node_5]
    for node in node_list:
        node_storage.store_node_metadata(node=node)

    node_db_client = CrawlerNodeMetadataDBClient(db_filepath=tempfile_path)
    result = node_db_client.get_known_nodes_metadata()

    node_list.sort(key=lambda x: x.checksum_address)  # result is sorted by staker address
    assert len(result) == len(node_list)

    # "result" of form {staker_address -> {column_name -> column_value}}
    for idx, key in enumerate(result):
        node_info = result[key]

        expected_row = convert_node_to_db_row(node_list[idx])
        for info_idx, column in enumerate(CrawlerNodeStorage.NODE_DB_SCHEMA):
            assert node_info[column[0]] == expected_row[info_idx], f"{column[0]} matches"


def test_node_client_get_state_metadata(tempfile_path):
    # Add some node data
    node_storage = CrawlerNodeStorage(db_filepath=tempfile_path)
    state_1 = create_random_mock_state()
    state_2 = create_random_mock_state()
    state_3 = create_random_mock_state()

    state_list = [state_1, state_2, state_3]
    for state in state_list:
        node_storage.store_state_metadata(state=state)

    node_db_client = CrawlerNodeMetadataDBClient(db_filepath=tempfile_path)
    result = node_db_client.get_previous_states_metadata(limit=len(state_list))

    state_list.sort(key=lambda x: x.updated.epoch, reverse=True)  # sorted by timestamp in descending order
    assert len(result) == len(state_list)

    # verify result
    # "result" of form of a list of state_info dictionaries
    for idx, value in enumerate(result):
        expected_row = convert_state_to_db_row(state_list[idx])
        for info_idx, column in enumerate(CrawlerNodeStorage.STATE_DB_SCHEMA):
            assert value[column[0]] == expected_row[info_idx], f"{column[0]} matches"


def test_node_client_get_current_teacher_checksum(tempfile_path):
    node_storage = CrawlerNodeStorage(db_filepath=tempfile_path)
    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum=teacher_checksum)

    node_db_client = CrawlerNodeMetadataDBClient(db_filepath=tempfile_path)

    result = node_db_client.get_current_teacher_checksum()
    assert result == teacher_checksum

    new_teacher_checksum = '0x9876543221'
    node_storage.store_current_teacher(teacher_checksum=new_teacher_checksum)
    result = node_db_client.get_current_teacher_checksum()
    assert result == new_teacher_checksum


#
# CrawlerBlockchainDBClient tests
#
@patch.object(InfluxDBClient, '__new__')
def test_blockchain_client_close(new_influx_db):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)

    blockchain_db_client.close()
    mock_influxdb_client.close.assert_called_once()


@patch.object(InfluxDBClient, '__new__')
def test_blockchain_client_get_historical_locked_tokens(new_influx_db):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    mock_query_object = MagicMock()
    mock_influxdb_client.query.return_value = mock_query_object

    # fake results for 5 days
    days = 5
    start_date = maya.now().subtract(days=days)
    base_amount = 45000
    amount_increment = 10000

    results = []
    for day in range(0, days):
        results.append(dict(time=start_date.add(days=day).rfc3339(), sum=base_amount + (day * amount_increment)))
    mock_query_object.get_points.return_value = results

    blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)

    locked_tokens_dict = blockchain_db_client.get_historical_locked_tokens_over_range(days)

    # check query
    today = datetime.utcnow()
    range_end = datetime(year=today.year, month=today.month, day=today.day,
                         hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)  # include today in range
    range_begin = range_end - timedelta(days=days)

    expected_in_query = [
        "SELECT SUM(locked_stake)",
        "AS locked_stake",

        f"FROM moe_network_info WHERE time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
        f"time < '{MayaDT.from_datetime(range_end).rfc3339()}'",

        "GROUP BY staker_address, time(1d)) GROUP BY time(1d)",
    ]

    mock_influxdb_client.query.assert_called_once()
    mock_query_object.get_points.assert_called_once()

    call_args_list = mock_influxdb_client.query.call_args_list
    assert len(call_args_list) == 1
    for idx, execute_call in enumerate(call_args_list):
        query = execute_call[0][0]
        for statement in expected_in_query:
            assert statement in query

    # check results
    assert len(locked_tokens_dict) == days

    for idx, key in enumerate(locked_tokens_dict):
        # use of rfc3339 loses milliseconds precision
        date = MayaDT.from_rfc3339(start_date.add(days=idx).rfc3339()).datetime()
        assert key == date

        locked_tokens = locked_tokens_dict[key]
        assert locked_tokens == base_amount + (idx * amount_increment)

    # close must be explicitly called on CrawlerBlockchainDBClient
    mock_influxdb_client.close.assert_not_called()


@patch.object(InfluxDBClient, '__new__')
def test_blockchain_client_get_historical_num_stakers(new_influx_db):
    mock_influxdb_client = MagicMock()
    new_influx_db.return_value = mock_influxdb_client

    mock_query_object = MagicMock()
    mock_influxdb_client.query.return_value = mock_query_object

    # fake results for 10 days
    days = 10
    start_date = maya.now().subtract(days=days)
    base_count = 100
    count_increment = 4

    results = []
    for day in range(0, days):
        results.append(dict(time=start_date.add(days=day).rfc3339(), count=base_count + (day * count_increment)))
    mock_query_object.get_points.return_value = results

    blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)

    num_stakers_dict = blockchain_db_client.get_historical_num_stakers_over_range(days)

    # check query
    today = datetime.utcnow()
    range_end = datetime(year=today.year, month=today.month, day=today.day,
                         hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)  # include today in range
    range_begin = range_end - timedelta(days=days)

    expected_in_query = [
        "SELECT COUNT(staker_address)",

        f"FROM moe_network_info WHERE time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
        f"time < '{MayaDT.from_datetime(range_end).rfc3339()}'",

        "GROUP BY staker_address, time(1d)) GROUP BY time(1d)",
    ]

    mock_influxdb_client.query.assert_called_once()
    mock_query_object.get_points.assert_called_once()

    call_args_list = mock_influxdb_client.query.call_args_list
    assert len(call_args_list) == 1
    for idx, execute_call in enumerate(call_args_list):
        query = execute_call[0][0]
        for statement in expected_in_query:
            assert statement in query

    # check results
    assert len(num_stakers_dict) == days

    for idx, key in enumerate(num_stakers_dict):
        # use of rfc3339 loses milliseconds precision
        date = MayaDT.from_rfc3339(start_date.add(days=idx).rfc3339()).datetime()
        assert key == date

        num_stakers = num_stakers_dict[key]
        assert num_stakers == base_count + (idx * count_increment)

    # close must be explicitly called on CrawlerBlockchainDBClient
    mock_influxdb_client.close.assert_not_called()
