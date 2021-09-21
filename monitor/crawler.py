import os
import random
import sqlite3
from collections import defaultdict
from typing import List, Dict

import click
import maya
from eth_typing import ChecksumAddress
from flask import Flask, jsonify
from hendrix.deploy.base import HendrixDeploy
from nucypher.acumen.perception import FleetSensor, ArchivedFleetState, RemoteUrsulaStatus
from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    StakingEscrowAgent,
    AdjudicatorAgent)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import datetime_at_period, datetime_to_period, estimate_block_number_for_period
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.network.nodes import Teacher, Learner
from twisted.internet import reactor
from twisted.logger import Logger

from monitor.utils import collector, DelayedLoopingCall


class CrawlerStorage:

    DB_FILE_NAME = 'crawler-storage.sqlite'
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DB_FILE_NAME)

    NODE_DB_NAME = 'node_info'
    NODE_DB_SCHEMA = [('staker_address', 'text primary key'), ('rest_url', 'text'), ('nickname', 'text'),
                      ('timestamp', 'text'), ('last_seen', 'text'), ('fleet_state_icon', 'text')]

    STATE_DB_NAME = 'fleet_state'
    STATE_DB_SCHEMA = [('nickname', 'text primary key'),
                       ('symbol', 'text'),
                       ('color_hex', 'text'),
                       ('color_name', 'text'),
                       ('updated', 'text')]

    TEACHER_DB_NAME = 'teacher'
    TEACHER_ID = 'current_teacher'
    TEACHER_DB_SCHEMA = [('id', 'text primary key'), ('checksum_address', 'text')]

    def __init__(self, db_filepath: str = DEFAULT_DB_FILEPATH):
        self.db_filepath = db_filepath

        if os.path.exists(self.db_filepath):
            os.remove(self.db_filepath)

        with self._connect() as db_conn:

            node_db_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.NODE_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.NODE_DB_NAME} ({node_db_schema})")

            state_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.STATE_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.STATE_DB_NAME} ({state_schema})")

            teacher_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.TEACHER_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.TEACHER_DB_NAME} ({teacher_schema})")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_filepath)

    def store_node_status(self, node_status: RemoteUrsulaStatus):

        # TODO: these DB fields should really be nullable
        if node_status.recorded_fleet_state:
            fleet_state_icon = node_status.recorded_fleet_state.nickname.icon
        else:
            fleet_state_icon = '?'

        if node_status.last_learned_from:
            last_learned_from = node_status.last_learned_from.iso8601()
        else:
            last_learned_from = '?'

        db_row = (node_status.staker_address,
                  node_status.rest_url,
                  str(node_status.nickname),
                  node_status.timestamp.iso8601(),
                  last_learned_from,
                  fleet_state_icon)

        with self._connect() as db_conn:
            db_conn.execute(f'REPLACE INTO {self.NODE_DB_NAME} VALUES(?,?,?,?,?,?)', db_row)

    @validate_checksum_address
    def remove_node_status(self, checksum_address: str):
        with self._connect() as db_conn:
            db_conn.execute(f"DELETE FROM {self.NODE_DB_NAME} WHERE staker_address='{checksum_address}'")

    def store_fleet_state(self, state: ArchivedFleetState):
        # TODO Limit the size of this table - no reason to store really old state values

        db_row = (str(state.nickname),
                  state.nickname.characters[0].symbol,
                  state.nickname.characters[0].color_hex,
                  state.nickname.characters[0].color_name,
                  # convert to rfc3339 for ease of sqlite3 sorting; we lose millisecond precision, but meh!
                  state.timestamp.rfc3339())
        sql = f'REPLACE INTO {self.STATE_DB_NAME} VALUES(?,?,?,?,?)'
        with self._connect() as db_conn:
            db_conn.execute(sql, db_row)

    def store_current_teacher(self, teacher_checksum: str):
        sql = f'REPLACE INTO {self.TEACHER_DB_NAME} VALUES (?,?)'
        with self._connect() as db_conn:
            db_conn.execute(sql, (self.TEACHER_ID, teacher_checksum))

    def __del__(self):
        if os.path.exists(self.db_filepath):
            os.remove(self.db_filepath)


def hooked_tracker_class(crawler_storage: CrawlerStorage):

    class HookedFleetSensor(FleetSensor):

        __crawler_storage = crawler_storage

        def record_fleet_state(self, *args, **kwargs):
            state_diff = super().record_fleet_state(*args, **kwargs)
            if not state_diff.empty():
                new_state = self._archived_states[-1]
                self.__crawler_storage.store_fleet_state(new_state)

                for checksum_address in state_diff.nodes_updated:
                    self.__crawler_storage.store_node_status(self.status_info(checksum_address))

                for checksum_address in state_diff.nodes_removed:
                    self.__crawler_storage.remove_node_status(checksum_address)

        def record_remote_fleet_state(self, checksum_address, *args, **kwargs):
            super().record_remote_fleet_state(checksum_address, *args, **kwargs)
            self.__crawler_storage.store_node_status(self.status_info(checksum_address))

    return HookedFleetSensor


class Crawler(Learner):
    """
    Obtain Blockchain information for Monitor and output to json.
    """

    _SHORT_LEARNING_DELAY = 2
    _LONG_LEARNING_DELAY = 30
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    LEARNING_TIMEOUT = 10
    DEFAULT_REFRESH_RATE = 60  # seconds
    REFRESH_RATE_WINDOW = 0.25

    METRICS_ENDPOINT = 'stats'
    DEFAULT_CRAWLER_HTTP_PORT = 9555

    ERROR_EVENTS = {
        # TODO for some reason this event causes issues with our web3 provider - #104
        # StakingEscrowAgent: ['Slashed'],
        AdjudicatorAgent: ['IncorrectCFragVerdict'],
    }
    ERROR_EVENTS_NUM_PAST_PERIODS = 2

    STAKER_PAGINATION_SIZE = 200

    def __init__(self,
                 crawler_http_port: int = DEFAULT_CRAWLER_HTTP_PORT,
                 registry: BaseContractRegistry = None,
                 db_filepath: str = CrawlerStorage.DEFAULT_DB_FILEPATH,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True,
                 *args, **kwargs):

        # Settings
        self.federated_only = False  # Nope - for compatibility with Learner TODO # nucypher/466
        Teacher.set_federated_mode(False)

        self.registry = registry or InMemoryContractRegistry.from_latest_publication()
        self.economics = EconomicsFactory.get_economics(registry=self.registry)
        self._refresh_rate = refresh_rate
        self._restart_on_error = restart_on_error

        # Tracking
        self.__storage = CrawlerStorage(db_filepath)
        self.tracker_class = hooked_tracker_class(self.__storage) # Used by Learner.__init__

        node_storage = ForgetfulNodeStorage(federated_only=False)

        super().__init__(save_metadata=True,
                         node_storage=node_storage,
                         verify_node_bonding=False,
                         *args, **kwargs)

        self.log = Logger(self.__class__.__name__)
        self.log.info(f"Storing status metadata in DB: {self.__storage.db_filepath}")

        # In-memory Metrics
        self._stats = {'status': 'initializing'}
        self._crawler_client = None

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Crawler Tasks
        self.__collection_round = 0
        self.__collecting_stats = False

        self._stats_collection_task = DelayedLoopingCall(f=self._collect_stats,
                                                         threaded=True,
                                                         start_delay=random.randint(2, 15))  # random staggered start

        # JSON Endpoint
        self._crawler_http_port = crawler_http_port
        self._flask = None

    def learn_from_teacher_node(self, *args, **kwargs):

        new_nodes = super().learn_from_teacher_node(*args, **kwargs)

        try:
            current_teacher = self.current_teacher_node(cycle=False)
        except self.NotEnoughTeachers as e:
            self.log.warn("Can't learn right now: {}".format(e.args[0]))
            return

        # update metadata of teacher - not just in memory but in the underlying storage system (db in this case)
        self.__storage.store_current_teacher(current_teacher.checksum_address)

        return new_nodes

    #
    # Measurements
    #

    @property
    def stats(self) -> dict:
        return self._stats

    @collector(label="Projected Stake and Stakers")
    def _measure_future_locked_tokens(self, periods: int = 365):
        period_range = range(1, periods + 1)
        token_counter = dict()
        for day in period_range:
            tokens, stakers = self.staking_agent.get_all_active_stakers(periods=day,
                                                                        pagination_size=self.STAKER_PAGINATION_SIZE)
            token_counter[day] = (float(NU.from_nunits(tokens).to_tokens()), len(stakers))
        return dict(token_counter)

    @collector(label="Top Stakes")
    def _measure_top_stakers(self) -> dict:
        _, stakers = self.staking_agent.get_all_active_stakers(periods=1, pagination_size=self.STAKER_PAGINATION_SIZE)
        data = dict(sorted(stakers.items(), key=lambda s: s[1], reverse=True))
        return data

    @collector(label="Staker Confirmation Status")
    def _measure_staker_activity(self) -> dict:
        confirmed, pending, inactive = self.staking_agent.partition_stakers_by_activity()
        inactive_without_expired = []
        for staker in inactive:
            if self._is_staker_expired(staker_address=staker):
                continue
            inactive_without_expired.append(staker)

        stakers = dict()
        stakers['active'] = len(confirmed)
        stakers['pending'] = len(pending)
        stakers['inactive'] = len(inactive_without_expired)
        return stakers

    @collector(label="Date/Time of Next Period")
    def _measure_start_of_next_period(self) -> str:
        """Returns iso8601 datetime of next period"""
        current_period = datetime_to_period(datetime=maya.now(), seconds_per_period=self.economics.seconds_per_period)
        next_period = datetime_at_period(period=current_period+1,
                                         seconds_per_period=self.economics.seconds_per_period,
                                         start_of_period=True)

        return next_period.iso8601()

    @collector(label="Known Nodes")
    def measure_known_nodes(self):

        #
        # Setup
        #
        current_period = datetime_to_period(datetime=maya.now(), seconds_per_period=self.economics.seconds_per_period)
        buckets = {-1: ('green', 'Confirmed'),           # Confirmed Next Period
                   0: ('#e0b32d', 'Pending'),            # Pending Confirmation of Next Period
                   current_period: ('#525ae3', 'Idle'),  # Never confirmed
                   NULL_ADDRESS: ('#d8d9da', 'Headless')  # Headless Staker (No Worker)
                   }

        shortest_uptime, newborn = float('inf'), None
        longest_uptime, uptime_king = 0, None

        uptime_template = '{days}d:{hours}h:{minutes}m'

        #
        # Scrape
        #

        payload = defaultdict(list)
        known_nodes = self._crawler_client.get_known_nodes_metadata()
        for staker_address in known_nodes:

            #
            # Confirmation Status Scraping
            #

            # is staker expired
            if self._is_staker_expired(staker_address=staker_address):
                # stake already expired, remove node from DB and ignore
                self.__storage.remove_node_status(checksum_address=staker_address)
                continue
            last_confirmed_period = self.staking_agent.get_last_committed_period(staker_address)
            missing_confirmations = current_period - last_confirmed_period
            worker = self.staking_agent.get_worker_from_staker(staker_address)
            if worker == NULL_ADDRESS:
                # missing_confirmations = NULL_ADDRESS
                continue  # TODO: Skip this DetachedWorker and do not display it
            try:
                color, status_message = buckets[missing_confirmations]
            except KeyError:
                color, status_message = 'red', f'Unconfirmed'
            node_status = {'status': status_message, 'missed_confirmations': missing_confirmations, 'color': color}

            #
            # Uptime Scraping
            #

            now = maya.now()
            timestamp = maya.MayaDT.from_iso8601(known_nodes[staker_address]['timestamp'])
            delta = now - timestamp

            node_qualifies_as_newborn = (delta.total_seconds() < shortest_uptime) and missing_confirmations == -1
            node_qualifies_for_uptime_king = (delta.total_seconds() > longest_uptime) and missing_confirmations == -1
            if node_qualifies_as_newborn:
                shortest_uptime, newborn = delta.total_seconds(), staker_address
            elif node_qualifies_for_uptime_king:
                longest_uptime, uptime_king = delta.total_seconds(), staker_address

            hours = delta.seconds // 3600
            minutes = delta.seconds % 3600 // 60
            natural_uptime = uptime_template.format(days=delta.days, hours=hours, minutes=minutes)

            #
            # Aggregate
            #

            known_nodes[staker_address]['status'] = node_status
            known_nodes[staker_address]['uptime'] = natural_uptime
            payload[status_message.lower()].append(known_nodes[staker_address])

        # There are not always winners...
        if newborn:
            known_nodes[newborn]['newborn'] = True
        if uptime_king:
            known_nodes[uptime_king]['uptime_king'] = True
        return payload

    def _collect_stats(self, threaded: bool = True) -> None:
        # TODO: Handle faulty connection to provider (requests.exceptions.ReadTimeout)
        if threaded:
            if self.__collecting_stats:
                self.log.debug("Skipping Round - Metrics collection thread is already running")
                return
            return reactor.callInThread(self._collect_stats, threaded=False)
        self.__collection_round += 1
        self.__collecting_stats = True

        start = maya.now()
        click.secho(f"Scraping Round #{self.__collection_round} ========================", color='blue')
        self.log.info("Collecting Statistics...")

        #
        # Read
        #

        # Time
        block = self.staking_agent.blockchain.client.w3.eth.getBlock('latest')
        block_number = block.number
        block_time = block.timestamp # epoch
        current_period = datetime_to_period(datetime=maya.now(), seconds_per_period=self.economics.seconds_per_period)
        click.secho("✓ ... Current Period", color='blue')
        next_period = self._measure_start_of_next_period()

        # Nodes
        teacher = self._crawler_client.get_current_teacher_checksum()
        states = self._crawler_client.get_previous_states_metadata()

        known_nodes = self.measure_known_nodes()

        activity = self._measure_staker_activity()

        # Stake
        global_locked_tokens = self.staking_agent.get_global_locked_tokens()
        click.secho("✓ ... Global Network Locked Tokens", color='blue')

        top_stakers = self._measure_top_stakers()

        # events
        network_events = self.check_network_events()

        #
        # Write
        #

        self._stats = {'blocknumber': block_number,
                       'blocktime': block_time,

                       'current_period': current_period,
                       'next_period': next_period,

                       'prev_states': states,
                       'current_teacher': teacher,
                       'known_nodes': len(self.known_nodes),
                       'activity': activity,
                       'node_details': known_nodes,

                       'global_locked_tokens': global_locked_tokens,
                       'top_stakers': top_stakers,
                       'network_events': network_events,
                       }
        done = maya.now()
        delta = done - start
        self.__collecting_stats = False
        click.echo(f"Scraping round completed (duration {delta}).", color='yellow')  # TODO: Make optional, use emitter, or remove
        click.echo("==========================================")
        self.log.debug(f"Collected new metrics took {delta}.")

    @collector(label="Network Events")
    def check_network_events(self) -> List[Dict]:
        blockchain_client = self.staking_agent.blockchain.client
        latest_block_number = blockchain_client.block_number

        two_periods_ago_datetime = maya.now() - maya.timedelta(days=self.ERROR_EVENTS_NUM_PAST_PERIODS * self.economics.days_per_period)
        two_periods_ago = datetime_to_period(datetime=two_periods_ago_datetime,
                                             seconds_per_period=self.economics.seconds_per_period)
        # estimate blocknumber - does not have to be exact
        two_periods_ago_est_blocknumber = estimate_block_number_for_period(
            period=two_periods_ago,
            seconds_per_period=self.economics.seconds_per_period,
            latest_block=latest_block_number)

        events_list = list()
        for agent_class, event_names in self.ERROR_EVENTS.items():
            agent = ContractAgency.get_agent(agent_class, registry=self.registry)
            for event_name in event_names:
                event = agent.contract.events[event_name]
                entries = event.getLogs(fromBlock=two_periods_ago_est_blocknumber, toBlock=latest_block_number)
                for event_record in entries:
                    record = EventRecord(event_record)
                    args = ", ".join(f"{k}:{v}" for k, v in record.args.items())
                    events_list.append(dict(
                        txhash=record.transaction_hash,
                        contract_name=agent.contract_name,
                        contract_address=agent.contract_address,
                        event_name=event_name,
                        block_number=record.block_number,
                        args=args,
                        timestamp=blockchain_client.w3.eth.getBlock(record.block_number).timestamp,
                    ))
        return events_list

    def make_flask_server(self):
        """JSON Endpoint"""
        flask = Flask('nucypher-monitor')
        self._flask = flask
        self._flask.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

        @flask.route('/stats', methods=['GET'])
        def stats():
            response = jsonify(self._stats)
            return response

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f'Unhandled error: {cleaned_traceback}. Attempting to restart crawler')
            if not self._stats_collection_task.running:
                self.start()
        else:
            self.log.critical(f'Unhandled error: {cleaned_traceback}')

    def start(self, eager: bool = False):
        """Start the crawler if not already running"""
        if not self.is_running:
            self.log.info('Starting Crawler...')
            if self._crawler_client is None:
                from monitor.db import CrawlerStorageClient
                self._crawler_client = CrawlerStorageClient()

            # start tasks
            collection_deferred = self._stats_collection_task.start(
                interval=random.randint(self._refresh_rate, int(self._refresh_rate * (1 + self.REFRESH_RATE_WINDOW))),
                now=eager)

            # hookup error callbacks
            collection_deferred.addErrback(self._handle_errors)

            # Start up
            self.start_learning_loop(now=False)
            self.make_flask_server()
            hx_deployer = HendrixDeploy(action="start", options={"wsgi": self._flask, "http_port": self._crawler_http_port})
            hx_deployer.run()  # <--- Blocking Call to Reactor

    def stop(self):
        """Stop the crawler if currently running"""
        if self.is_running:
            self.log.info('Stopping Monitor Crawler')

            # stop tasks
            self._stats_collection_task.stop()


    @property
    def is_running(self):
        """Returns True if currently running, False otherwise"""
        return self._stats_collection_task.running

    def _is_staker_expired(self, staker_address: ChecksumAddress):
        tokens_for_current_period = self.staking_agent.get_locked_tokens(staker_address=staker_address)
        tokens_for_next_period = self.staking_agent.get_locked_tokens(staker_address=staker_address, periods=1)

        return tokens_for_current_period == 0 and tokens_for_next_period == 0
