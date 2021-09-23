from typing import List

from dash import dash_table, html
from maya import MayaDT
from nucypher.blockchain.eth.token import NU
from pendulum.parsing import ParserError

from monitor.utils import get_etherscan_url, EtherscanURLType

NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Uptime', 'Last Seen', 'Fleet State']
NODE_TABLE_COLUMNS_PROPERTIES = {
    'Status': dict(name=NODE_TABLE_COLUMNS[0], id=NODE_TABLE_COLUMNS[0], editable=False, presentation='markdown'),
    'Checksum': dict(name=NODE_TABLE_COLUMNS[1], id=NODE_TABLE_COLUMNS[1], editable=False, type='text', presentation='markdown'),
    'Nickname': dict(name=NODE_TABLE_COLUMNS[2], id=NODE_TABLE_COLUMNS[2], editable=False, type='text', presentation='markdown'),
    'Uptime': dict(name=NODE_TABLE_COLUMNS[3], id=NODE_TABLE_COLUMNS[3], editable=False),
    'Last Seen': dict(name=NODE_TABLE_COLUMNS[4], id=NODE_TABLE_COLUMNS[4], editable=False),
    'Fleet State': dict(name=NODE_TABLE_COLUMNS[5], id=NODE_TABLE_COLUMNS[5], editable=False),
}
NODE_TABLE_PAGE_SIZE = 80

STATUS_IMAGE_PATHS = {
    'Confirmed': '/assets/status/status_confirmed.png',  # green
    'Idle': '/assets/status/status_idle.png',  # 525ae3
    'Pending': '/assets/status/status_pending.png',  # e0b32d
    'Unconfirmed': '/assets/status/status_unconfirmed.png',  # red
}


# Note: Unused entries will be ignored
BUCKET_DESCRIPTIONS = {
    'active': "Nodes that are currently confirmed or pending",
    'confirmed': "Nodes that confirmed activity for the next period",
    'pending': "Nodes that previously confirmed activity for the current period but not for the next period",
    'idle': "Nodes that have never confirmed.",
    'inactive': "Nodes that previously confirmed activity but have missed multiple periods since then.",
    'unconnected': "Nodes that the monitor has not connected to - can be temporary while learning about the network (nodes should NOT remain here)",
}

NODE_STATUS_URL_TEMPLATE = "https://{}/status"

NO_CONNECTION_TO_NODE = "No Connection to Node"
NOT_YET_CONNECTED_TO_NODE = "Not Yet Connected to Node"

# TODO - not needed?
# def header() -> html.Div:
#     return html.Div([html.Div(f'v{nucypher.__version__}', id='version')], className="logo-widget")


def make_contract_row(network: str, agent, balance: NU = None):
    contract_name = agent.contract_name
    contract_address = agent.contract_address
    cells = [
        html.A(f'{contract_name} {contract_address} ({agent.contract.version})',
               id=f"{contract_name}-contract-address",
               href=get_etherscan_url(network, EtherscanURLType.ADDRESS, contract_address))
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


def generate_node_row(network: str, node_info: dict) -> dict:
    staker_address = node_info['staker_address']
    etherscan_url = get_etherscan_url(network, EtherscanURLType.ADDRESS, staker_address)

    slang_last_seen = get_last_seen(node_info)

    status = node_info['status']['status']
    status_image_path = STATUS_IMAGE_PATHS[status]
    node_row = {
        NODE_TABLE_COLUMNS[0]: f'![{status}]({status_image_path})',
        NODE_TABLE_COLUMNS[1]: f'[{staker_address[:10]}...]({etherscan_url})',
        NODE_TABLE_COLUMNS[2]: f'[{node_info["nickname"]}]({NODE_STATUS_URL_TEMPLATE.format(node_info["rest_url"])})',
        NODE_TABLE_COLUMNS[3]: node_info['uptime'],
        NODE_TABLE_COLUMNS[4]: slang_last_seen,
        NODE_TABLE_COLUMNS[5]: node_info['fleet_state_icon'],
        #'Peers ': html.Td(node_info['peers']),  # TODO
    }

    return node_row


def get_last_seen(node_info):
    try:
        slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
    except ParserError:
        # Show whatever we have anyways
        slang_last_seen = str(node_info['last_seen'])

    if slang_last_seen == NO_CONNECTION_TO_NODE:
        slang_last_seen = NOT_YET_CONNECTED_TO_NODE

    return slang_last_seen


def nodes_table(network: str, nodes: List) -> dash_table.DataTable:
    rows = list()
    table_tooltip_data = list()

    king_nickname = ''
    newborn_nickname = ''
    for index, node_info in enumerate(nodes):
        # Fill columns
        components = generate_node_row(network=network, node_info=node_info)
        rows.append(components)
        if node_info.get('uptime_king'):
            king_nickname = components['Nickname']
        elif node_info.get('newborn'):
            newborn_nickname = components['Nickname']

        if node_info['status']['status'] == 'Unconfirmed':
            # add to tooltip
            missed_confirmations = node_info['status']['missed_confirmations']
            table_tooltip_data.append({NODE_TABLE_COLUMNS[0]: f"{missed_confirmations} missed confirmations"})

    style_table = {'minHeight': '100%',
                   'height': '100%',
                   'maxHeight': 'none'}

    # static properties of table are overridden (!important) via stylesheet.css (.node-table class css entries)
    table = dash_table.DataTable(columns=[NODE_TABLE_COLUMNS_PROPERTIES[col] for col in NODE_TABLE_COLUMNS],
                                 data=rows,
                                 fixed_rows=dict(headers=True, data=0),
                                 filter_action='native',
                                 page_size=NODE_TABLE_PAGE_SIZE,
                                 page_action='native',
                                 style_as_list_view=True,
                                 style_table=style_table,
                                 tooltip_data=table_tooltip_data,
                                 style_header={'backgroundColor': 'rgb(30, 30, 30)'},
                                 style_cell={'backgroundColor': 'rgb(33, 33, 36)'},
                                 style_cell_conditional=[
                                     {  # nickname column - should make best effort to fit entire name
                                         'if': {
                                             'column_id': 'Nickname'
                                         },
                                         'width': '30%'
                                     },
                                     {  # status column - try to keep relatively small
                                         'if': {
                                             'column_id': 'Status'
                                         },
                                         'width': '5%'
                                     }
                                 ],
                                 style_data_conditional=[
                                     {  # no connection to node styling
                                         'if': {
                                             'filter_query': f'{{Last Seen}} eq "{NOT_YET_CONNECTED_TO_NODE}"'
                                         },
                                         # 'opacity': 0.45
                                     },
                                     {  # highlight king
                                         'if': {
                                             'column_id': 'Uptime',
                                             'filter_query': f'{{Nickname}} eq "{king_nickname}"'
                                         },
                                         'color': 'rgb(169, 162, 101)',
                                         'font-size': '1.2em',
                                         'font-weight': 900
                                     },
                                     {  # highlight baby
                                         'if': {
                                             'column_id': 'Uptime',
                                             'filter_query': f'{{Nickname}} eq "{newborn_nickname}"'
                                         },
                                         'color': 'rgb(141, 78, 171)',
                                         'font-size': '1.2em',
                                         'font-weight': 900
                                     },
                                 ])
    return table


def known_nodes(network: str, nodes_dict: dict) -> List[html.Div]:
    components = []
    buckets = {'active': sorted([*nodes_dict.get('confirmed', []), *nodes_dict.get('pending', [])],
                                key=lambda n: n['timestamp']),
               'idle': nodes_dict.get('idle', []),
               'inactive': nodes_dict.get('unconfirmed', [])}
    for label, nodes in list(buckets.items()):
        component = nodes_list_section(network, label, nodes)
        components.append(component)
    return components


def nodes_list_section(network: str, label: str, nodes: List):
    try:
        label_description = BUCKET_DESCRIPTIONS[label]
    except KeyError:
        label_description = ''

    total_nodes = len(nodes)

    tooltip = html.Div([
        html.H4(f'{label.capitalize()} Nodes ({total_nodes})'),
        html.Div([
            html.Img(src='/assets/status/status_info.png', className='info-icon'),
            html.Span(label_description, className='tooltiptext')
        ], className='tooltip')
    ], className='label-and-tooltip')

    table = nodes_table(network, nodes)

    component = html.Div([
            html.Div([
                tooltip,
            ], id=f"{label}-list"),
            html.Div([table], className='info-table')
        ])
    return component
