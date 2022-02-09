import json

from dash import Dash
from dash import html
from dash.dependencies import Output, Input
from flask import Flask, request
from maya import MayaDT
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
from web3 import Web3

from monitor import layout, settings
from monitor.components import make_contract_row
from monitor.supply import calculate_supply_information


class Dashboard:
    # static value from when halt NU inflation occurred - `self.staking_agent.contract.functions.currentMintingPeriod().call()`
    HALT_PERIOD = 2713

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


        @flask_server.route('/supply_information', methods=["GET"])
        def supply_information():
            frozen_total_supply_nunits = self.staking_agent.contract.functions.currentPeriodSupply().call()
            frozen_total_supply = NU.from_nunits(frozen_total_supply_nunits)
            parameter = request.args.get('q')
            if parameter is None or parameter == 'est_circulating_supply':
                # the original max supply no longer applies because of Threshold merger
                max_supply = frozen_total_supply

                # worklock supply
                worklock_supply = NU.from_nunits(self.worklock_agent.lot_value)

                # no query - return all supply information
                supply_info = calculate_supply_information(max_supply=max_supply,
                                                           current_total_supply=frozen_total_supply,
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
                        response=str(float(frozen_total_supply.to_tokens())),
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
            return html.Div([html.H4("Period of Inflation Halt"), html.H5(self.HALT_PERIOD, id='current-period-value')])

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
            agents = (self.token_agent, self.staking_agent, self.policy_agent, self.adjudicator_agent, self.worklock_agent)
            rows = [make_contract_row(self.network, agent) for agent in agents]
            _components = html.Div([html.H4('Contracts'), *rows], id='contract-names')
            return _components

        @dash_app.callback(Output('staked-tokens', 'children'), [Input('url', 'pathname')])  # on page-load
        def staking_escrow_nu(pathname):
            max_supply = NU.from_nunits(self.token_agent.contract.functions.totalSupply().call())
            frozen_total_supply = NU.from_nunits(self.staking_agent.contract.functions.currentPeriodSupply().call())
            halted_rewards = max_supply - frozen_total_supply

            nu_in_staking_escrow = NU.from_nunits(self.token_agent.get_balance(self.staking_agent.contract_address)) - halted_rewards
            staked = round(nu_in_staking_escrow, 2)  # round to 2 decimals
            return html.Div([html.H4('Legacy Stakes Size'), html.H5(f"{staked}", id='staked-tokens-value')])

        @dash_app.callback(Output('worklock-status', 'children'), [Input('url', 'pathname')])  # on page-load
        def staking_escrow_nu(pathname):
            eth_balance_wei = self.worklock_agent.blockchain.client.get_balance(self.worklock_agent.contract_address)
            eth_balance = Web3.fromWei(eth_balance_wei, "ether")
            return html.Div([html.H4('ETH in WorkLock'), html.H5(f"{round(eth_balance, 2)} ETH", id='staked-tokens-value')])

        return dash_app
