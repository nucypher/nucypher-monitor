from typing import List

import dash_daq as daq
import dash_html_components as html
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from maya import MayaDT
from pendulum.parsing import ParserError

import nucypher

NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Uptime', 'Last Seen', 'Fleet State']

NODE_LABEL_DESCRIPTIONS = {
    'confirmed': "Nodes that confirmed activity for the next period",
    'pending': "Nodes that previously confirmed activity for the current period but not for the next period",
    'idle': "Nodes that have never confirmed activity",
    'unconfirmed': "Nodes that have previously confirmed activity but have missed multiple periods since then",
    'unreachable':  "Nodes that are currently unreachable by the monitor",
}


def header() -> html.Div:
    return html.Div([html.Div(f'v{nucypher.__version__}', id='version')], className="logo-widget")


def state_detail(state: dict, current_state: bool) -> html.Div:
    children = [
        html.Div([
            html.Div(state['symbol'], className='single-symbol'),
        ], className='nucypher-nickname-icon', style={'border-color': state['color_hex']}),
        html.Span(state['nickname'], title=state['updated'])]

    if current_state:
        # add current annotation to children
        children.append(html.Span('(*Current)', style={'color': 'red'}))

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
        html.H4('Previous States'),
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
    #king = 'uptime-king' if node_info.get('uptime_king') else ''
    #baby = 'newborn' if node_info.get('newborn') else ''
    #king_or_baby = king or baby
    #uptime_cell = html.Td( html.Span(node_info['uptime']), className='uptime-cell', id=king_or_baby, title=king_or_baby),
    components = {
        'Status': status,
        'Checksum': html.Td(html.A(f'{staker_address[:10]}...', href=etherscan_url, target='_blank'), className='node-address'),
        'Nickname': identity,
        'Uptime': html.Td(html.Span(node_info['uptime']), className='uptime-cell'),
        'Last Seen': html.Td([slang_last_seen]),
        'Fleet State': fleet_state,
        #'Peers ': html.Td(node_info['peers']),
    }

    return components


def get_last_seen(node_info):
    try:
        slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
    except ParserError:
        # Show whatever we have anyways
        slang_last_seen = str(node_info['last_seen'])
    return slang_last_seen


def nodes_table(nodes, track_unreachable_nodes: bool = True) -> (html.Table, List):
    rows = []
    unreachable_nodes = [] if track_unreachable_nodes else None
    for index, node_info in enumerate(nodes):
        row = list()
        if track_unreachable_nodes and 'No Connection' in get_last_seen(node_info):
            unreachable_nodes.append(node_info)
            continue
        components = generate_node_row(node_info=node_info)
        for col in NODE_TABLE_COLUMNS:
            cell = components[col]
            row.append(cell)
        style_dict = {'overflowY': 'scroll'}
        rows.append(html.Tr(row, style=style_dict, className='node-row'))
    table = html.Table(rows, id='node-table')
    return table, unreachable_nodes


def known_nodes(nodes_dict: dict, teacher_checksum: str = None) -> List[html.Div]:
    components = list()
    unreachable_nodes = list()

    # nodes
    for label, nodes in list(nodes_dict.items()):
        component, unreachable = nodes_list_section(label, nodes)
        unreachable_nodes += unreachable
        components.append(component)

    # unreachable nodes
    if len(unreachable_nodes) > 0:
        label = 'unreachable'
        component, _ = nodes_list_section(label, unreachable_nodes, track_unreachable_nodes=False)
        components.append(component)

    return components


def nodes_list_section(label, nodes, track_unreachable_nodes: bool = True):
    table, unreachable_nodes = nodes_table(nodes, track_unreachable_nodes=track_unreachable_nodes)
    try:
        label_description = NODE_LABEL_DESCRIPTIONS[label]
    except KeyError:
        label_description = None

    component = html.Div([
        html.H4(f'{label.capitalize()} Nodes ({len(nodes)})'),
        html.P(label_description, className='nodes-list-description'),
        html.Br(),
        html.Div([table])
    ], id=f"{label}-list")
    return component, unreachable_nodes
