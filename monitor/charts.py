import dash_core_components as dcc
import maya
import plotly.graph_objs as go
import IP2Location

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
    colors = ['green', 'red', '#e0b32d']  # [active, inactive, pending] (sorted labels)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=list(data.keys()),
                values=staker_breakdown,
                textinfo='value',
                sort=False,  # sort by labels
                name='Stakers',
                marker=dict(colors=colors,
                            line=dict(width=2))
            )
        ],
        layout=go.Layout(
            title=f'Swarm Status',
            showlegend=True,
            font=dict(
                family="monospace",
                size=11,
                color="slategrey"
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            autosize=True,
            width=None,
            height=None
        ))

    graph = dcc.Graph(figure=fig,
                      id='staker-breakdown-graph',
                      config=GRAPH_CONFIG,
                      style={'width': '100%'})
    return graph


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
            marker=go.treemap.Marker(colors=list(data.keys()), colorscale='Viridis', line={"width": 2}),
            pathbar=dict(visible=False),
        ),
        layout=go.Layout(
            title=f'Top Stakers ({len(treemap_values)})',
            showlegend=False,
            font=dict(
                family="monospace",
                size=11,
                color="slategrey"
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            autosize=True,
            width=None,
            height=None,
        ))

    graph = dcc.Graph(figure=fig,
                      id='top-stakers',
                      config=GRAPH_CONFIG,
                      style={'width': '100%'})
    return graph


def nodes_geolocation_map(nodes_dict: dict, ip2loc: IP2Location):
    longitudes = []
    latitudes = []
    staker_text = []
    status_colors = []

    # determine geo locations
    for bucket in nodes_dict:
        nodes = nodes_dict[bucket]
        for node_info in nodes:
            rest_url = node_info['rest_url'][:-5]  # remove port number
            try:
                # get_all is called even if more specific element is requested eg. get_longitude
                geo_info = ip2loc.get_all(rest_url)
                long = geo_info.longitude
                lat = geo_info.latitude
                country = geo_info.country_long

                longitudes.append(long)
                latitudes.append(lat)
                staker_text.append(f"{node_info['staker_address']} ({country})")
                status_colors.append(node_info['status']['color'])
            except OSError:
                # TODO: log something? nothing to see here
                pass

    fig = go.Figure(
        data=go.Scattergeo(
            lon=longitudes,
            lat=latitudes,
            text=staker_text,
            hoverinfo='text',
            mode='markers',
            marker=dict(
                opacity=0.5,
                color=status_colors
            )
        ),
        layout=go.Layout(
            title='Node Locations',
            showlegend=False,
            geo=dict(
                scope='world',
                showframe=False,
                projection={'type': 'equirectangular'},
                showcountries=True,
                countrycolor='darkslategrey',
                showland=True,
                landcolor='slategrey',
                showcoastlines=True,
                coastlinecolor='darkslategrey',
                showlakes=False,
                bgcolor='rgba(0,0,0,0)',
            ),
            # font=dict(
            #     family='monospace',
            #     size=11,
            #     color='slategrey'
            # ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            autosize=True,
            width=None,
            height=None,
            margin=dict(
                l=1,
                r=1,
                b=1,
                t=1,
                pad=0
            )
        ))

    graph = dcc.Graph(figure=fig,
                      id='nodes-geolocation',
                      config=GRAPH_CONFIG,
                      style={'width': '100%', 'height': 750})
    return graph


def future_locked_tokens_bar_chart(future_locked_tokens: dict, past_locked_tokens: dict, node_history: dict):
    future_periods = len(future_locked_tokens)
    now = maya.now()

    nodes_history = list(node_history.values())

    # eg. Jan-23-2020
    date_format = '%b-%d-%Y'

    past_period_range = [d.strftime(date_format) for d in past_locked_tokens.keys()]
    future_period_range = list((now+maya.timedelta(days=p)).datetime().strftime(date_format) for p in range(1, future_periods + 1))
    period_range = past_period_range + future_period_range

    past_token_values = [float(v) for v in past_locked_tokens.values()]
    future_locked_tokens, future_num_stakers = map(list, zip(*future_locked_tokens.values()))
    locked_tokens = past_token_values + future_locked_tokens

    x_coord_today = now.datetime().strftime(date_format)

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
        # Known Nodes (past and future)
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
        ),

        # Today Vertical Line
        go.Scatter(
            x=[x_coord_today, x_coord_today],
            y=[0, max(locked_tokens) * 1.1],  # point slightly above actual max
            name='',
            text=['', 'Today'],
            mode='lines+text',
            textposition='top center',
            hoverinfo='none',
            line=dict(
                color='Red',
                width=4,
                dash='dashdot',
            ),
            textfont=dict(
                color='Red',
            )
        )
    ]

    layout = go.Layout(
            title=f'Stake and Stakers | {period_range[0].capitalize()} - {period_range[-1]}',
            xaxis={'title': 'Days'},
            yaxis={'title': 'NU Tokens', 'rangemode': 'tozero', 'showgrid': False},
            yaxis2={'title': f'Stakers', 'overlaying': 'y', 'side': 'right', 'rangemode': 'tozero', 'showgrid': False},
            showlegend=False,
            legend=go.layout.Legend(x=0, y=1.0),
            font=dict(
                family="monospace",
                size=11,
                color="slategrey"
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            autosize=True,
            width=None,
            height=None
    )

    fig = go.Figure(data=plots, layout=layout)
    fig.update_traces(marker_line_width=0.1, opacity=1)
    fig.update_layout(bargap=0.15)
    graph = dcc.Graph(figure=fig,
                      id='locked-stake',
                      config=GRAPH_CONFIG,
                      style={'width': '100%'})
    return graph
