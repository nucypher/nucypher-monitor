import dash_core_components as dcc
import dash_html_components as html

MINUTE_REFRESH_RATE = 60 * 1000
DAILY_REFRESH_RATE = MINUTE_REFRESH_RATE * 60 * 24

BODY = html.Div([
        dcc.Location(id='url', refresh=False),

        # Update buttons also used for WS topic notifications
        html.Div([
            html.Img(src='/assets/nucypher_logo.svg', className='banner'),  # TODO: Configure assets path
            html.Div(id='header'),
            html.Div([
                html.Button("Refresh States", id='state-update-button', type='submit',
                            className='nucypher-button button-primary'),
                html.Button("Refresh Known Nodes", id='node-update-button', type='submit',
                            className='nucypher-button button-primary'),
            ])
        ], id="controls"),

        ###############################################################

        html.Div([

            html.Div([

                # Stats
                html.Div([
                    html.Div(id='current-period'),
                    html.Div(id='time-remaining'),
                    html.Div(id='domains'),
                    html.Div(id='active-stakers'),
                    html.Div(id='staked-tokens'),
                ], id='stats'),

                # Charts
                html.Div([
                    html.Div(id='staker-breakdown'),
                    html.Div(id='prev-num-stakers-graph'),
                    html.Div(id='prev-locked-stake-graph'),
                    html.Div(id='locked-stake-graph'),
                    html.Div(id='prev-states'),
                ], id='widgets'),

                # Known Nodes Table
                html.Div([
                    html.Div(id='known-nodes'),
                ])
            ]),

        ], id='main'),

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
        )
    ])
