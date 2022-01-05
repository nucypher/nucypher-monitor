import json
from pathlib import Path

import IP2Location
import requests
from dash import Dash
from dash import html
from dash.dependencies import Output, Input, State
from flask import Flask, request
from maya import MayaDT
from monitor import layout, components, settings
from monitor.charts import (
    stakers_breakdown_pie_chart,
    top_stakers_chart,
    nodes_geolocation_map
)
from monitor.components import make_contract_row
from monitor.crawler import Crawler
from monitor.supply import calculate_supply_information
from nucypher.blockchain.eth.agents import (
    StakingEscrowAgent,
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
    AdjudicatorAgent,
    WorkLockAgent
)
from nucypher.blockchain.eth.token import NU
from twisted.logger import Logger


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
                 crawler_port: int):

        self.log = Logger(self.__class__.__name__)

        # Crawler
        self.crawler_host = crawler_host
        self.crawler_port = crawler_port

        # Blockchain & Contracts
        self.network = network
        self.registry = registry

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)
        self.worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.registry)

        # Economics
        #self.economics = EconomicsFactory.get_economics(registry=self.registry)

        # Add informational endpoints
        # Supply
        self.add_supply_endpoint(flask_server=flask_server)

        # TODO: Staker

        # Dash
        self.dash_app = self.make_dash_app(flask_server=flask_server, route_url=route_url)

        # GeoLocation
        iplocation_file = Path(settings.ASSETS_PATH, 'geolocation', 'IP2LOCATION-LITE-DB5.BIN')
        self.ip2loc = IP2Location.IP2Location(filename=iplocation_file.resolve())

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
            current_total_supply_nunits = self.staking_agent.contract.functions.currentPeriodSupply().call()
            current_total_supply = NU.from_nunits(current_total_supply_nunits)
            parameter = request.args.get('q')
            if parameter is None or parameter == 'est_circulating_supply':
                # max supply needed
                max_supply_nunits = self.token_agent.contract.functions.totalSupply().call()
                max_supply = NU.from_nunits(max_supply_nunits)

                # worklock supply
                worklock_supply = NU.from_nunits(self.worklock_agent.lot_value)

                # no query - return all supply information
                supply_info = calculate_supply_information(max_supply=max_supply,
                                                           current_total_supply=current_total_supply,
                                                           worklock_supply=worklock_supply)
                if parameter is None:
                    # return all information
                    response = flask_server.response_class(
                        response=json.dumps(supply_info),
                        status=200,
                        mimetype='application/json'
                    )
                else:
                    # only return est. circulating supply
                    est_circulating_supply = supply_info['est_circulating_supply']
                    response = flask_server.response_class(
                        response=str(est_circulating_supply),
                        status=200,
                        mimetype='text/plain'
                    )
            else:
                # only current total supply requested
                if parameter == 'current_total_supply':
                    response = flask_server.response_class(
                        response=str(float(current_total_supply.to_tokens())),
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
                        assets_folder=settings.ASSETS_PATH.resolve(),
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
                            Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def network_info_content(pathname, n, latest_crawler_stats):
            return known_nodes(latest_crawler_stats=latest_crawler_stats)

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

        @dash_app.callback(Output('current-period', 'children'), [Input('url', 'pathname')])  # on page-load
        def current_period(pathname):
            halt_period = self.staking_agent.contract.functions.currentMintingPeriod().call()
            return html.Div([html.H4("Period of NU Inflation Halt"), html.H5(halt_period, id='current-period-value')])

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
            return html.Div([html.H4('Registry'), html.H5(self.registry.id[:16], id="registry-value")])

        @dash_app.callback(Output('contracts', 'children'),
                           [Input('domain', 'children')])  # after domain obtained to prevent concurrent blockchain requests
        def contracts(domain):
            agents = (self.token_agent, self.staking_agent, self.policy_agent, self.adjudicator_agent)
            rows = [make_contract_row(self.network, agent) for agent in agents]
            _components = html.Div([html.H4('Contracts'), *rows], id='contract-names')
            return _components

        @dash_app.callback(Output('staked-tokens', 'children'), [Input('url', 'pathname')])  # on page-load
        def staked_tokens(pathname):
            halt_period = self.staking_agent.contract.functions.currentMintingPeriod().call()
            total_staked = self.staking_agent.get_global_locked_tokens(at_period=halt_period)
            staked = round(NU.from_nunits(total_staked), 2)  # round to 2 decimals
            return html.Div([html.H4('Total Legacy Stakes'), html.H5(f"{staked}", id='staked-tokens-value')])

        @dash_app.callback(Output('staked-tokens-next-period', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def staked_tokens_next_period(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            staked = round(NU.from_nunits(data['global_locked_tokens']), 2)  # round to 2 decimals
            return html.Div([html.H4('Currently Staked for Next Period'), html.H5(f"{staked}", id='staked-tokens-next-period-value')])

        @dash_app.callback(Output('nodes-geolocation-graph', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def nodes_geographical_locations(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            nodes_map = nodes_geolocation_map(nodes_dict=data['node_details'], ip2loc=self.ip2loc)
            return nodes_map

        return dash_app
