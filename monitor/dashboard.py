import json
from os import path

import IP2Location
import dash_html_components as html
import requests
from dash import Dash
from dash.dependencies import Output, Input, State
from flask import Flask, request
from maya import MayaDT
from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import (
    StakingEscrowAgent,
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
    AdjudicatorAgent
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU
from twisted.logger import Logger

from monitor import layout, components, settings
from monitor.charts import (
    stakers_breakdown_pie_chart,
    top_stakers_chart,
    nodes_geolocation_map
)
from monitor.components import make_contract_row
from monitor.crawler import Crawler
from monitor.db import CrawlerInfluxClient
from monitor.supply import calculate_supply_information, calculate_current_total_supply, calculate_circulating_supply


class Dashboard:
    """
    Dash Status application for monitoring a swarm of nucypher Ursula nodes.
    """

    def __init__(self,
                 registry,
                 flask_server: Flask,
                 route_url: str,
                 network: str,
                 crawler_host: str,
                 crawler_port: int,
                 influx_host: str,
                 influx_port: int):

        self.log = Logger(self.__class__.__name__)

        # Crawler
        self.crawler_host = crawler_host
        self.crawler_port = crawler_port
        self.influx_client = CrawlerInfluxClient(host=influx_host, port=influx_port, database=Crawler.INFLUX_DB_NAME)

        # Blockchain & Contracts
        self.network = network
        self.registry = registry

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

        # Add informational endpoints
        # Supply
        self.add_supply_endpoint(flask_server=flask_server)

        # TODO: Staker

        # Dash
        self.dash_app = self.make_dash_app(flask_server=flask_server, route_url=route_url)

        # GeoLocation
        iplocation_file = path.join(settings.ASSETS_PATH, 'geolocation', 'IP2LOCATION-LITE-DB5.BIN')
        self.ip2loc = IP2Location.IP2Location(filename=iplocation_file)

    def make_request(self):
        url = f'http://{self.crawler_host}:{self.crawler_port}/{Crawler.METRICS_ENDPOINT}'
        response = requests.get(url=url)
        payload = response.json()
        return payload

    def verify_cached_stats(self, cached_stats):
        if cached_stats is None:
            # cached stats may not have been populated by the time it is attempted to be read from
            # get data directly from the crawler - not expected to happen more than a few times during first page load
            data = self.make_request()
        else:
            data = json.loads(cached_stats)
        return data

    def add_supply_endpoint(self, flask_server: Flask):
        @flask_server.route('/supply_information', methods=["GET"])
        def supply_information():
            economics = EconomicsFactory.retrieve_from_blockchain(registry=self.registry)

            parameter = request.args.get('q')
            if parameter is None:
                # no query - return all supply information
                supply_info = calculate_supply_information(economics=economics)
                response = flask_server.response_class(
                    response=json.dumps(supply_info),
                    status=200,
                    mimetype='application/json'
                )
            else:
                # specific request query provided
                if parameter == 'current_total_supply':
                    current_total_supply = calculate_current_total_supply(economics)
                    response = flask_server.response_class(
                        response=str(current_total_supply),
                        status=200,
                        mimetype='text/plain'
                    )
                elif parameter == 'est_circulating_supply':
                    est_circulating_supply = calculate_circulating_supply(economics)
                    response = flask_server.response_class(
                        response=str(est_circulating_supply),
                        status=200,
                        mimetype='text/plain'
                    )
                else:
                    response = flask_server.response_class(
                        response=f"Unsupported supply parameter: {parameter}",
                        status=400,
                        mimetype='text/plain'
                    )
            return response

    def make_dash_app(self, flask_server: Flask, route_url: str, debug: bool = False):
        dash_app = Dash(name=__name__,
                        server=flask_server,
                        assets_folder=settings.ASSETS_PATH,
                        url_base_pathname=route_url,
                        suppress_callback_exceptions=debug,
                        eager_loading=False,
                        assets_ignore='.*\\.BIN')  # ignore ip2loc database file

        # Initial State
        dash_app.title = settings.TITLE
        dash_app.layout = layout.BODY

        # TODO - not needed?
        # @dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        # def header(pathname):
        #     return components.header()

        @dash_app.callback(Output('cached-crawler-stats', 'children'), [Input('request-interval', 'n_intervals')])
        def update_cached_stats(n_intervals):
            payload = self.make_request()
            return json.dumps(payload)

        @dash_app.callback(Output('prev-states', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def state(n_intervals, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            states = data['prev_states']
            return components.previous_states(states=states)

        @dash_app.callback(Output('network-info-content', 'children'),
                           [Input('url', 'pathname'),
                            Input('minute-interval', 'n_intervals'),
                            Input('network-info-tabs', 'value')],
                           [State('cached-crawler-stats', 'children')])
        def network_info_tab_content(pathname, n, current_tab, latest_crawler_stats):
            if current_tab == 'node-details':
                return known_nodes(latest_crawler_stats=latest_crawler_stats)
            else:
                return events()

        def events():
            prior_periods = 30  # TODO more thought? (note: retention for the db is 5w - so anything longer is useless)
            events_data = self.influx_client.get_historical_events(days=prior_periods)
            events_table = components.events_table(network=self.network, events=events_data, days=prior_periods)
            return events_table

        def known_nodes(latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            node_tables = components.known_nodes(network=self.network, nodes_dict=data['node_details'])
            return node_tables

        @dash_app.callback(Output('active-stakers', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def active_stakers(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            data = data['activity']
            confirmed, pending, inactive = data['active'], data['pending'], data['inactive']
            total_stakers = confirmed + pending + inactive
            return html.Div([html.H4("Active Ursulas"), html.H5(f"{confirmed}/{total_stakers}", id='active-ursulas-value')])

        @dash_app.callback(Output('staker-breakdown', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def stakers_breakdown(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            return stakers_breakdown_pie_chart(data=data['activity'])

        @dash_app.callback(Output('top-stakers-graph', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def top_stakers(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            return top_stakers_chart(data=data['top_stakers'])

        @dash_app.callback(Output('current-period', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def current_period(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            return html.Div([html.H4("Current Period"), html.H5(data['current_period'], id='current-period-value')])

        @dash_app.callback(Output('blocktime-value', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def blocktime(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            block_epoch = data['blocktime']
            block_number = data['blocknumber']
            blocktime = f"{MayaDT(block_epoch).iso8601()} | {block_number}"
            return html.Div([html.H4("Blocktime"), html.H5(blocktime, id='blocktime')])

        @dash_app.callback(Output('time-remaining', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def time_remaining(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            slang = MayaDT.from_iso8601(data['next_period']).slang_time()
            return html.Div([html.H4("Next Period"), html.H5(slang)])

        @dash_app.callback(Output('domain', 'children'), [Input('url', 'pathname')])  # on page-load
        def domain(pathname):
            chain = self.staking_agent.blockchain.client.chain_name
            network_and_chain = f'{self.network.capitalize()} | {chain}'
            return html.Div([html.H4('Network'), html.H5(network_and_chain, id="domain-value")])

        @dash_app.callback(Output('registry', 'children'), [Input('url', 'pathname')])  # on page-load
        def registry(pathname):
            latest = InMemoryContractRegistry.from_latest_publication(network=self.network)
            return html.Div([html.H4('Registry'), html.H5(latest.id[:16], id="registry-value")])

        @dash_app.callback(Output('contracts', 'children'),
                           [Input('domain', 'children')])  # after domain obtained to prevent concurrent blockchain requests
        def contracts(domain):
            agents = (self.token_agent, self.staking_agent, self.policy_agent, self.adjudicator_agent)
            rows = [make_contract_row(self.network, agent) for agent in agents]
            _components = html.Div([html.H4('Contracts'), *rows], id='contract-names')
            return _components

        @dash_app.callback(Output('staked-tokens', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def staked_tokens(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            staked = NU.from_nunits(data['global_locked_tokens'])
            return html.Div([html.H4('Staked in Current Period'), html.H5(f"{staked}", id='staked-tokens-value')])

        # @dash_app.callback(Output('locked-stake-graph', 'children'),
        #                    [Input('daily-interval', 'n_intervals')],
        #                    [State('cached-crawler-stats', 'children')])
        # def stake_and_known_nodes_plot(n, latest_crawler_stats):
        #     prior_periods = 30
        #     data = self.verify_cached_stats(latest_crawler_stats)
        #     nodes_history = self.influx_client.get_historical_num_stakers_over_range(prior_periods)
        #     past_stakes = self.influx_client.get_historical_locked_tokens_over_range(prior_periods)
        #     future_stakes = data['future_locked_tokens']
        #     graph = future_locked_tokens_bar_chart(future_locked_tokens=future_stakes,
        #                                            past_locked_tokens=past_stakes,
        #                                            node_history=nodes_history)
        #     return graph

        @dash_app.callback(Output('nodes-geolocation-graph', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def nodes_geographical_locations(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            nodes_map = nodes_geolocation_map(nodes_dict=data['node_details'], ip2loc=self.ip2loc)
            return nodes_map

        # @dash_app.callback(Output('prev-work-orders-graph', 'children'), [Input('daily-interval', 'n_intervals')])
        # def historical_work_orders(n):
        #     TODO: only works for is_me characters
        #     prior_periods = 30
        #     num_work_orders_data = self.influx_client.get_historical_work_orders_over_range(prior_periods)
        #     return historical_work_orders_line_chart(data=num_work_orders_data)

        return dash_app
