import dash_core_components as dcc
import plotly.graph_objs as go

from nucypher.blockchain.eth.token import NU

GRAPH_CONFIG = {'displaylogo': False,
                'autosizable': True,
                'responsive': True,
                'fillFrame': False,
                'displayModeBar': False}

LINE_CHART_MARKER_COLOR = 'rgb(0, 163, 239)'


def _historical_line_chart(chart_id: str, chart_title: str, y_title: str, data: dict):
    fig = go.Figure(data=[
            go.Scatter(
                mode='lines+markers',
                x=list(data.keys()),
                y=list(data.values()),
                marker={'color': LINE_CHART_MARKER_COLOR}
            )
        ],
        layout=go.Layout(
            title=chart_title,
            xaxis={'title': 'Date', 'nticks': len(data) + 1, 'showgrid': False},
            yaxis={'title': y_title, 'zeroline': False, 'showgrid': False, 'rangemode': 'tozero'},
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))

    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id=chart_id, config=GRAPH_CONFIG)


def historical_known_nodes_line_chart(data: dict):
    return _historical_line_chart(chart_id='prev-stakers-graph',
                                  chart_title=f'Num Stakers over the previous {len(data)} days',
                                  y_title='Stakers',
                                  data=data)


def historical_work_orders_line_chart(data: dict):
    return _historical_line_chart(chart_id='prev-orders-graph',
                                  chart_title=f'Num Work Orders over the previous {len(data)} days',
                                  y_title='Work Orders',
                                  data=data)


def historical_locked_tokens_bar_chart(locked_tokens: dict):
    prior_periods = len(locked_tokens)
    token_values = list(locked_tokens.values())
    fig = go.Figure(data=[
        go.Bar(
            textposition='auto',
            x=list(locked_tokens.keys()),
            y=token_values,
            name='Locked Stake',
            marker=go.bar.Marker(color=token_values, colorscale='Viridis')
        )
    ],
        layout=go.Layout(
            title=f'Staked NU over the previous {prior_periods} days',
            xaxis={'title': 'Date', 'nticks': len(locked_tokens) + 1},
            yaxis={'title': 'NU Tokens', 'zeroline': False, 'rangemode': 'tozero'},
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))

    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='prev-locked-graph', config=GRAPH_CONFIG)


def stakers_breakdown_pie_chart(data):
    staker_breakdown = list(data.values())
    colors = ['#FAE755', '#74C371', '#3E0751']  # colors from Viridis colorscale
    fig = go.Figure(
        data=[
            go.Pie(
                labels=list(data.keys()),
                values=staker_breakdown,
                textinfo='value',
                name='Stakers',
                marker=dict(colors=colors,
                            line=dict(width=2))
            )
        ],
        layout=go.Layout(
            title=f'Breakdown of Network Stakers',
            showlegend=True,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))

    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='staker-breakdown-graph', config=GRAPH_CONFIG)


def future_locked_tokens_bar_chart(data):
    periods = len(data)
    period_range = list(range(1, periods + 1))
    future_locked_tokens, future_num_stakers = map(list, zip(*data.values()))
    fig = go.Figure(data=[
            go.Bar(
                textposition='auto',
                x=period_range,
                y=future_locked_tokens,
                name='Stake (NU)',
                marker=go.bar.Marker(color=future_locked_tokens, colorscale='Viridis')
            ),
            go.Scatter(
                mode='lines+markers',
                x=period_range,
                y=future_num_stakers,
                name='Stakers',
                yaxis='y2',
                xaxis='x',
                marker={'color': LINE_CHART_MARKER_COLOR}
            )
        ],
        layout=go.Layout(
            title=f'Staked NU and Stakers over the next {periods} days.',
            xaxis={'title': 'Days'},
            yaxis={'title': 'NU Tokens', 'rangemode': 'tozero', 'showgrid': False},
            yaxis2={'title': f'Stakers', 'overlaying': 'y', 'side': 'right', 'rangemode': 'tozero', 'showgrid': False},
            showlegend=False,
            legend=go.layout.Legend(x=0, y=1.0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))

    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='locked-graph', config=GRAPH_CONFIG)
