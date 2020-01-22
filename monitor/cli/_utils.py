from cryptography.hazmat.primitives.asymmetric import ec

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.server import TLSHostingPower


def _get_registry(provider_uri, registry_filepath, network):
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    if registry_filepath:
        registry = LocalContractRegistry.from_latest_publication(network=network)
    else:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)

    return registry


def _get_self_signed_hosting_power(host: str):
    tls_hosting_keypair = HostingKeypair(curve=ec.SECP384R1, host=host)
    tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=host)
    return tls_hosting_power
