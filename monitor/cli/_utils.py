from cryptography.hazmat.primitives.asymmetric import ec
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.server import TLSHostingPower
from umbral.keys import UmbralPrivateKey


def _get_registry(provider_uri, registry_filepath):
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    if registry_filepath:
        registry = LocalContractRegistry.from_latest_publication()
    else:
        registry = InMemoryContractRegistry.from_latest_publication()

    return registry


def _get_tls_hosting_power(host: str = None,
                           tls_certificate_filepath: str = None,
                           tls_private_key_filepath: str = None):
    # Pre-Signed
    if tls_certificate_filepath and tls_private_key_filepath:
        with open(tls_private_key_filepath, 'rb') as file:
            tls_private_key = UmbralPrivateKey.from_bytes(file.read())
        tls_hosting_keypair = HostingKeypair(curve=ec.SECP384R1,
                                             host=host,
                                             certificate_filepath=tls_certificate_filepath,
                                             private_key=tls_private_key)

    # Self-Sign
    else:
        tls_hosting_keypair = HostingKeypair(curve=ec.SECP384R1, host=host)

    tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=host)
    return tls_hosting_power
