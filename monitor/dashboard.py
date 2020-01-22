import json
from datetime import datetime, timedelta

import dash_html_components as html
import maya
import requests
from dash import Dash
from dash.dependencies import Output, Input, State
from flask import Flask
from maya import MayaDT
from twisted.logger import Logger

from monitor import layout, components, settings
from monitor.charts import (
    future_locked_tokens_bar_chart,
    stakers_breakdown_pie_chart,
    top_stakers_chart
)
from monitor.crawler import Crawler
from monitor.db import CrawlerInfluxClient
from nucypher.blockchain.eth.agents import (
    StakingEscrowAgent,
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
    AdjudicatorAgent
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU


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

        # Dash
        self.dash_app = self.make_dash_app(flask_server=flask_server, route_url=route_url)

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

    def make_dash_app(self, flask_server: Flask, route_url: str, debug: bool = False):
        dash_app = Dash(name=__name__,
                        server=flask_server,
                        assets_folder=settings.ASSETS_PATH,
                        url_base_pathname=route_url,
                        suppress_callback_exceptions=debug,
                        eager_loading=False)

        # Initial State
        dash_app.title = settings.TITLE
        dash_app.layout = layout.BODY

        @dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return components.header()

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

        @dash_app.callback(Output('known-nodes', 'children'),
                           [Input('url', 'pathname'), Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def known_nodes(pathname, n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            table = components.known_nodes(nodes_dict=data['node_details'])
            return table

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
                           [Input('minute-interval', 'n_intervals')])
        def blocktime(n):
            # TODO: Consider doing this here or not - It exposes a web3 call on a public interface
            block = self.staking_agent.blockchain.client.w3.eth.getBlock('latest')
            blocktime = block.timestamp  # epoch
            blocktime = f"{MayaDT(blocktime).iso8601()} | {block.number}"
            return html.Div([html.H4("Blocktime"), html.H5(blocktime, id='blocktime')])

        @dash_app.callback(Output('time-remaining', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def time_remaining(n, latest_crawler_stats):
            # data = self.verify_cached_stats(latest_crawler_stats)  # TODO: use period utils
            tomorrow = datetime.now() + timedelta(1)
            midnight = datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day, hour=0, minute=0, second=0)
            delta = (midnight - datetime.now())
            slang = (maya.now() + delta).slang_time()
            data = {'next_period': slang}
            return html.Div([html.H4("Next Period"), html.H5(data['next_period'])])

        @dash_app.callback(Output('domains', 'children'), [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = f'{self.network.capitalize()} | {self.staking_agent.blockchain.client.chain_name}'
            return html.Div([html.H4('Network'), html.H5(domains, id="domain-value")])

        @dash_app.callback(Output('registry', 'children'), [Input('url', 'pathname')])  # on page-load
        def registry(pathname):
            latest = InMemoryContractRegistry.from_latest_publication(network=self.network)
            return html.Div([html.H4('Registry'), html.H5(latest.id[:16], id="registry-value")])

        @dash_app.callback(Output('contracts', 'children'), [Input('url', 'pathname')])  # on page-load
        def contracts(pathname):
            base_url = "https://goerli.etherscan.io/address/{}"
            reward_supply = NU.from_nunits(self.token_agent.get_balance(self.staking_agent.contract_address))
            components = html.Div([html.H4('Contracts'),

                                   html.Tr([
                                       html.A(f'{self.token_agent.contract_name} {self.token_agent.contract_address}',
                                              id="token-contract-address",
                                              href=base_url.format(self.token_agent.contract_address)),
                                       html.Span(f'{self.token_agent.contract.version}')
                                   ]),

                                   html.Tr([
                                       html.A(
                                           f'{self.staking_agent.contract_name} {self.staking_agent.contract_address}',
                                           id="staking-contract-address",
                                           href=base_url.format(self.staking_agent.contract_address)),
                                       html.Span(f'{self.staking_agent.contract.version}'),
                                       html.Span(f'{reward_supply}')
                                   ]),

                                   html.Tr([
                                       html.A(
                                           f'{self.policy_agent.contract_name} {self.policy_agent.contract_address}',
                                           id="policy-contract-address",
                                           href=base_url.format(self.policy_agent.contract_address)),
                                       html.Span(f'{self.policy_agent.contract.version}'),
                                       html.Span(f'{NU.from_nunits(self.token_agent.get_balance(self.policy_agent.contract_address))}')
                                   ]),

                                   html.Tr([
                                       html.A(f'{self.adjudicator_agent.contract_name} {self.adjudicator_agent.contract_address}',
                                              id="adjudicator-contract-address",
                                              href=base_url.format(self.adjudicator_agent.contract_address)),
                                       html.Span(f'{self.adjudicator_agent.contract.version}'),
                                       html.Span(f'{NU.from_nunits(self.token_agent.get_balance(self.adjudicator_agent.contract_address))}')
                                   ])

                                   ], id='contract-names')
            return components

        @dash_app.callback(Output('staked-tokens', 'children'),
                           [Input('minute-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def staked_tokens(n, latest_crawler_stats):
            data = self.verify_cached_stats(latest_crawler_stats)
            staked = NU.from_nunits(data['global_locked_tokens'])
            return html.Div([html.H4('Staked Tokens'), html.H5(f"{staked}", id='staked-tokens-value')])

        @dash_app.callback(Output('locked-stake-graph', 'children'),
                           [Input('daily-interval', 'n_intervals')],
                           [State('cached-crawler-stats', 'children')])
        def stake_and_known_nodes_plot(n, latest_crawler_stats):
            prior_periods = 30
            data = self.verify_cached_stats(latest_crawler_stats)
            nodes_history = self.influx_client.get_historical_num_stakers_over_range(prior_periods)
            past_stakes = self.influx_client.get_historical_locked_tokens_over_range(prior_periods)
            future_stakes = data['future_locked_tokens']
            graph = future_locked_tokens_bar_chart(future_locked_tokens=future_stakes,
                                                   past_locked_tokens=past_stakes,
                                                   node_history=nodes_history)
            return graph

        # @dash_app.callback(Output('prev-work-orders-graph', 'children'), [Input('daily-interval', 'n_intervals')])
        # def historical_work_orders(n):
        #     TODO: only works for is_me characters
        #     prior_periods = 30
        #     num_work_orders_data = self.influx_client.get_historical_work_orders_over_range(prior_periods)
        #     return historical_work_orders_line_chart(data=num_work_orders_data)

        return dash_app
