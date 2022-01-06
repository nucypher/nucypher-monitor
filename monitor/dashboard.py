import json

from dash import Dash
from dash import html
from dash.dependencies import Output, Input
from flask import Flask, request
from maya import MayaDT
from monitor import layout, settings
from monitor.components import make_contract_row
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
                 network: str):

        self.log = Logger(self.__class__.__name__)

        # Blockchain & Contracts
        self.network = network
        self.registry = registry

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)
        self.worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.registry)

        # Add informational endpoints
        # Supply
        self.add_supply_endpoint(flask_server=flask_server)

        # Dash
        self.dash_app = self.make_dash_app(flask_server=flask_server, route_url=route_url)

    def add_supply_endpoint(self, flask_server: Flask):
        # base "now" on static inflation halt transaction time (https://etherscan.io/tx/0x23ef7eacd809399ed5135d5fe7dd9f6970c813f2704f884a12842479c213a87c)
        # probably don't need to be that specific since vesting is by months, but why not document it here
        halt_nu_datetime = MayaDT.from_iso8601('2021-12-31T07:44:37.0Z')

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
                                                           worklock_supply=worklock_supply,
                                                           now=halt_nu_datetime)
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

        @dash_app.callback(Output('current-period', 'children'), [Input('url', 'pathname')])  # on page-load
        def current_period(pathname):
            halt_period = self.staking_agent.contract.functions.currentMintingPeriod().call()
            return html.Div([html.H4("Period of Inflation Halt"), html.H5(halt_period, id='current-period-value')])

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
            return html.Div([html.H4('Total Legacy Stakes Size'), html.H5(f"{staked}", id='staked-tokens-value')])

        return dash_app
