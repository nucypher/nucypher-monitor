import random
from typing import List, Dict
from unittest.mock import MagicMock, patch

import monitor.dashboard
import nucypher
import pytest
from flask import Flask
from monitor.crawler import CrawlerStorage
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU
from tests.markers import circleci_only
from tests.utilities import MockContractAgency, create_random_mock_node, create_random_mock_state


@pytest.mark.skip()
@circleci_only(reason="Additional complexity when using local machine's chromedriver")
@patch.object(monitor.dashboard.ContractAgency, 'get_agent', autospec=True)
def test_dashboard_render(get_agent, tempfile_path, dash_duo):
    ############## SETUP ################
    current_period = 18622

    # create node metadata
    nodes_list, last_confirmed_period_dict = create_nodes(num_nodes=5, current_period=current_period)

    # create states
    states_list = create_states(num_states=3)

    # write node, teacher (first item in node list), and state data to storage
    node_storage = CrawlerStorage(db_filepath=tempfile_path)
    store_node_db_data(node_storage, nodes=nodes_list, states=states_list)

    # Setup StakingEscrowAgent and ContractAgency
    partitioned_stakers = (25, 5, 10)  # confirmed, pending, inactive
    global_locked_tokens = NU(1000000, 'NU').to_nunits()
    staking_agent = create_mocked_staker_agent(partitioned_stakers=partitioned_stakers,
                                               current_period=current_period,
                                               global_locked_tokens=global_locked_tokens,
                                               last_confirmed_period_dict=last_confirmed_period_dict,
                                               nodes_list=nodes_list)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    ############## RUN ################
    server = Flask("monitor-dashboard")
    dashboard = monitor.dashboard.Dashboard(registry=None,
                                            flask_server=server,
                                            route_url='/',
                                            network='goerli')
    dash_duo.start_server(dashboard.dash_app)

    # check version
    assert dash_duo.wait_for_element_by_id('version').text == f'v{nucypher.__version__}'

    # check current period
    assert dash_duo.wait_for_element_by_id('current-period-value').text == str(current_period)

    # check domain
    assert dash_duo.wait_for_element_by_id('domain-value').text == 'goerli'

    # check active ursulas
    confirmed, pending, inactive = partitioned_stakers
    assert dash_duo.wait_for_element_by_id('active-ursulas-value').text == \
           f"{confirmed}/{confirmed + pending + inactive}"

    # check staked tokens
    assert dash_duo.wait_for_element_by_id('staked-tokens-value').text == str(NU.from_nunits(global_locked_tokens))

    #
    # check dash components/tables - keeping it simple by simply checking text
    # TODO there might be an easier way to test this
    #

    # staker breakdown
    pie_chart_text = dash_duo.wait_for_element_by_id('staker-breakdown-graph').text
    for num in partitioned_stakers:
        assert str(num) in pie_chart_text

    # check previous states
    state_table = dash_duo.wait_for_element_by_id('state-table')
    for state in states_list:
        verify_state_data_in_table(state, state_table)

    # check nodes
    node_table = dash_duo.wait_for_element_by_id('node-table')
    for node in nodes_list:
        verify_node_data_in_table(node=node,
                                  last_confirmed_period=last_confirmed_period_dict[node.checksum_address],
                                  current_period=current_period,
                                  node_table=node_table)

    #
    # test refresh/update buttons
    #

    # add a node and update page - ensure new node is displayed
    new_node = create_random_mock_node(generate_certificate=False)
    last_confirmed_period_dict[new_node.checksum_address] = current_period
    nodes_list.append(new_node)  # add new node to list
    node_storage.store_node_status(new_node)

    dash_duo.find_element("#node-update-button").click()

    node_table_updated = dash_duo.wait_for_element_by_id('node-table')
    # check for all nodes including new node
    assert new_node in nodes_list, "ensure new node in list to check"
    for node in nodes_list:
        verify_node_data_in_table(node=node,
                                  last_confirmed_period=last_confirmed_period_dict[node.checksum_address],
                                  current_period=current_period,
                                  node_table=node_table_updated)

    # add a state and update page - ensure new state is displayed
    new_state = create_random_mock_state()
    states_list.append(new_state)  # add state to list
    node_storage.store_state_metadata(new_state)

    dash_duo.find_element("#state-update-button").click()
    state_table_updated = dash_duo.wait_for_element_by_id('state-table')
    # check for all states including new state
    assert new_state in states_list, "ensure new state in list to check"
    for state in states_list:
        verify_state_data_in_table(state, state_table_updated)


def create_nodes(num_nodes: int, current_period: int):
    nodes_list = []
    base_active_period = current_period + 1
    last_confirmed_period_dict = dict()
    for i in range(0, num_nodes):
        node = create_random_mock_node(generate_certificate=False)
        nodes_list.append(node)

        last_confirmed_period = base_active_period - random.randrange(0, 3)
        # some percentage of the time flag the node as never confirmed
        if random.random() > 0.9:
            last_confirmed_period = 0
        last_confirmed_period_dict[node.checksum_address] = last_confirmed_period

    return nodes_list, last_confirmed_period_dict


def create_states(num_states: int):
    states_list = []
    for i in range(0, num_states):
        states_list.append(create_random_mock_state())

    return states_list


def store_node_db_data(storage: CrawlerStorage, nodes: List, states: List):
    for idx, node in enumerate(nodes):
        storage.store_node_status(node=node)
        if idx == 0:
            # first item in list is teacher
            storage.store_current_teacher(teacher_checksum=node.checksum_address)

    for state in states:
        storage.store_state_metadata(state)


def create_blockchain_db_historical_data(days_in_past: int):
    historical_staked_tokens = []
    historical_stakers = []
    historical_work_orders = []
    for i in range(1, (days_in_past+1)):
        historical_staked_tokens.append(NU(500000 + i*100000, 'NU').to_nunits())
        historical_stakers.append(10 + i*9)
        historical_work_orders.append(random.randrange(0, 20))

    return historical_staked_tokens, historical_stakers, historical_work_orders


def create_mocked_staker_agent(partitioned_stakers: tuple,
                               current_period: int,
                               global_locked_tokens: int,
                               last_confirmed_period_dict: Dict,
                               nodes_list: List):
    staking_agent = MagicMock(spec=StakingEscrowAgent, autospec=True)

    confirmed = MagicMock(spec=list)
    confirmed.__len__.return_value = partitioned_stakers[0]
    pending = MagicMock(spec=list)
    pending.__len__.return_value = partitioned_stakers[1]
    inactive = MagicMock(spec=list)
    inactive.__len__.return_value = partitioned_stakers[2]

    staking_agent.partition_stakers_by_activity.return_value = (confirmed, pending, inactive)

    staking_agent.get_current_period.return_value = current_period

    staking_agent.get_global_locked_tokens.return_value = global_locked_tokens

    staking_agent.get_worker_from_staker.side_effect = \
        lambda staker_address: list(filter(
            lambda x: x.checksum_address == staker_address, nodes_list))[0].worker_address

    base_locked_tokens = NU(1000000, 'NU').to_nunits()

    def _get_mock_all_active_stakers(periods: int, pagination_size: int = None):
        tokens = base_locked_tokens - NU(periods*2500, 'NU').to_nunits()
        # linearly decrease over 1 year
        num_stakers_for_period = round(partitioned_stakers[0] - (periods * partitioned_stakers[0] / 366))
        stakers_list = MagicMock(spec=list)
        stakers_list.__len__.return_value = num_stakers_for_period

        return tokens, stakers_list

    staking_agent.get_all_active_stakers.side_effect = _get_mock_all_active_stakers

    staking_agent.get_last_committed_period.side_effect = \
        lambda staker_address: last_confirmed_period_dict[staker_address]

    return staking_agent


def verify_node_data_in_table(node, last_confirmed_period, current_period, node_table):
    node_table_text = node_table.text
    node_table_inner_html = node_table.get_attribute('innerHTML')

    assert f'{node.checksum_address[:10]}...' in node_table_text, "checksum displayed"
    assert node.nickname in node_table_text, 'nickname displayed'
    assert node.timestamp.iso8601() in node_table_text, 'launch time displayed'
    assert node.last_seen.slang_time() in node_table_text, 'last seen displayed'
    last_confirmed_period = last_confirmed_period
    assert str(last_confirmed_period) in node_table_text, 'last confirmed period displayed'
    assert node.rest_url() in node_table_inner_html
    # check status
    # TODO probably a better way to do this
    expected_status = get_expected_status_text(current_period=current_period,
                                               last_confirmed_period=last_confirmed_period,
                                               worker_address=node.worker_address)
    assert expected_status in node_table_text, 'status text displayed'


def verify_state_data_in_table(state, state_table):
    state_table_text = state_table.text
    assert state.nickname in state_table_text, 'nickname displayed'
    assert state.metadata[0][1] in state_table_text, 'symbol displayed'


def get_expected_status_text(current_period: int, last_confirmed_period: int, worker_address: str):
    if worker_address == NULL_ADDRESS:
        return 'Headless'

    missing_confirmations = current_period - last_confirmed_period
    if missing_confirmations < 0:
        return 'OK'
    elif missing_confirmations == 0:
        return 'Pending'
    elif missing_confirmations == current_period:
        return 'Idle'
    else:
        return 'Unconfirmed'
