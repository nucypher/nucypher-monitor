from datetime import datetime, timedelta
from string import Template

import dash_html_components as html
from dash import Dash
from dash.dependencies import Output, Input
from flask import Flask
from maya import MayaDT
from twisted.logger import Logger

from monitor import layout, components, settings
from monitor.charts import (
    future_locked_tokens_bar_chart,
    historical_locked_tokens_bar_chart,
    stakers_breakdown_pie_chart,
    historical_known_nodes_line_chart
)
from monitor.crawler import Crawler, CrawlerNodeStorage
from monitor.db import CrawlerBlockchainDBClient, CrawlerNodeMetadataDBClient
from monitor.settings import TEMPLATE_PATH
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.token import NU


class Dashboard:
    """
    Dash Status application for monitoring a swarm of nucypher Ursula nodes.
    """

    def __init__(self,
                 registry,
                 flask_server: Flask,
                 route_url: str,
                 domain: str,
                 blockchain_db_host: str,
                 blockchain_db_port: int,
                 node_db_filepath: str = CrawlerNodeStorage.DEFAULT_DB_FILEPATH):

        self.log = Logger(self.__class__.__name__)

        # Database
        self.node_metadata_db_client = CrawlerNodeMetadataDBClient(db_filepath=node_db_filepath)
        self.network_crawler_db_client = CrawlerBlockchainDBClient(host=blockchain_db_host,
                                                                   port=blockchain_db_port,
                                                                   database=Crawler.BLOCKCHAIN_DB_NAME)

        # Blockchain & Contracts
        self.registry = registry
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Dash
        self.make_dash_app(flask_server=flask_server, route_url=route_url, domain=domain)

    def make_dash_app(monitor, flask_server: Flask, route_url: str, domain: str):
        dash_app = Dash(name=__name__,
                        server=flask_server,
                        assets_folder=settings.ASSETS_PATH,
                        url_base_pathname=route_url,
                        suppress_callback_exceptions=False)  # TODO: Set to True by default or make configurable

        # Initial State
        dash_app.title = settings.TITLE
        dash_app.layout = layout.BODY

        @dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return components.header()

        @dash_app.callback(Output('prev-states', 'children'),
                           [Input('state-update-button', 'n_clicks'), Input('minute-interval', 'n_intervals')])
        def state(n_clicks, n_intervals):
            states_dict_list = monitor.node_metadata_db_client.get_previous_states_metadata()
            return components.previous_states(states_dict_list=states_dict_list)

        @dash_app.callback(Output('known-nodes', 'children'),
                           [Input('node-update-button', 'n_clicks'), Input('half-minute-interval', 'n_intervals')])
        def known_nodes(n_clicks, n_intervals):
            known_nodes_dict = monitor.node_metadata_db_client.get_known_nodes_metadata()
            teacher_checksum = monitor.node_metadata_db_client.get_current_teacher_checksum()
            return components.known_nodes(nodes_dict=known_nodes_dict,
                                          registry=monitor.registry,
                                          teacher_checksum=teacher_checksum)

        @dash_app.callback(Output('active-stakers', 'children'), [Input('minute-interval', 'n_intervals')])
        def active_stakers(n):
            confirmed, pending, inactive = monitor.staking_agent.partition_stakers_by_activity()
            total_stakers = len(confirmed) + len(pending) + len(inactive)
            return html.Div([html.H4("Active Ursulas"), html.H5(f"{len(confirmed)}/{total_stakers}")])

        @dash_app.callback(Output('staker-breakdown', 'children'), [Input('minute-interval', 'n_intervals')])
        def stakers_breakdown(n):
            return stakers_breakdown_pie_chart(staking_agent=monitor.staking_agent)

        @dash_app.callback(Output('current-period', 'children'), [Input('minute-interval', 'n_intervals')])
        def current_period(pathname):
            return html.Div([html.H4("Current Period"), html.H5(monitor.staking_agent.get_current_period())])

        @dash_app.callback(Output('time-remaining', 'children'), [Input('minute-interval', 'n_intervals')])
        def time_remaining(n):
            tomorrow = datetime.utcnow() + timedelta(days=1)
            midnight = datetime(year=tomorrow.year, month=tomorrow.month,
                                day=tomorrow.day, hour=0, minute=0, second=0, microsecond=0)
            seconds_remaining = MayaDT.from_datetime(midnight).slang_time()
            return html.Div([html.H4("Next Period"), html.H5(seconds_remaining)])

        @dash_app.callback(Output('domains', 'children'), [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            return html.Div([html.H4('Domain'), html.H5(domain)])

        @dash_app.callback(Output('staked-tokens', 'children'), [Input('minute-interval', 'n_intervals')])
        def staked_tokens(n):
            nu = NU.from_nunits(monitor.staking_agent.get_global_locked_tokens())
            return html.Div([html.H4('Staked Tokens'), html.H5(f"{nu}")])

        @dash_app.callback(Output('prev-locked-stake-graph', 'children'), [Input('daily-interval', 'n_intervals')])
        def prev_locked_tokens(n):
            prior_periods = 30
            locked_tokens_data = monitor.network_crawler_db_client.get_historical_locked_tokens_over_range(prior_periods)
            return historical_locked_tokens_bar_chart(locked_tokens=locked_tokens_data)

        @dash_app.callback(Output('prev-num-stakers-graph', 'children'), [Input('daily-interval', 'n_intervals')])
        def historical_known_nodes(n):
            prior_periods = 30
            num_stakers_data = monitor.network_crawler_db_client.get_historical_num_stakers_over_range(prior_periods)
            return historical_known_nodes_line_chart(data=num_stakers_data)

        @dash_app.callback(Output('locked-stake-graph', 'children'), [Input('daily-interval', 'n_intervals')])
        def future_locked_tokens(n):
            return future_locked_tokens_bar_chart(staking_agent=monitor.staking_agent)
