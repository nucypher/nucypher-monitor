import click
from flask import Flask
from nucypher.cli import actions
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import echo_version
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.network.middleware import RestMiddleware
from twisted.internet import reactor

from monitor.cli._utils import _get_registry, _get_tls_hosting_power
from monitor.crawler import Crawler
from monitor.dashboard import Dashboard
import os


MONITOR_BANNER = r"""
 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= {} =========
"""


DEFAULT_PROVIDER = f'file://{os.path.expanduser("~")}/.ethereum/goerli/geth.ipc'
DEFAULT_TEACHER = 'https://discover.nucypher.network:9151'


@click.group()
@click.option('--nucypher-version', help="Echo the nucypher version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
def monitor():
    pass


@monitor.command()
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING, default=DEFAULT_TEACHER)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING, default='goerli')
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default=DEFAULT_PROVIDER)
@nucypher_click_config
def crawl(click_config,
          teacher_uri,
          registry_filepath,
          min_stake,
          network,
          learn_on_launch,
          provider_uri,
          ):
    """
    Gather NuCypher network information.
    """

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format("Crawler"))

    registry = _get_registry(provider_uri, registry_filepath)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else None
    teacher_nodes = actions.load_seednodes(emitter,
                                           teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=False,
                                           network_domains={network} if network else None,
                                           network_middleware=click_config.middleware)

    # Configure Storage
    crawler = Crawler(domains={network} if network else None,
                      network_middleware=RestMiddleware(),
                      known_nodes=teacher_nodes,
                      registry=registry,
                      federated_only=False,
                      start_learning_now=True,
                      learn_on_same_thread=learn_on_launch,
                      )

    crawler.start()
    reactor.run()


@monitor.command()
@click.option('--host', help="The host to run monitor dashboard on", type=click.STRING, default='127.0.0.1')
@click.option('--http-port', help="The network port to run monitor dashboard on", type=NETWORK_PORT, default=12500)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath")
@click.option('--tls-key-filepath', help="TLS private key filepath")
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default=DEFAULT_PROVIDER)
@click.option('--network', help="Network Domain Name", type=click.STRING, default='goerli')
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def dashboard(click_config,
              host,
              http_port,
              registry_filepath,
              certificate_filepath,
              tls_key_filepath,
              provider_uri,
              network,
              dry_run,
              ):
    """
    Run UI dashboard of NuCypher network.
    """

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(MONITOR_BANNER.format("Dashboard"))

    registry = _get_registry(provider_uri, registry_filepath)

    #
    # WSGI Service
    #
    rest_app = Flask("monitor-dashboard")
    Dashboard(flask_server=rest_app, route_url='/', registry=registry)

    #
    # Server
    #
    tls_hosting_power = _get_tls_hosting_power(host=host,
                                               tls_certificate_filepath=certificate_filepath,
                                               tls_private_key_filepath=tls_key_filepath)
    emitter.message(f"Running Monitor Dashboard - https://{host}:{http_port}")
    deployer = tls_hosting_power.get_deployer(rest_app=rest_app, port=http_port)
    if not dry_run:
        deployer.run()
