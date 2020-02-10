from typing import List

import dash_daq as daq
import dash_html_components as html
import dash_table
from maya import MayaDT
from pendulum.parsing import ParserError

import nucypher
from nucypher.blockchain.eth.token import NU

NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Uptime', 'Last Seen', 'Fleet State']
NODE_TABLE_COLUMNS_PROPERTIES = {
    'Status': dict(name=NODE_TABLE_COLUMNS[0], id=NODE_TABLE_COLUMNS[0], editable=False, presentation='markdown'),
    'Checksum': dict(name=NODE_TABLE_COLUMNS[1], id=NODE_TABLE_COLUMNS[1], editable=False, type='text', presentation='markdown'),
    'Nickname': dict(name=NODE_TABLE_COLUMNS[2], id=NODE_TABLE_COLUMNS[2], editable=False, type='text', presentation='markdown'),
    'Uptime': dict(name=NODE_TABLE_COLUMNS[3], id=NODE_TABLE_COLUMNS[3], editable=False),
    'Last Seen': dict(name=NODE_TABLE_COLUMNS[4], id=NODE_TABLE_COLUMNS[4], editable=False),
    'Fleet State': dict(name=NODE_TABLE_COLUMNS[5], id=NODE_TABLE_COLUMNS[5], editable=False),
}
NODE_TABLE_PAGE_SIZE = 100

STATUS_IMAGE_PATHS = {
    'Confirmed': '/assets/status_confirmed.png',
    'Idle': '/assets/status_idle.png',
    'Pending': '/assets/status_pending.png',
    'Unconfirmed': '/assets/status_unconfirmed.png',
}


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

NODE_STATUS_URL_TEMPLATE = "https://{}/status"


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


def generate_node_row(node_info: dict) -> dict:
    staker_address = node_info['staker_address']
    etherscan_url = ETHERSCAN_URL_TEMPLATE.format(staker_address)

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
    return slang_last_seen


def nodes_table(nodes) -> (html.Table, List):
    rows = list()
    for index, node_info in enumerate(nodes):
        # Fill columns
        components = generate_node_row(node_info=node_info)
        rows.append(components)

    table = dash_table.DataTable(columns=[NODE_TABLE_COLUMNS_PROPERTIES[col] for col in NODE_TABLE_COLUMNS],
                                 data=rows,
                                 fixed_rows=dict(headers=True, data=0),
                                 filter_action='native',
                                 page_current=0,
                                 page_size=NODE_TABLE_PAGE_SIZE,
                                 page_action='native',
                                 style_as_list_view=True,
                                 style_cell={
                                      'overflow': 'hidden',
                                      'textOverflow': 'ellipsis',
                                      'maxWidth': 0,
                                      'background-color': 'rgba(0,0,0,0)',
                                      'text-align': 'left',
                                      'font-size': '1.2rem'
                                 },
                                 style_header={
                                     'font-style': 'bold'
                                 },
                                 style_cell_conditional=[
                                     {  # nickname column should try to fit entire name
                                         'if': {
                                             'column_id': 'Nickname'
                                         },
                                         'width': '30%'
                                     },
                                     {
                                         'if': {
                                             'column_id': 'Status'
                                         },
                                         'vertical-align': 'center',
                                         'width': '5%'
                                     },
                                 ],
                                 style_data_conditional=[
                                     {  # no connection to node styling
                                         'if': {
                                             'filter_query': '{Last Seen} eq "No Connection to Node"'
                                         },
                                         'opacity': 0.5
                                     },
                                 ])
    return table


def known_nodes(nodes_dict: dict, teacher_checksum: str = None) -> List[html.Div]:
    components = []
    buckets = {'active': sorted([*nodes_dict['confirmed'], *nodes_dict['pending']], key=lambda n: n['timestamp']),
               'idle': nodes_dict['idle'],
               'inactive': nodes_dict['unconfirmed']}
    for label, nodes in list(buckets.items()):
        component = nodes_list_section(label, nodes)
        components.append(component)
    return components


def nodes_list_section(label, nodes):
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

    table = nodes_table(nodes)

    component = html.Div([
        html.Div([
            html.Hr(),
            tooltip,
        ], id=f"{label}-list"),
        table])
    return component
