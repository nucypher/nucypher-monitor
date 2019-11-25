from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import maya
from influxdb import InfluxDBClient
from maya import MayaDT

from monitor.crawler import CrawlerNodeStorage
from monitor.db import CrawlerNodeMetadataDBClient, CrawlerBlockchainDBClient


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


def test_node_client_get_node_metadata(sqlite_db_conn):
    node_db_client = CrawlerNodeMetadataDBClient()

    # mock result
    execute_result = MagicMock()

    description = [(column[0], ) for column in CrawlerNodeStorage.NODE_DB_SCHEMA]
    execute_result.description = description

    fake_rows = [('0xfCD3367aDab428823b075297e957a97e3fa9692d', '12.370.46.67:9151', 'LightSlateGray Rain HotPink Swords', '2019-11-10T11:53:50Z', 'No Connection to Node', '?'),
                 ('0x4e004bCEc66bBF7b4EDa060D4D552770A9e63e23', '674.232.83.642:9151', 'Snow Juno DarkSlateGray Earth', '2019-11-11T20:45:57Z', 'No Connection to Node', '?'),
                 ('0xF63838F8FbD63c352DeefC3657111550d129d710', '61.234.3.9:9151', 'DarkRed Shamrock Crimson Fleur-de-lis', '2019-11-12T16:14:18Z', 'No Connection to Node', '?'),
                 ('0x4FDf08D2B5E8CcaBe32d9C439521DB26bE992Ad8', '143.109.142.84:9151', 'GoldenRod Ferry MediumBlue Gemini', '2019-11-13T07:38:17Z', 'No Connection to Node', '?'),
                 ('0xF7f04b6c817A16E8F3D4508969F1f6741a02457b', '15.547.15.106:9151', 'Thistle Swords DarkBlue Libra', '2019-11-14T13:26:38Z', 'No Connection to Node', '?'),
                 ('0x0f4Fbe8a28a8fF33bEcD6A8982D74308FC35D021', '222.22.22.22:9151', 'Brown Ground MintCream Helm', '2019-11-15T17:44:41Z', 'No Connection to Node', '?')]
    execute_result.__iter__.return_value = fake_rows
    sqlite_db_conn.execute.return_value = execute_result

    result = node_db_client.get_known_nodes_metadata()
    sqlite_db_conn.execute.assert_called_once_with(
        f"SELECT * FROM {CrawlerNodeStorage.NODE_DB_NAME} ORDER BY staker_address"
    )

    # verify result
    # "result" of form {staker_address -> {column_name -> column_value}}
    assert len(result) == len(fake_rows)

    for idx, key in enumerate(result):
        # ensure order remains
        assert key == fake_rows[idx][0]  # check staker_address

        node_info = result[key]
        # check node info dict values
        for info_idx, column in enumerate(CrawlerNodeStorage.NODE_DB_SCHEMA):
            assert node_info[column[0]] == fake_rows[idx][info_idx]

    sqlite_db_conn.close.assert_called_once()


def test_node_client_get_state_metadata(sqlite_db_conn):
    node_db_client = CrawlerNodeMetadataDBClient()

    # mock result
    execute_result = MagicMock()

    description = [(column[0], ) for column in CrawlerNodeStorage.STATE_DB_SCHEMA]
    execute_result.description = description

    fake_rows = [('PowderBlue Club', '♣', '#B0E0E6', 'PowderBlue', '2019-11-19T18:07:48.0Z'),
                 ('MintCream Juno', '⚵', '#F5FFFA', 'MintCream', '2019-11-19T18:07:06.6Z'),
                 ('RoyalBlue Earth', '♁', '#4169E1', 'RoyalBlue', '2019-11-19T18:05:33.3Z')]

    execute_result.__iter__.return_value = fake_rows
    sqlite_db_conn.execute.return_value = execute_result
    limit = 10
    result = node_db_client.get_previous_states_metadata(limit=limit)

    sqlite_db_conn.execute.assert_called_once_with(f"SELECT * FROM {CrawlerNodeStorage.STATE_DB_NAME} "
                                                   f"ORDER BY datetime(updated) DESC LIMIT {limit}")

    # verify result
    # "result" of form of a list of state_info dictionaries
    assert len(result) == len(fake_rows)

    for idx, value in enumerate(result):
        # ensure order remains and check node info dict values
        for info_idx, column in enumerate(CrawlerNodeStorage.STATE_DB_SCHEMA):
            column_name = column[0]
            expected_value = fake_rows[idx][info_idx]
            if column_name == 'updated':
                # timestamp is converted from rfc3339 to rfc2822 format
                expected_value = MayaDT.from_rfc3339(expected_value).rfc2822()

            assert value[column[0]] == expected_value

    sqlite_db_conn.close.assert_called_once()


def test_node_client_get_current_teacher_checksum(sqlite_db_conn):
    node_db_client = CrawlerNodeMetadataDBClient()

    # mock result
    execute_result = MagicMock()

    # set result column names
    description = [(column[0], ) for column in CrawlerNodeStorage.TEACHER_DB_SCHEMA]
    execute_result.description = description

    # checksum is specifically queried for, not entire row
    teacher_checksum = '0x4FDf08D2B5E8CcaBe32d9C439521DB26bE992Ad8'
    fake_rows = [(teacher_checksum, )]

    execute_result.__iter__.return_value = fake_rows
    sqlite_db_conn.execute.return_value = execute_result
    result = node_db_client.get_current_teacher_checksum()

    sqlite_db_conn.execute.assert_called_once_with(f"SELECT checksum_address from "
                                                   f"{CrawlerNodeStorage.TEACHER_DB_NAME} LIMIT 1")

    # verify result
    assert result == teacher_checksum

    sqlite_db_conn.close.assert_called_once()


#
# CrawlerBlockchainDBClient tests
#

def test_blockchain_client_close():
    mock_influxdb_client = MagicMock()
    with patch.object(InfluxDBClient, "__init__", lambda *args, **kwargs: None):
        blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)
        blockchain_db_client._client = mock_influxdb_client

        blockchain_db_client.close()
        mock_influxdb_client.close.assert_called_once()


def test_blockchain_client_get_historical_locked_tokens():
    mock_influxdb_client = MagicMock()

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

    with patch.object(InfluxDBClient, "__init__", lambda *args, **kwargs: None):
        blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)
        blockchain_db_client._client = mock_influxdb_client

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


def test_blockchain_client_get_historical_num_stakers():
    mock_influxdb_client = MagicMock()

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

    with patch.object(InfluxDBClient, "__init__", lambda *args, **kwargs: None):
        blockchain_db_client = CrawlerBlockchainDBClient(None, None, None)
        blockchain_db_client._client = mock_influxdb_client

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
