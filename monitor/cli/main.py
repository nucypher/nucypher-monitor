import os

import click
from flask import Flask
from twisted.internet import reactor

from monitor.cli._utils import _get_registry, _get_tls_hosting_power
from monitor.crawler import Crawler
from monitor.dashboard import Dashboard
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli import actions
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import echo_version
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.network.middleware import RestMiddleware

CRAWLER = "Crawler"
DASHBOARD = "Dashboard"

MONITOR_BANNER = r"""
 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= {} =========
"""


# TODO: Help!!!
DEFAULT_PROVIDER = f'file://{os.path.expanduser("~")}/.ethereum/goerli/geth.ipc'
DEFAULT_TEACHER = 'https://discover.nucypher.network:9151'


@click.group()
@click.option('--nucypher-version', help="Echo the nucypher version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
def monitor():
    pass


@monitor.command()
@group_general_config
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING, default=DEFAULT_TEACHER)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.Choice(choices=NetworksInventory.networks), required=True)
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default=DEFAULT_PROVIDER)
@click.option('--influx-host', help="InfluxDB host URI", type=click.STRING, default='0.0.0.0')
@click.option('--influx-port', help="InfluxDB network port", type=NETWORK_PORT, default=8086)
@click.option('--http-port', help="Crawler HTTP port for JSON endpoint", type=NETWORK_PORT, default=Crawler.DEFAULT_CRAWLER_HTTP_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the crawler", is_flag=True)
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
          dry_run):
    """
    Gather NuCypher network information.
    """

    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format(CRAWLER))

    registry = _get_registry(provider_uri, registry_filepath, network)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else None
    teacher_nodes = actions.load_seednodes(emitter,
                                           teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=False,
                                           network_domains={network} if network else None,
                                           network_middleware=RestMiddleware())

    crawler = Crawler(domains={network} if network else None,
                      network_middleware=RestMiddleware(),
                      known_nodes=teacher_nodes,
                      registry=registry,
                      start_learning_now=False,
                      learn_on_same_thread=learn_on_launch,
                      influx_host=influx_host,
                      influx_port=influx_port)
    if not dry_run:
        message = f"Running Nucypher Crawler JSON endpoint at http://localhost:{http_port}/stats"
        emitter.message(message, color='blue', bold=True)
        crawler.start()
        reactor.run()


@monitor.command()
@group_general_config
@click.option('--host', help="The host to run monitor dashboard on", type=click.STRING, default='127.0.0.1')
@click.option('--http-port', help="The network port to run monitor dashboard on", type=NETWORK_PORT, default=12500)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath")
@click.option('--tls-key-filepath', help="TLS private key filepath")
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default=DEFAULT_PROVIDER)
@click.option('--network', help="Network Domain Name", type=click.Choice(choices=NetworksInventory.networks), required=True)
@click.option('--crawler-host', help="Crawler's host address", type=click.STRING, default='localhost')
@click.option('--crawler-port', help="Crawler's HTTP port serving JSON", type=NETWORK_PORT, default=Crawler.DEFAULT_CRAWLER_HTTP_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the dashboard", is_flag=True)
def dashboard(general_config,
              host,
              http_port,
              registry_filepath,
              certificate_filepath,
              tls_key_filepath,
              provider_uri,
              network,
              crawler_host,
              crawler_port,
              dry_run,
              ):
    """
    Run UI dashboard of NuCypher network.
    """

    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format(DASHBOARD))

    # Setup
    registry = _get_registry(provider_uri, registry_filepath, network)

    #
    # WSGI Service
    #

    rest_app = Flask("monitor-dashboard")
    Dashboard(flask_server=rest_app,
              route_url='/',
              registry=registry,
              network=network,
              crawler_host=crawler_host,
              crawler_port=crawler_port)

    #
    # Server
    #

    tls_hosting_power = _get_tls_hosting_power(host=host,
                                               tls_certificate_filepath=certificate_filepath,
                                               tls_private_key_filepath=tls_key_filepath)
    deployer = tls_hosting_power.get_deployer(rest_app=rest_app, port=http_port)

    if not dry_run:
        emitter.message(f"Running Monitor Dashboard - https://{host}:{http_port}", color='blue', bold=True)
        deployer.run()
