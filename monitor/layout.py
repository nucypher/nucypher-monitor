import dash_core_components as dcc
import dash_html_components as html

# NOTE: changing this to an empty string is enough to remove the pinned message.
PINNED_MESSAGE_TEXT = 'This page is under active development: bugs and inaccuracies may be present.  '\
                      'New issues can be filed at https://github.com/nucypher/nucypher-monitor/issues/.'\

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
    PINNED_MESSAGE = html.Div(PINNED_MESSAGE_TEXT, id='pinned-message')
else:
    PINNED_MESSAGE = ''

HEADER = html.Div([
    html.A(html.Img(src=LOGO_PATH, className='banner'), href='https://www.nucypher.com'),
    html.Div(id='header'),
    HIDDEN_BUTTONS],
    id="controls")

STATS = html.Div([
            html.Div(id='blocktime-value'),
            html.Div(id='registry'),
            html.Div([html.Div(id='current-period')]),
            html.Div(id='time-remaining'),
            html.Div(id='domains'),
            html.Div(id='active-stakers'),
            html.Div(id='staked-tokens'),
], id='stats')


GRAPHS = html.Div([
            html.Div(id='contracts'),
            html.Div(id='staker-breakdown'),
            # html.Div(id='prev-work-orders-graph'),  # TODO
            html.Div(id='top-stakers-graph'),
            html.Div(id='locked-stake-graph'),
            html.Div(id='prev-states'),
        ], id='widgets')

CONTENT = html.Div([html.Div([STATS, GRAPHS, html.Div([html.Div(id='known-nodes')])])], id='main')

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
