import os
import random
import string
from ipaddress import IPv4Address
from unittest.mock import MagicMock

import maya
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from eth_utils.address import to_checksum_address
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.keystore.keypairs import HostingKeypair

COLORS = ['red', 'green', 'yellow', 'blue', 'black', 'brown', 'purple']


def create_eth_address():
    random_address = to_checksum_address(os.urandom(20))
    return random_address


def create_random_mock_node(generate_certificate: bool = False):
    host = str(IPv4Address(random.getrandbits(32)))
    nickname = ''.join(random.choice(string.ascii_letters) for i in range(25))
    checksum_address = create_eth_address()

    # some percentage of the time produce a NULL_ADDRESS
    if random.random() > 0.9:
        worker_address = BlockchainInterface.NULL_ADDRESS
    else:
        worker_address = create_eth_address()
    timestamp = maya.now().subtract(hours=(random.randrange(0, 10)))
    last_seen = maya.now()

    work_orders = random.randrange(0, 5)

    return create_specific_mock_node(generate_certificate=generate_certificate,
                                     checksum_address=checksum_address,
                                     host=host,
                                     nickname=nickname,
                                     worker_address=worker_address,
                                     timestamp=timestamp,
                                     last_seen=last_seen,
                                     num_work_orders=work_orders)


def create_node_certificate(host: str, checksum_address: str):
    tls_hosting_keypair = HostingKeypair(host=host,
                                         checksum_address=checksum_address)

    return tls_hosting_keypair.certificate


def create_specific_mock_node(generate_certificate: bool = False,
                              checksum_address: str = '0x123456789',
                              host: str = '127.0.0.1',
                              nickname: str = 'Blue Knight Teal Club',
                              worker_address: str = '0x987654321',
                              timestamp: maya.MayaDT = maya.now().subtract(days=4),
                              last_seen: maya.MayaDT = maya.now(),
                              fleet_state_nickname_metadata=UNKNOWN_FLEET_STATE,
                              num_work_orders=2):
    if generate_certificate:
        # Generate certificate
        certificate = create_node_certificate(host=host, checksum_address=checksum_address)
    else:
        certificate = MagicMock()

    node = MagicMock(certificate=certificate, checksum_address=checksum_address, nickname=nickname,
                     worker_address=worker_address, timestamp=timestamp, last_seen=last_seen,
                     fleet_state_nickname_metadata=fleet_state_nickname_metadata)

    node.rest_url.return_value = f"{host}:9151"  # TODO: Needs cleanup

    work_orders_list = MagicMock(spec=list)
    work_orders_list.__len__.return_value = num_work_orders
    node.work_orders.return_value = work_orders_list

    return node


def create_random_mock_state():
    nickname = ''.join(random.choice(string.ascii_letters) for i in range(25))
    updated = maya.now().subtract(minutes=(random.randrange(0, 59)))
    symbol = random.choice(string.punctuation)
    color_hex = f"#{''.join(random.choice(string.hexdigits) for i in range(6))}"
    color = random.choice(COLORS)

    return create_specific_mock_state(nickname=nickname, symbol=symbol, color_hex=color_hex,
                                      color=color, updated=updated)


def create_specific_mock_state(nickname: str = 'Blue Knight Teal Club',
                               symbol: str = '♣',
                               color_hex: str = '#1E65F3',
                               color: str = 'blue',
                               updated: maya.MayaDT = maya.now()):
    metadata = [(dict(hex=color_hex, color=color), symbol)]
    state = MagicMock(nickname=nickname, metadata=metadata, updated=updated)
    return state


class MockContractAgency:
    def __init__(self, staking_agent=MagicMock(spec=StakingEscrowAgent)):
        self.staking_agent = staking_agent

    def get_agent(self, agent_class, registry: BaseContractRegistry, provider_uri: str = None):
        if agent_class == StakingEscrowAgent:
            return self.staking_agent
        else:
            return MagicMock(spec=agent_class)
