from dash import dcc
from dash import html

# NOTE: changing this to an empty string is enough to remove the pinned message.
PINNED_MESSAGE_TEXT = 'We are upgrading to Threshold Network (https://threshold.network)!'

MINUTE_REFRESH_RATE = 60 * 1000
DAILY_REFRESH_RATE = MINUTE_REFRESH_RATE * 60 * 24
NU_LOGO_PATH = '/assets/nucypher_logo.png'  # TODO: Configure assets path
THRESHOLD_LOGO_PATH = '/assets/threshold_wordmark.png'

if PINNED_MESSAGE_TEXT:
    PINNED_MESSAGE = html.Div([html.P(PINNED_MESSAGE_TEXT)], id='pinned-message')
else:
    PINNED_MESSAGE = ''

HEADER = html.Div([
        html.A(html.Img(src=NU_LOGO_PATH, className='banner'), href='https://www.nucypher.com', target='_'),
    ],
    id="controls")

THRESHOLD_NOTE = html.Div([
        html.A(html.Img(src=THRESHOLD_LOGO_PATH, className='threshold_wordmark'), href='https://threshold.network', target='_'),
        html.P('We are upgrading to the Threshold Network!'),
        html.Br(),
        html.P('Network information is currently not displayable on the status '
               'dashboard during the upgrade to Threshold.'),
        html.Br(),
        html.P('Existing NU and KEEP stakers will be grandfathered into Threshold '
               'via special staking adapters. It is not necessary to keep your '
               'worker node up until the instructions for Threshold staking '
               'are shared.'),
        html.Br(),
        html.P('Rest assured, your legacy NU stakes are safe and will be eligible '
               'to be utilized by Threshold Network via a staking adapter to instead '
               'earn rewards in the T token.')
    ],
    id='threshold_note')

STATS = html.Div([
            html.Div(id='domain'),
            html.Div([html.Div(id='current-period')]),
            html.Div(id='staked-tokens'),
            html.Div(id='worklock-status'),
], id='stats')


BLOCKCHAIN_DATA = html.Div([
            html.Div(id='registry'),
            html.Div(id='contracts'),
        ], id='widgets')

CONTENT = html.Div([html.Div([STATS, BLOCKCHAIN_DATA])], id='main')

BODY = html.Div([
        dcc.Location(id='url', refresh=False),
        PINNED_MESSAGE,
        HEADER,
        THRESHOLD_NOTE,
        CONTENT,
    ])
