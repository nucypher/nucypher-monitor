from dash import dcc
from dash import html

# NOTE: changing this to an empty string is enough to remove the pinned message.
PINNED_MESSAGE_TEXT = 'This page is under active development with frequent updates: bugs/inaccuracies may be present.\n' \
                       'New issues can be filed at https://github.com/nucypher/nucypher-monitor/issues/.'

MINUTE_REFRESH_RATE = 60 * 1000
DAILY_REFRESH_RATE = MINUTE_REFRESH_RATE * 60 * 24
LOGO_PATH = '/assets/nucypher_logo.png'  # TODO: Configure assets path

# Buttons used for WS topic notifications
HIDDEN_BUTTONS = html.Div([
    html.Button("Refresh States",
                hidden=True,
                id='state-update-button',
                type='submit',
                className='nucypher-button button-primary'),
    html.Button("Refresh Known Nodes",
                hidden=True,
                id='node-update-button',
                type='submit',
                className='nucypher-button button-primary'),
])

if PINNED_MESSAGE_TEXT:
    PINNED_MESSAGE = html.Div([html.P(PINNED_MESSAGE_TEXT)], id='pinned-message')
else:
    PINNED_MESSAGE = ''

HEADER = html.Div([
    html.A(html.Img(src=LOGO_PATH, className='banner'), href='https://www.nucypher.com'),
    # html.Div(id='header'), TODO not needed?
    HIDDEN_BUTTONS],
    id="controls")

STATS = html.Div([
            html.Div(id='blocktime-value'),
            html.Div(id='registry'),
            html.Div([html.Div(id='current-period')]),
            html.Div(id='time-remaining'),
            html.Div(id='domain'),
            html.Div(id='active-stakers'),
            html.Div(id='staked-tokens'),
], id='stats')


GRAPHS = html.Div([
            html.Div(id='contracts'),
            html.Div(id='staker-breakdown'),
            html.Div(id='nodes-geolocation-graph'),
            html.Div(id='top-stakers-graph'),
            html.Div(id='prev-states'),
        ], id='widgets')

NETWORK_INFO_TABS = html.Div([
    html.H4('Network Information'),
    dcc.Tabs(id='network-info-tabs',
             parent_className='network-info-tabs-parent',
             children=[
                 dcc.Tab(label='Nodes', value='node-details', className='network-info-tab', selected_className='network-info-tab--selected'),
                 dcc.Tab(label='Issues/Events', value='event-details', className='network-info-tab', selected_className='network-info-tab--selected'),
             ],
             value='node-details'),
    html.Div(id='network-info-content')
])

CONTENT = html.Div([html.Div([STATS, GRAPHS, NETWORK_INFO_TABS])], id='main')

# Hidden div inside the app that stores previously decrypted heartbeats
HIDDEN_DIV = html.Div(id='cached-crawler-stats', style={'display': 'none'})

BODY = html.Div([
        dcc.Location(id='url', refresh=False),
        PINNED_MESSAGE,
        HEADER,
        HIDDEN_DIV,
        CONTENT,

        dcc.Interval(
            id='second-interval',
            interval=1 * 1000,  # in milliseconds
            n_intervals=0
        ),

        dcc.Interval(
            id='minute-interval',
            interval=MINUTE_REFRESH_RATE,
            n_intervals=0
        ),
        dcc.Interval(
            id='half-minute-interval',
            interval=(MINUTE_REFRESH_RATE / 2),
            n_intervals=0,
        ),
        dcc.Interval(
            id='daily-interval',
            interval=DAILY_REFRESH_RATE,
            n_intervals=0
        ),
        dcc.Interval(
            id='request-interval',
            interval=(MINUTE_REFRESH_RATE / 2),  # should ALWAYS be the minimum value of the intervals above
            n_intervals=0,
        )
    ])
