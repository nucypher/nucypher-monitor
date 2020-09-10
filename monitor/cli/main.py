import os

import click
from flask import Flask
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.config import group_general_config
from nucypher.cli.painting.help import echo_version
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.network.middleware import RestMiddleware
from twisted.internet import reactor
from nucypher.characters.lawful import Ursula


from monitor.cli._utils import _get_registry, _get_deployer
from monitor.crawler import Crawler
from monitor.dashboard import Dashboard

CRAWLER = "Crawler"
DASHBOARD = "Dashboard"

MONITOR_BANNER = r"""
 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= {} =========
"""


@click.group()
@click.option('--nucypher-version', help="Echo the nucypher version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
def monitor():
    pass


@monitor.command()
@group_general_config
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.Choice(choices=NetworksInventory.NETWORKS), required=True)
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, required=True)
@click.option('--influx-host', help="InfluxDB host URI", type=click.STRING, default='0.0.0.0')
@click.option('--influx-port', help="InfluxDB network port", type=NETWORK_PORT, default=8086)
@click.option('--http-port', help="Crawler HTTP port for JSON endpoint", type=NETWORK_PORT, default=Crawler.DEFAULT_CRAWLER_HTTP_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the crawler", is_flag=True)
@click.option('--eager', help="Start learning and scraping before starting up other services", is_flag=True, default=False)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
def crawl(general_config,
          teacher_uri,
          registry_filepath,
          min_stake,
          network,
          learn_on_launch,
          provider_uri,
          influx_host,
          influx_port,
          http_port,
          dry_run,
          eager,
          poa,
          ):
    """
    Gather NuCypher network information.
    """

    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format(CRAWLER))

    # Setup
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri, poa=poa)
    registry = _get_registry(registry_filepath, network)
    middleware = RestMiddleware()

    # Teacher Ursula
    sage_node = None
    if teacher_uri:
        sage_node = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                            min_stake=0,  # TODO: Where to get this?
                                            federated_only=False,  # always False
                                            network_middleware=middleware,
                                            registry=registry)

    crawler = Crawler(domains={network} if network else None,
                      network_middleware=middleware,
                      known_nodes=[sage_node] if teacher_uri else None,
                      registry=registry,
                      start_learning_now=eager,
                      learn_on_same_thread=learn_on_launch,
                      influx_host=influx_host,
                      influx_port=influx_port)

    emitter.message(f"Network: {network.capitalize()}", color='blue')
    emitter.message(f"InfluxDB: {influx_host}:{influx_port}", color='blue')
    emitter.message(f"Provider: {provider_uri}", color='blue')
    emitter.message(f"Refresh Rate: {crawler._refresh_rate}s", color='blue')
    message = f"Running Nucypher Crawler JSON endpoint at http://localhost:{http_port}/stats"
    emitter.message(message, color='green', bold=True)
    if not dry_run:
        crawler.start(eager=eager)
        reactor.run()


@monitor.command()
@group_general_config
@click.option('--host', help="The host to run monitor dashboard on", type=click.STRING, default='127.0.0.1')
@click.option('--http-port', help="The network port to run monitor dashboard on", type=NETWORK_PORT, default=12500)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath")
@click.option('--tls-key-filepath', help="TLS private key filepath")
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, required=True)
@click.option('--network', help="Network Domain Name", type=click.Choice(choices=NetworksInventory.NETWORKS), required=True)
@click.option('--influx-host', help="InfluxDB host URI", type=click.STRING)
@click.option('--influx-port', help="InfluxDB network port", type=NETWORK_PORT, default=8086)
@click.option('--crawler-host', help="Crawler's HTTP host address", type=click.STRING, default='localhost')
@click.option('--crawler-port', help="Crawler's HTTP port serving JSON", type=NETWORK_PORT, default=Crawler.DEFAULT_CRAWLER_HTTP_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the dashboard", is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
def dashboard(general_config,
              host,
              http_port,
              registry_filepath,
              certificate_filepath,
              tls_key_filepath,
              provider_uri,
              network,
              influx_host,
              influx_port,
              crawler_host,
              crawler_port,
              dry_run,
              poa,
              ):
    """
    Run UI dashboard of NuCypher network.
    """

    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format(DASHBOARD))

    # Setup
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri, poa=poa)
    registry = _get_registry(registry_filepath, network)

    #
    # WSGI Service
    #

    if not influx_host:
        influx_host = crawler_host

    rest_app = Flask("monitor-dashboard")
    if general_config.debug:
        os.environ['FLASK_ENV'] = 'development'

    Dashboard(flask_server=rest_app,
              route_url='/',
              registry=registry,
              network=network,
              influx_host=influx_host,
              influx_port=influx_port,
              crawler_host=crawler_host,
              crawler_port=crawler_port)

    #
    # Server
    #

    deployer = _get_deployer(rest_app=rest_app,
                             host=host,
                             port=http_port,
                             certificate_filepath=certificate_filepath,
                             tls_key_filepath=tls_key_filepath)

    # Pre-Launch Info
    emitter.message(f"Network: {network.capitalize()}", color='blue')
    emitter.message(f"Crawler: {crawler_host}:{crawler_port}", color='blue')
    emitter.message(f"InfluxDB: {influx_host}:{influx_port}", color='blue')
    emitter.message(f"Provider: {provider_uri}", color='blue')
    if not dry_run:
        emitter.message(f"Running Monitor Dashboard - https://{host}:{http_port}", color='green', bold=True)
        try:
            deployer.run()  # <--- Blocking
        finally:
            click.secho("Shutting Down")
