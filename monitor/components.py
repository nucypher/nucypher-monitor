import dash_daq as daq
import dash_html_components as html
import nucypher
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from maya import MayaDT
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from pendulum.parsing import ParserError

NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Launched', 'Last Seen', 'Fleet State']


def header() -> html.Div:
    return html.Div([html.Div(f'v{nucypher.__version__}', id='version')], className="logo-widget")


def state_detail(state_dict) -> html.Div:
    detail = html.Div([
        html.Div([
            html.Div(state_dict['symbol'], className='single-symbol'),
        ], className='nucypher-nickname-icon', style={'border-color': state_dict['color_hex']}),
        html.Span(state_dict['nickname'], title=state_dict['updated']),
    ], className='state', style={'background-color': state_dict['color_hex']})
    return detail


def _states_table(states_dict_list) -> html.Table:
    row = []
    for state_dict in states_dict_list:
        # add previous states in order (already reversed)
        row.append(html.Td(state_detail(state_dict)))
    return html.Table([html.Tr(row, id='state-table')])


def previous_states(states_dict_list) -> html.Div:
    return html.Div([
        html.H4('Previous States'),
        html.Div([
            _states_table(states_dict_list)
        ]),
    ], className='row')


def get_node_status(agent, staker_address, current_period, last_confirmed_period) -> html.Td:
    missing_confirmations = current_period - last_confirmed_period
    worker = agent.get_worker_from_staker(staker_address)
    if worker == BlockchainInterface.NULL_ADDRESS:
        missing_confirmations = BlockchainInterface.NULL_ADDRESS

    color_codex = {-1: ('green', 'OK'),                                   # Confirmed Next Period
                   0: ('#e0b32d', 'Pending'),                             # Pending Confirmation of Next Period
                   current_period: ('#525ae3', 'Idle'),                   # Never confirmed
                   BlockchainInterface.NULL_ADDRESS: ('red', 'Headless')  # Headless Staker (No Worker)
                   }
    try:
        color, status_message = color_codex[missing_confirmations]
    except KeyError:
        color, status_message = 'red', f'{missing_confirmations} Unconfirmed'
    status_cell = daq.Indicator(id='Status',
                                color=color,
                                value=True,
                                label=status_message,
                                labelPosition='right',
                                size=25)  # pixels
    status = html.Td(status_cell)
    return status


def generate_node_table_components(node_info: dict, registry) -> dict:
    identity = html.Td(children=html.Div([
        html.A(node_info['nickname'],
               href=f'https://{node_info["rest_url"]}/status',
               target='_blank')
    ]))

    # Fleet State
    fleet_state_div = []
    fleet_state_icon = node_info['fleet_state_icon']
    if fleet_state_icon is not UNKNOWN_FLEET_STATE:
        icon_list = node_info['fleet_state_icon']
        fleet_state_div = icon_list
    fleet_state = html.Td(children=html.Div(fleet_state_div))

    staker_address = node_info['staker_address']

    # Blockchainy (TODO)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    current_period = staking_agent.get_current_period()
    last_confirmed_period = staking_agent.get_last_active_period(staker_address)
    status = get_node_status(staking_agent, staker_address, current_period, last_confirmed_period)

    etherscan_url = f'https://goerli.etherscan.io/address/{node_info["staker_address"]}'
    try:
        slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
    except ParserError:
        slang_last_seen = node_info['last_seen']

    components = {
        'Status': status,
        'Checksum': html.Td(html.A(f'{node_info["staker_address"][:10]}...',
                                   href=etherscan_url,
                                   target='_blank')),
        'Nickname': identity,
        'Launched': html.Td(node_info['timestamp']),
        'Last Seen': html.Td([slang_last_seen, f" | Period {last_confirmed_period}"]),
        'Fleet State': fleet_state
    }

    return components


def nodes_table(nodes, teacher_index, registry) -> html.Table:
        rows = []
        for index, node_info in enumerate(nodes):
            row = []
            # TODO: could return list (skip column for-loop); however, dict is good in case of re-ordering of columns
            components = generate_node_table_components(node_info=node_info, registry=registry)
            for col in NODE_TABLE_COLUMNS:
                cell = components[col]
                if cell:
                    row.append(cell)

            style_dict = {'overflowY': 'scroll'}
            # highlight teacher
            if index == teacher_index:
                style_dict['backgroundColor'] = '#1E65F3'
                style_dict['color'] = 'white'

            rows.append(html.Tr(row, style=style_dict, className='node-row'))

        table = html.Table(
            # header
            [html.Tr([html.Th(col) for col in NODE_TABLE_COLUMNS], className='table-header')] +
            rows,
            id='node-table'
        )
        return table


def known_nodes(nodes_dict: dict, registry, teacher_checksum: str = None) -> html.Div:
    nodes = list()
    teacher_index = None
    for checksum in nodes_dict:
        node_data = nodes_dict[checksum]
        if node_data:
            if checksum == teacher_checksum:
                teacher_index = len(nodes)
            nodes.append(node_data)

    component = html.Div([
        html.H4('Network Nodes'),
        html.Div([
            html.Div('* Current Teacher',
                     style={'backgroundColor': '#1E65F3', 'color': 'white'},
                     className='two columns'),
        ]),
        html.Br(),
        html.H6(f'Known Nodes: {len(nodes_dict)}'),
        html.Div([nodes_table(nodes, teacher_index, registry)])
    ])

    return component
