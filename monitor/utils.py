import click
import maya
from enum import Enum
from nucypher.blockchain.eth.networks import NetworksInventory
from twisted.internet import defer
from twisted.internet.task import LoopingCall


def collector(label: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            start = maya.now()
            result = func(*args, **kwargs)
            end = maya.now()
            delta = end - start
            duration = f"{delta.total_seconds() or delta.microseconds}s"
            click.secho(f"✓ ... {label} [{duration}]", color='blue')
            return result
        return wrapped
    return decorator


class EtherscanURLType(Enum):
    ADDRESS = 1
    TRANSACTION = 2


def get_etherscan_url(network: str, url_type: EtherscanURLType, address_or_tx_hash: str) -> str:
    if not network:
        raise ValueError("Network must be specified")
    if not url_type:
        raise ValueError("URL type must be specified")
    if not address_or_tx_hash:
        raise ValueError("Address/Tx Hash must be specified")

    # url chain prefix
    chain_id = NetworksInventory.get_ethereum_chain_id(network)
    if chain_id == 1:
        url_chain_prefix = ''  # mainnet = no url prefix
    elif chain_id == 4:
        url_chain_prefix = 'rinkeby.'
    elif chain_id == 5:
        url_chain_prefix = 'goerli.'
    else:
        raise ValueError(f"Unrecognized network {network} and chain id {chain_id}")

    if url_type == EtherscanURLType.ADDRESS:
        return f"https://{url_chain_prefix}etherscan.io/address/{address_or_tx_hash}"
    elif url_type == EtherscanURLType.TRANSACTION:
        # transaction
        return f"https://{url_chain_prefix}etherscan.io/tx/{address_or_tx_hash}"


class DelayedLoopingCall(LoopingCall):
    def __init__(self, start_delay: int = 0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_delay = start_delay

    def start(self, interval, now=True):
        assert not self.running, ("Tried to start an already running "
                                  "LoopingCall.")
        if interval < 0:
            raise ValueError("interval must be >= 0")
        self.running = True
        # Loop might fail to start and then self._deferred will be cleared.
        # This why the local C{deferred} variable is used.
        deferred = self._deferred = defer.Deferred()
        self.starttime = self.clock.seconds() + self.start_delay
        self.interval = interval
        self._runAtStart = now
        if now:
            self()
        else:
            self._scheduleFrom(self.starttime)
        return deferred