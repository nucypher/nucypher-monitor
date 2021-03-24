from cryptography.hazmat.primitives.asymmetric import ec
from hendrix.deploy.tls import HendrixDeployTLS

from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.network.server import TLSHostingPower


def _get_registry(registry_filepath, network):

    if registry_filepath:
        registry = LocalContractRegistry.from_latest_publication(network=network)
    else:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)

    return registry


def _get_self_signed_hosting_power(host: str):
    tls_hosting_keypair = HostingKeypair(host=host, generate_certificate=True)
    tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=host)
    return tls_hosting_power


def _get_deployer(rest_app, host: str, port: int, tls_key_filepath: str = None, certificate_filepath: str = None):
    if tls_key_filepath and certificate_filepath:
        deployer = HendrixDeployTLS("start",
                                    key=tls_key_filepath,
                                    cert=certificate_filepath,
                                    options={"wsgi": rest_app, "https_port": port})
    else:
        tls_hosting_power = _get_self_signed_hosting_power(host=host)
        deployer = tls_hosting_power.get_deployer(rest_app=rest_app, port=port)

    return deployer
