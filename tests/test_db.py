from monitor.crawler import CrawlerStorage
from monitor.db import CrawlerStorageClient
from tests.utilities import (
    create_random_mock_node_status,
    create_random_mock_state,
)


#
# CrawlerStorageClient tests
#


def test_node_client_init_values():
    temp_db_filepath = "/tmp/test.db"
    node_db_client = CrawlerStorageClient(temp_db_filepath)
    assert node_db_client._db_filepath == temp_db_filepath


def test_node_client_get_node_metadata(tempfile_path):
    # Add some node data
    node_storage = CrawlerStorage(db_filepath=tempfile_path)
    node_1 = create_random_mock_node_status()
    node_2 = create_random_mock_node_status()
    node_3 = create_random_mock_node_status()
    node_4 = create_random_mock_node_status()
    node_5 = create_random_mock_node_status()

    node_list = [node_1, node_2, node_3, node_4, node_5]
    for node in node_list:
        node_storage.store_node_status(node)

    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)
    result = node_db_client.get_known_nodes_metadata()

    node_list.sort(key=lambda x: x.staker_address)  # result is sorted by staker address
    assert len(result) == len(node_list)

    # "result" of form {staker_address -> {column_name -> column_value}}
    for idx, key in enumerate(result):
        node_info = result[key]

        expected_row = convert_node_status_to_db_row(node_list[idx])
        for info_idx, column in enumerate(CrawlerStorage.NODE_DB_SCHEMA):
            assert node_info[column[0]] == expected_row[info_idx], f"{column[0]} matches"


def test_node_client_get_state_metadata(tempfile_path):
    # Add some node data
    node_storage = CrawlerStorage(db_filepath=tempfile_path)
    state_1 = create_random_mock_state(seed=1)
    state_2 = create_random_mock_state(seed=2)
    state_3 = create_random_mock_state(seed=3)

    state_list = [state_1, state_2, state_3]
    for state in state_list:
        node_storage.store_fleet_state(state)

    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)
    result = node_db_client.get_previous_states_metadata(limit=len(state_list))

    state_list.sort(key=lambda x: x.timestamp.epoch, reverse=True)  # sorted by timestamp in descending order
    assert len(result) == len(state_list)

    # verify result
    # "result" of form of a list of state_info dictionaries
    for idx, value in enumerate(result):
        expected_row = convert_state_to_display_values(state_list[idx])
        for info_idx, column in enumerate(CrawlerStorage.STATE_DB_SCHEMA):
            assert value[column[0]] == expected_row[info_idx], f"{column[0]} matches"


def test_node_client_get_current_teacher_checksum(tempfile_path):
    node_storage = CrawlerStorage(db_filepath=tempfile_path)
    teacher_checksum = '0x123456789'
    node_storage.store_current_teacher(teacher_checksum=teacher_checksum)

    node_db_client = CrawlerStorageClient(db_filepath=tempfile_path)

    result = node_db_client.get_current_teacher_checksum()
    assert result == teacher_checksum

    new_teacher_checksum = '0x9876543221'
    node_storage.store_current_teacher(teacher_checksum=new_teacher_checksum)
    result = node_db_client.get_current_teacher_checksum()
    assert result == new_teacher_checksum


def convert_node_status_to_db_row(node_status):
    return (node_status.staker_address, node_status.rest_url, str(node_status.nickname),
            node_status.timestamp.iso8601(), node_status.last_learned_from.iso8601(), "?")


def convert_state_to_display_values(state):
    return (str(state.nickname), state.nickname.characters[0].symbol, state.nickname.characters[0].color_hex,
            state.nickname.characters[0].color_name, state.timestamp.rfc2822())
