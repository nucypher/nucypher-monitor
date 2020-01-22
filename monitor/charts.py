import dash_core_components as dcc
import maya
import plotly.graph_objs as go

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


def historical_work_orders_line_chart(data: dict):
    return _historical_line_chart(chart_id='prev-orders-graph',
                                  chart_title=f'Num Work Orders over the previous {len(data)} days',
                                  y_title='Work Orders',
                                  data=data)


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
            title=f'Staker Status',
            showlegend=True,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))

    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='staker-breakdown-graph', config=GRAPH_CONFIG)


def top_stakers_chart(data: dict):
    data_values_list = list(data.values())
    total_staked = sum(data_values_list)

    # add Total entry as root element
    treemap_labels = (list(data.keys()) + ['Total'])
    treemap_values = data_values_list + [total_staked]
    treemap_parents = ['Total'] * len(data) + ['']  # set parent of Total entry to be root ('')

    fig = go.Figure(
        data=go.Treemap(
            branchvalues="total",
            labels=treemap_labels,
            name='',
            parents=treemap_parents,
            values=treemap_values,
            textinfo='none',
            hovertemplate="<b>%{label} </b> <br> Stake Size: %{value:,.2f} NU<br> % of Network: %{percentRoot:.3% %}",
            marker=go.treemap.Marker(colors=data_values_list, colorscale='Viridis', line={"width": 2}, showscale=True),
            pathbar=dict(visible=False),
        ),
        layout=go.Layout(
            title=f'Top Stakers',
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        ))
    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='top-stakers-graph', config=GRAPH_CONFIG)


def future_locked_tokens_bar_chart(future_locked_tokens: dict, past_locked_tokens: dict, node_history: dict):
    future_periods = len(future_locked_tokens)
    now = maya.now()

    nodes_history = list(node_history.values())

    past_period_range = [maya.MayaDT.from_datetime(d).slang_date() for d in past_locked_tokens.keys()]
    future_period_range = list((now+maya.timedelta(days=p)).slang_date() for p in range(1, future_periods + 1))
    period_range = past_period_range + future_period_range

    past_token_values = [float(v) for v in past_locked_tokens.values()]
    future_locked_tokens, future_num_stakers = map(list, zip(*future_locked_tokens.values()))
    locked_tokens = past_token_values + future_locked_tokens

    plots = [

        #
        # Stakes
        #

        go.Bar(
            textposition='auto',
            x=period_range,
            y=locked_tokens,
            name='Stake (NU)',
            marker=go.bar.Marker(color=locked_tokens, colorscale='Viridis')
        ),

        #
        # Known Nodes
        #

        go.Scatter(
            mode='lines+markers',
            x=past_period_range,
            y=nodes_history,
            name='Past Stakers',
            yaxis='y2',
            xaxis='x',
            marker={'color': 'rgb(0, 163, 139)'}
        ),
        go.Scatter(
            mode='lines+markers',
            x=future_period_range,
            y=future_num_stakers,
            name='Future Stakers',
            yaxis='y2',
            xaxis='x',
            marker={'color': 'rgb(0, 153, 239)'}
        )
    ]

    layout = go.Layout(
            title=f'Staked NU and Stakers | {period_range[0]} - {period_range[-1]}',
            xaxis={'title': 'Days'},
            yaxis={'title': 'NU Tokens', 'rangemode': 'tozero', 'showgrid': False},
            yaxis2={'title': f'Past Stakers', 'overlaying': 'y', 'side': 'right', 'rangemode': 'tozero', 'showgrid': False},
            showlegend=False,
            legend=go.layout.Legend(x=0, y=1.0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )

    fig = go.Figure(data=plots, layout=layout)
    fig['layout'].update(autosize=True, width=None, height=None)
    return dcc.Graph(figure=fig, id='locked-stake', config=GRAPH_CONFIG)
