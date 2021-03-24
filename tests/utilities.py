import functools
import os
import random
from ipaddress import IPv4Address
from unittest.mock import MagicMock

import maya
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from eth_utils.address import to_checksum_address
from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import RemoteUrsulaStatus, ArchivedFleetState
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.network.nodes import Teacher
from nucypher.characters.lawful import Ursula

COLORS = ['red', 'green', 'yellow', 'blue', 'black', 'brown', 'purple']


def create_eth_address():
    random_address = to_checksum_address(os.urandom(20))
    return random_address


def create_random_mock_node(generate_certificate: bool = False):
    host = str(IPv4Address(random.getrandbits(32)))
    checksum_address = create_eth_address()

    # some percentage of the time produce a NULL_ADDRESS
    if random.random() > 0.9:
        worker_address = NULL_ADDRESS
    else:
        worker_address = create_eth_address()
    timestamp = maya.now().subtract(hours=(random.randrange(0, 10)))

    work_orders = random.randrange(0, 5)

    return create_specific_mock_node(generate_certificate=generate_certificate,
                                     checksum_address=checksum_address,
                                     host=host,
                                     worker_address=worker_address,
                                     timestamp=timestamp,
                                     num_work_orders=work_orders)


def create_random_mock_node_status():
    host = str(IPv4Address(random.getrandbits(32)))
    timestamp = maya.now().subtract(hours=(random.randrange(0, 10)))
    last_learned_from = maya.now()
    return RemoteUrsulaStatus(nickname=Nickname.from_seed(random.randint(0, 2**32), length=2),
                              staker_address=create_eth_address(),
                              worker_address=create_eth_address(),
                              rest_url=f"{host}:9151",
                              timestamp=timestamp,
                              last_learned_from=last_learned_from,
                              recorded_fleet_state=None,
                              verified=True,
                              )


def create_node_certificate(host: str, checksum_address: str):
    tls_hosting_keypair = HostingKeypair(host=host,
                                         checksum_address=checksum_address)

    return tls_hosting_keypair.certificate


def create_specific_mock_node(generate_certificate: bool = False,
                              checksum_address: str = '0x123456789',
                              host: str = '127.0.0.1',
                              nickname: Nickname = Nickname.from_seed(seed=None),
                              worker_address: str = '0x987654321',
                              timestamp: maya.MayaDT = maya.now().subtract(days=4),
                              has_fleet_state: bool = False,
                              num_work_orders=2):
    if generate_certificate:
        # Generate certificate
        certificate = create_node_certificate(host=host, checksum_address=checksum_address)
    else:
        certificate = MagicMock()

    if has_fleet_state:
        recorded_fleet_state = dict(checksum=fleet_state_checksum,
                                    nickname=fleet_state_nickname,
                                    timestamp=maya.now(),
                                    population=1)
    else:
        recorded_fleet_state = None

    node = MagicMock(certificate=certificate, checksum_address=checksum_address, nickname=nickname,
                     worker_address=worker_address, timestamp=timestamp,
                     _recorded_fleet_state=recorded_fleet_state,
                     is_me=False)

    node.rest_url.return_value = f"{host}:9151"  # TODO: Needs cleanup

    work_orders_list = MagicMock(spec=list)
    work_orders_list.__len__.return_value = num_work_orders
    node.work_orders.return_value = work_orders_list

    return node


def create_random_mock_state(seed=None):
    timestamp = maya.now().subtract(minutes=(random.randrange(0, 59)))
    return create_specific_mock_state(nickname=Nickname.from_seed(seed=seed), timestamp=timestamp)


def create_specific_mock_state(nickname: Nickname = Nickname.from_seed(seed=None),
                               timestamp: maya.MayaDT = maya.now()):
    # 0 out microseconds since it causes issues converting from rfc2822 and rfc3339
    timestamp = timestamp.subtract(microseconds=timestamp.datetime().microsecond)
    state = ArchivedFleetState(nickname=nickname,
                               timestamp=timestamp,
                               checksum="0x12345678",
                               population=42)
    return state


class MockContractAgency:
    def __init__(self, staking_agent=MagicMock(spec=StakingEscrowAgent)):
        self.staking_agent = staking_agent

    def get_agent(self, agent_class, registry: BaseContractRegistry, provider_uri: str = None):
        if agent_class == StakingEscrowAgent:
            return self.staking_agent
        else:
            return MagicMock(spec=agent_class)
