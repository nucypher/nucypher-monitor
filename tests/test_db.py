from unittest.mock import MagicMock

from maya import MayaDT

from monitor.crawler import CrawlerNodeStorage
from monitor.db import CrawlerNodeMetadataDBClient


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

    description = [(column[0], ) for column in CrawlerNodeStorage.TEACHER_DB_SCHEMA]
    execute_result.description = description

    teacher_checksum = '0x4FDf08D2B5E8CcaBe32d9C439521DB26bE992Ad8'

    # checksum is specifically queried for, not entire row
    fake_rows = [(teacher_checksum, )]

    execute_result.__iter__.return_value = fake_rows
    sqlite_db_conn.execute.return_value = execute_result
    result = node_db_client.get_current_teacher_checksum()

    sqlite_db_conn.execute.assert_called_once_with(f"SELECT checksum_address from "
                                                   f"{CrawlerNodeStorage.TEACHER_DB_NAME} LIMIT 1")

    # verify result
    assert result == teacher_checksum

    sqlite_db_conn.close.assert_called_once()
