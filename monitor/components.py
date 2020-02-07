from typing import List

import dash_daq as daq
import dash_html_components as html
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from maya import MayaDT
from pendulum.parsing import ParserError

import nucypher
from nucypher.blockchain.eth.token import NU

NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Uptime', 'Last Seen', 'Fleet State']


# Note: Unused entries will be ignored
BUCKET_DESCRIPTIONS = {
    'active': "Nodes that are currently confirmed or pending",
    'confirmed': "Nodes that confirmed activity for the next period",
    'pending': "Nodes that previously confirmed activity for the current period but not for the next period",
    'idle': "Nodes that have never confirmed.",
    'inactive': "Nodes that previously confirmed activity but missed multiple periods since then.",
    'unconnected': "Nodes that the monitor has not connected to - can be temporary while learning about the network (nodes should NOT remain here)",
}


ETHERSCAN_URL_TEMPLATE = "https://goerli.etherscan.io/address/{}"


def header() -> html.Div:
    return html.Div([html.Div(f'v{nucypher.__version__}', id='version')], className="logo-widget")


def make_contract_row(agent, balance: NU = None):
    cells = [
        html.A(f'{agent.contract_name} {agent.contract_address} ({agent.contract.version})',
               id=f"{agent.contract_name}-contract-address",
               href=ETHERSCAN_URL_TEMPLATE.format(agent.contract_address)),
    ]

    if balance is not None:
        cells.append(html.Span(balance))

    row = html.Tr(cells)
    return row


def state_detail(state: dict, current_state: bool) -> html.Div:
    children = [
        html.Div([
            html.Div(state['symbol'], className='single-symbol'),
        ], className='nucypher-nickname-icon', style={'border-color': state['color_hex']}),
        html.Span(state['nickname'], title=state['updated'])]

    if current_state:
        # add current annotation to children
        children.append(html.Span('(*Current)'))

    detail = html.Div(children=children,
                      className='state state-current' if current_state else 'state',
                      style={'background-color': state['color_hex']})
    return detail


def _states_table(states: List[dict]) -> html.Table:
    row = []
    for idx, state_dict in enumerate(states):
        # add previous states in order (already reversed)
        current_state = (idx == 0)
        row.append(html.Td(state_detail(state=state_dict, current_state=current_state)))
    return html.Table([html.Tr(row, id='state-table')])


def previous_states(states: List[dict]) -> html.Div:
    return html.Div([
        html.H4('Fleet States'),
        html.Div([
            _states_table(states)
        ]),
    ], className='row')


def generate_node_status_icon(status: dict) -> html.Td:
    # TODO: daq loading issue with dash >1.5.0
    # https://community.plot.ly/t/solved-intermittent-dash-dependency-exception-dash-daq-is-registered-but-the-path-requested-is-not-valid/31563
    status_message, color, missed = status['status'], status['color'], status['missed_confirmations']
    status_cell = daq.Indicator(id='Status',
                                color=color,
                                value=True,
                                size=10)  # pixels

    if missed > 0:
        status_message = f"{missed} missed confirmations"
    status = html.Td(status_cell, className='node-status-indicator', title=status_message)
    return status


def generate_node_row(node_info: dict) -> dict:

    identity = html.Td(children=html.Div([
        html.A(node_info['nickname'],
               href=f'https://{node_info["rest_url"]}/status',
               target='_blank')
    ]), className='node-nickname')

    # Fleet State
    fleet_state_div = []
    fleet_state_icon = node_info['fleet_state_icon']
    if fleet_state_icon is not UNKNOWN_FLEET_STATE:
        icon_list = node_info['fleet_state_icon']
        fleet_state_div = icon_list
    fleet_state = html.Td([html.Div(fleet_state_div)])

    staker_address = node_info['staker_address']
    etherscan_url = f'https://goerli.etherscan.io/address/{node_info["staker_address"]}'

    slang_last_seen = get_last_seen(node_info)

    status = generate_node_status_icon(node_info['status'])

    # Uptime
    king = 'uptime-king' if node_info.get('uptime_king') else ''
    baby = 'newborn' if node_info.get('newborn') else ''
    king_or_baby = king or baby
    uptime_cell = html.Td(node_info['uptime'], className='uptime-cell', id=king_or_baby, title=king_or_baby)
    components = {
        'Status': status,
        'Checksum': html.Td(html.A(f'{staker_address[:10]}...', href=etherscan_url, target='_blank'), className='node-address'),
        'Nickname': identity,
        'Uptime': uptime_cell,
        'Last Seen': html.Td([slang_last_seen]),
        'Fleet State': fleet_state,
        #'Peers ': html.Td(node_info['peers']),  # TODO
    }

    return components


def get_last_seen(node_info):
    try:
        slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
    except ParserError:
        # Show whatever we have anyways
        slang_last_seen = str(node_info['last_seen'])
    return slang_last_seen


def nodes_table(nodes, display_unconnected_nodes: bool = True) -> (html.Table, List):
    style_dict = {'overflowY': 'scroll'}

    rows = []
    for index, node_info in enumerate(nodes):
        row = list()

        # Fill columns
        components = generate_node_row(node_info=node_info)
        for col in NODE_TABLE_COLUMNS:
            cell = components[col]
            row.append(cell)

        # Handle In-line Row Styles
        row_class = 'connected-to-node'
        if 'No Connection' in get_last_seen(node_info):
            if display_unconnected_nodes:
                row_class = 'no-connection-to-node'
            else:
                continue

        # Aggregate
        rows.append(html.Tr(row, style=style_dict, className=f'node-row {row_class}'))
    table = html.Table(rows, id='node-table')
    return table


def known_nodes(nodes_dict: dict, teacher_checksum: str = None) -> List[html.Div]:
    components = dict()
    buckets = {'active': sorted([*nodes_dict['confirmed'], *nodes_dict['pending']], key=lambda n: n['timestamp']),
               'idle': nodes_dict['idle'],
               'inactive': nodes_dict['unconfirmed']}
    for label, nodes in list(buckets.items()):
        component = nodes_list_section(label, nodes, display_unconnected_nodes=True)
        components[label] = component
    return list(components.values())


def nodes_list_section(label, nodes, display_unconnected_nodes: bool = True):
    table = nodes_table(nodes, display_unconnected_nodes=display_unconnected_nodes)
    try:
        label_description = BUCKET_DESCRIPTIONS[label]
    except KeyError:
        label_description = ''

    total_nodes = len(nodes)

    tooltip = html.Div([
        html.H4(f'{label.capitalize()} Nodes ({total_nodes})'),
        html.Div([
            html.Img(src='/assets/info.png', className='info-icon'),
            html.Span(label_description, className='tooltiptext')], className='tooltip')
        ], className='label-and-tooltip')

    component = html.Div([
        html.Hr(),
        tooltip,
        html.Div([table])
    ], id=f"{label}-list")
    return component
