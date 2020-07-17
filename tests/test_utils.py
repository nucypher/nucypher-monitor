from unittest import mock

import pytest
from nucypher.blockchain.eth.networks import NetworksInventory

from monitor.utils import get_etherscan_url, EtherscanURLType

ADDRESS_OR_TX_HASH = "0xdeadbeef"


def test_etherscan_url_invalid_inputs():
    # no network
    with pytest.raises(ValueError):
        get_etherscan_url(network=None, url_type=EtherscanURLType.ADDRESS, address_or_tx_hash=ADDRESS_OR_TX_HASH)

    with pytest.raises(ValueError):
        get_etherscan_url(network='', url_type=EtherscanURLType.ADDRESS, address_or_tx_hash=ADDRESS_OR_TX_HASH)

    # unknown network
    with pytest.raises(ValueError):
        get_etherscan_url(network='pandora', url_type=EtherscanURLType.TRANSACTION, address_or_tx_hash=ADDRESS_OR_TX_HASH)

    # None url type
    with pytest.raises(ValueError):
        get_etherscan_url(network=NetworksInventory.IBEX, url_type=None, address_or_tx_hash=ADDRESS_OR_TX_HASH)

    # no hash
    with pytest.raises(ValueError):
        get_etherscan_url(network=NetworksInventory.IBEX,
                          url_type=EtherscanURLType.TRANSACTION,
                          address_or_tx_hash=None)

    with pytest.raises(ValueError):
        get_etherscan_url(network=NetworksInventory.IBEX,
                          url_type=EtherscanURLType.TRANSACTION,
                          address_or_tx_hash='')


def test_etherscan_url_ibex():
    # address
    url = get_etherscan_url(network=NetworksInventory.IBEX,
                            url_type=EtherscanURLType.ADDRESS,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://rinkeby.etherscan.io/address/{ADDRESS_OR_TX_HASH}"

    # transaction
    url = get_etherscan_url(network=NetworksInventory.IBEX,
                            url_type=EtherscanURLType.TRANSACTION,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://rinkeby.etherscan.io/tx/{ADDRESS_OR_TX_HASH}"


def test_etherscan_url_mainnet():
    # address
    url = get_etherscan_url(network=NetworksInventory.MAINNET,
                            url_type=EtherscanURLType.ADDRESS,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://etherscan.io/address/{ADDRESS_OR_TX_HASH}"

    # transaction
    url = get_etherscan_url(network=NetworksInventory.MAINNET,
                            url_type=EtherscanURLType.TRANSACTION,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://etherscan.io/tx/{ADDRESS_OR_TX_HASH}"


@mock.patch('nucypher.blockchain.eth.networks.NetworksInventory.get_ethereum_chain_id', return_value=5)
def test_etherscan_url_goerli(chain_id_func):
    # address
    url = get_etherscan_url(network='rando-goerli',  # name irrelevant because of patch
                            url_type=EtherscanURLType.ADDRESS,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://goerli.etherscan.io/address/{ADDRESS_OR_TX_HASH}"

    # transaction
    url = get_etherscan_url(network='rando-goerli',  # name irrelevant because of patch
                            url_type=EtherscanURLType.TRANSACTION,
                            address_or_tx_hash=ADDRESS_OR_TX_HASH)
    assert url == f"https://goerli.etherscan.io/tx/{ADDRESS_OR_TX_HASH}"
