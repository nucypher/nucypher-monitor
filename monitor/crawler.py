import os
import random
import sqlite3
from collections import defaultdict
from typing import Tuple

import click
import maya
import requests
from constant_sorrow.constants import NOT_STAKING
from flask import Flask, jsonify
from hendrix.deploy.base import HendrixDeploy
from influxdb import InfluxDBClient
from maya import MayaDT
from monitor.utils import collector, DelayedLoopingCall
from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    StakingEscrowAgent,
    AdjudicatorAgent,
    PolicyManagerAgent)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, BaseContractRegistry
from nucypher.blockchain.eth.token import StakeList, NU
from nucypher.blockchain.eth.utils import datetime_at_period, datetime_to_period
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.network.nodes import FleetSensor, Teacher
from nucypher.network.nodes import Learner
from twisted.internet import reactor
from twisted.logger import Logger


class SQLiteForgetfulNodeStorage(ForgetfulNodeStorage):
    """
    SQLite forgetful storage of node metadata
    """
    _name = 'sqlite'
    DB_FILE_NAME = 'nodes.sqlite'
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DB_FILE_NAME)

    NODE_DB_NAME = 'node_info'
    NODE_DB_SCHEMA = [('staker_address', 'text primary key'), ('rest_url', 'text'), ('nickname', 'text'),
                      ('timestamp', 'text'), ('last_seen', 'text'), ('fleet_state_icon', 'text')]

    def __init__(self, db_filepath: str = DEFAULT_DB_FILEPATH, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_filepath = db_filepath
        self.init_db_tables()

    def __del__(self):
        if os.path.exists(self.db_filepath):
            os.remove(self.db_filepath)

    def store_node_metadata(self, node, filepath: str = None):
        self.__write_node_metadata(node)
        return super().store_node_metadata(node=node, filepath=filepath)

    @validate_checksum_address
    def remove(self,
               checksum_address: str,
               metadata: bool = True,
               certificate: bool = True
               ) -> Tuple[bool, str]:

        if metadata is True:
            with sqlite3.connect(self.db_filepath) as db_conn:
                db_conn.execute(f"DELETE FROM {self.NODE_DB_NAME} WHERE staker_address='{checksum_address}'")

        return super().remove(checksum_address=checksum_address, metadata=metadata, certificate=certificate)

    def clear(self, metadata: bool = True, certificates: bool = True) -> None:
        if metadata is True:
            with sqlite3.connect(self.db_filepath) as db_conn:
                db_conn.execute(f"DELETE FROM {self.NODE_DB_NAME}")

        super().clear(metadata=metadata, certificates=certificates)

    def initialize(self) -> bool:
        if os.path.exists(self.db_filepath):
            os.remove(self.db_filepath)
        self.init_db_tables()
        return super().initialize()

    def init_db_tables(self):
        with sqlite3.connect(self.db_filepath) as db_conn:
            # ensure tables are empty
            db_conn.execute(f"DROP TABLE IF EXISTS {self.NODE_DB_NAME}")

            # create fresh new node table (same column names as FleetStateTracker.abridged_nodes_details)
            node_db_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.NODE_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.NODE_DB_NAME} ({node_db_schema})")

    def __write_node_metadata(self, node):
        node.mature()
        node_dict = node.node_details(node=node)
        db_row = (node_dict['staker_address'],
                  node_dict['rest_url'],
                  node_dict['nickname'],
                  node_dict['timestamp'],
                  node_dict['last_seen'],
                  node_dict['fleet_state_icon'])
        with sqlite3.connect(self.db_filepath) as db_conn:
            db_conn.execute(f'REPLACE INTO {self.NODE_DB_NAME} VALUES(?,?,?,?,?,?)', db_row)


class CrawlerNodeStorage(SQLiteForgetfulNodeStorage):
    _name = 'crawler'

    DB_FILE_NAME = 'crawler-storage.sqlite'
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DB_FILE_NAME)

    STATE_DB_NAME = 'fleet_state'
    STATE_DB_SCHEMA = [('nickname', 'text primary key'),
                       ('symbol', 'text'),
                       ('color_hex', 'text'),
                       ('color_name', 'text'),
                       ('updated', 'text')]

    TEACHER_DB_NAME = 'teacher'
    TEACHER_ID = 'current_teacher'
    TEACHER_DB_SCHEMA = [('id', 'text primary key'), ('checksum_address', 'text')]

    def __init__(self, storage_filepath: str = DEFAULT_DB_FILEPATH, *args, **kwargs):
        super().__init__(db_filepath=storage_filepath, federated_only=False, *args, **kwargs)

    def init_db_tables(self):
        with sqlite3.connect(self.db_filepath) as db_conn:

            # ensure table is empty
            for table in [self.STATE_DB_NAME, self.TEACHER_DB_NAME]:
                db_conn.execute(f"DROP TABLE IF EXISTS {table}")

            # create fresh new state table (same column names as FleetStateTracker.abridged_state_details)
            state_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.STATE_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.STATE_DB_NAME} ({state_schema})")

            # create new teacher table
            teacher_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.TEACHER_DB_SCHEMA)
            db_conn.execute(f"CREATE TABLE {self.TEACHER_DB_NAME} ({teacher_schema})")
        super().init_db_tables()

    def clear(self, metadata: bool = True, certificates: bool = True) -> None:
        if metadata is True:
            with sqlite3.connect(self.db_filepath) as db_conn:
                # TODO Clear the states table here?
                for table in [self.STATE_DB_NAME, self.TEACHER_DB_NAME]:
                    db_conn.execute(f"DELETE FROM {table}")

        super().clear(metadata=metadata, certificates=certificates)

    def store_state_metadata(self, state: dict):
        # TODO Limit the size of this table - no reason to store really old state values

        db_row = (state['nickname'],
                  state['symbol'],
                  state['color_hex'],
                  state['color_name'],
                  # convert to rfc3339 for ease of sqlite3 sorting; we lose millisecond precision, but meh!
                  MayaDT.from_rfc2822(state['updated']).rfc3339())
        sql = f'REPLACE INTO {self.STATE_DB_NAME} VALUES(?,?,?,?,?)'
        with sqlite3.connect(self.db_filepath) as db_conn:
            db_conn.execute(sql, db_row)

    def store_current_teacher(self, teacher_checksum: str):
        sql = f'REPLACE INTO {self.TEACHER_DB_NAME} VALUES (?,?)'
        with sqlite3.connect(self.db_filepath) as db_conn:
            db_conn.execute(sql, (self.TEACHER_ID, teacher_checksum))


class Crawler(Learner):
    """
    Obtain Blockchain information for Monitor and output to a DB.
    """

    _SHORT_LEARNING_DELAY = 2
    _LONG_LEARNING_DELAY = 30
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    LEARNING_TIMEOUT = 10
    DEFAULT_REFRESH_RATE = 60  # seconds
    REFRESH_RATE_WINDOW = 0.25

    # InfluxDB Line Protocol Format (note the spaces, commas):
    # +-----------+--------+-+---------+-+---------+
    # |measurement|,tag_set| |field_set| |timestamp|
    # +-----------+--------+-+---------+-+---------+
    NODE_MEASUREMENT = 'crawler_node_info'
    NODE_LINE_PROTOCOL = '{measurement},staker_address={staker_address} ' \
                         'worker_address="{worker_address}",' \
                         'start_date={start_date},' \
                         'end_date={end_date},' \
                         'stake={stake},' \
                         'locked_stake={locked_stake},' \
                         'current_period={current_period}i,' \
                         'last_confirmed_period={last_confirmed_period}i ' \
                         '{timestamp}'

    EVENT_MEASUREMENT = 'crawler_event_info'
    EVENT_LINE_PROTOCOL = '{measurement},txhash={txhash} ' \
                          'contract_name="{contract_name}",' \
                          'contract_address="{contract_address}",' \
                          'event_name="{event_name}",' \
                          'block_number={block_number}i,' \
                          'args="{args}" ' \
                          '{timestamp}'

    INFLUX_DB_NAME = 'network'
    INFLUX_RETENTION_POLICY_NAME = 'network_info_retention'

    # TODO: review defaults for retention policy
    RETENTION = '5w'  # Weeks
    REPLICATION = '1'

    METRICS_ENDPOINT = 'stats'
    DEFAULT_CRAWLER_HTTP_PORT = 9555

    ERROR_EVENTS = {
        StakingEscrowAgent: ['Slashed'],
        AdjudicatorAgent: ['IncorrectCFragVerdict'],
        PolicyManagerAgent: ['NodeBrokenState'],
    }

    def __init__(self,
                 influx_host: str,
                 influx_port: int,
                 crawler_http_port: int = DEFAULT_CRAWLER_HTTP_PORT,
                 registry: BaseContractRegistry = None,
                 node_storage_filepath: str = CrawlerNodeStorage.DEFAULT_DB_FILEPATH,
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

        # TODO: Needs cleanup
        # Tracking
        node_storage = CrawlerNodeStorage(storage_filepath=node_storage_filepath)

        class MonitoringTracker(FleetSensor):
            def record_fleet_state(self, *args, **kwargs):
                new_state_or_none = super().record_fleet_state(*args, **kwargs)
                if new_state_or_none:
                    _, new_state = new_state_or_none
                    state = self.abridged_state_details(new_state)
                    node_storage.store_state_metadata(state)
        self.tracker_class = MonitoringTracker

        super().__init__(save_metadata=True,
                         node_storage=node_storage,
                         verify_node_bonding=False,
                         *args, **kwargs)

        self.log = Logger(self.__class__.__name__)
        self.log.info(f"Storing node metadata in DB: {node_storage.db_filepath}")
        self.log.info(f"Storing blockchain metadata in DB: {influx_host}:{influx_port}")

        # In-memory Metrics
        self._stats = {'status': 'initializing'}
        self._crawler_client = None

        # Initialize InfluxDB
        self._db_host = influx_host
        self._db_port = influx_port
        self._influx_client = None

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Crawler Tasks
        self.__collection_round = 0
        self.__collecting_nodes = False  # thread tracking
        self.__collecting_stats = False
        self.__events_from_block = 0  # from the beginning
        self.__collecting_events = False

        self._node_details_task = DelayedLoopingCall(f=self._learn_about_nodes,
                                                     start_delay=random.randint(2, 15))  # random staggered start
        self._stats_collection_task = DelayedLoopingCall(f=self._collect_stats,
                                                         threaded=True,
                                                         start_delay=random.randint(2, 15))  # random staggered start
        self._events_collection_task = DelayedLoopingCall(f=self._collect_events,
                                                          start_delay=random.randint(2, 15))  # random staggered start

        # JSON Endpoint
        self._crawler_http_port = crawler_http_port
        self._flask = None

    def _initialize_influx(self):
        try:
            db_list = self._influx_client.get_list_database()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"No connection to InfluxDB at {self._db_host}:{self._db_port}")
        found_db = (list(filter(lambda db: db['name'] == self.INFLUX_DB_NAME, db_list)))
        if len(found_db) == 0:
            # db not previously created
            self.log.info(f'Database {self.INFLUX_DB_NAME} not found, creating it')
            self._influx_client.create_database(self.INFLUX_DB_NAME)
            self._influx_client.create_retention_policy(name=self.INFLUX_RETENTION_POLICY_NAME,
                                                        duration=self.RETENTION,
                                                        replication=self.REPLICATION,
                                                        database=self.INFLUX_DB_NAME,
                                                        default=True)
        else:
            self.log.info(f'Database {self.INFLUX_DB_NAME} already exists, no need to create it')

    def learn_from_teacher_node(self, *args, **kwargs):
        try:
            current_teacher = self.current_teacher_node(cycle=False)
        except self.NotEnoughTeachers as e:
            self.log.warn("Can't learn right now: {}".format(e.args[0]))
            return

        new_nodes = super().learn_from_teacher_node(*args, **kwargs)

        # update metadata of teacher - not just in memory but in the underlying storage system (db in this case)
        self.node_storage.store_node_metadata(current_teacher)
        self.node_storage.store_current_teacher(current_teacher.checksum_address)

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
            tokens, stakers = self.staking_agent.get_all_active_stakers(periods=day)
            token_counter[day] = (float(NU.from_nunits(tokens).to_tokens()), len(stakers))
        return dict(token_counter)

    @collector(label="Top Stakes")
    def _measure_top_stakers(self) -> dict:
        _, stakers = self.staking_agent.get_all_active_stakers(periods=1)
        data = dict(sorted(stakers.items(), key=lambda s: s[1], reverse=True))
        return data

    @collector(label="Staker Confirmation Status")
    def _measure_staker_activity(self) -> dict:
        confirmed, pending, inactive = self.staking_agent.partition_stakers_by_activity()
        stakers = dict()
        stakers['active'] = len(confirmed)
        stakers['pending'] = len(pending)
        stakers['inactive'] = len(inactive)
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
        future_locked_tokens = self._measure_future_locked_tokens()
        global_locked_tokens = self.staking_agent.get_global_locked_tokens()
        click.secho("✓ ... Global Network Locked Tokens", color='blue')

        top_stakers = self._measure_top_stakers()

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
                       'future_locked_tokens': future_locked_tokens,
                       'top_stakers': top_stakers,
                       }
        done = maya.now()
        delta = done - start
        self.__collecting_stats = False
        click.echo(f"Scraping round completed (duration {delta}).", color='yellow')  # TODO: Make optional, use emitter, or remove
        click.echo("==========================================")
        self.log.debug(f"Collected new metrics took {delta}.")

    @collector(label="Network Event Details")
    def _collect_events(self, threaded: bool = True):
        if threaded:
            if self.__collecting_events:
                self.log.debug("Skipping Round - Events collection thread is already running")
                return
            return reactor.callInThread(self._collect_events, threaded=False)
        self.__collecting_events = True


        blockchain_client = self.staking_agent.blockchain.client
        latest_block_number = blockchain_client.block_number
        from_block = self.__events_from_block

        #block_time = latest_block.timestamp  # precision in seconds

        current_period = datetime_to_period(datetime=maya.now(), seconds_per_period=self.economics.seconds_per_period)

        events_list = list()
        for agent_class, event_names in self.ERROR_EVENTS.items():
            agent = ContractAgency.get_agent(agent_class, registry=self.registry)
            for event_name in event_names:
                events = [agent.contract.events[event_name]]
                for event in events:
                    entries = event.getLogs(fromBlock=from_block, toBlock=latest_block_number)
                    for event_record in entries:
                        record = EventRecord(event_record)
                        args = ", ".join(f"{k}:{v}" for k, v in record.args.items())
                        events_list.append(self.EVENT_LINE_PROTOCOL.format(
                            measurement=self.EVENT_MEASUREMENT,
                            txhash=record.transaction_hash,
                            contract_name=agent.contract_name,
                            contract_address=agent.contract_address,
                            event_name=event_name,
                            block_number=record.block_number,
                            args=args,
                            timestamp=blockchain_client.w3.eth.getBlock(record.block_number).timestamp,
                        ))

        success = self._influx_client.write_points(events_list,
                                                   database=self.INFLUX_DB_NAME,
                                                   time_precision='s',
                                                   batch_size=10000,
                                                   protocol='line')
        self.__events_from_block = latest_block_number
        self.__collecting_events = False
        if not success:
            # TODO: What do we do here - Event hook for alerting?
            self.log.warn(f'Unable to write events to database {self.INFLUX_DB_NAME} '
                          f'| Period {current_period} starting from block {from_block}')

    @collector(label="Known Node Details")
    def _learn_about_nodes(self, threaded: bool = True):
        if threaded:
            if self.__collecting_nodes:
                self.log.debug("Skipping Round - Nodes collection thread is already running")
                return
            return reactor.callInThread(self._learn_about_nodes, threaded=False)
        self.__collecting_nodes = True

        agent = self.staking_agent
        known_nodes = list(self.known_nodes)

        block_time = agent.blockchain.client.get_blocktime()  # precision in seconds
        current_period = datetime_to_period(datetime=maya.now(), seconds_per_period=self.economics.seconds_per_period)

        log = f'Processing {len(known_nodes)} nodes at {MayaDT(epoch=block_time)} | Period {current_period}'
        self.log.info(log)

        data = list()
        for node in known_nodes:

            staker_address = node.checksum_address
            worker = agent.get_worker_from_staker(staker_address)

            stake = agent.owned_tokens(staker_address)
            staked_nu_tokens = float(NU.from_nunits(stake).to_tokens())
            locked_nu_tokens = float(NU.from_nunits(agent.get_locked_tokens(staker_address=staker_address)).to_tokens())

            economics = EconomicsFactory.get_economics(registry=self.registry)
            stakes = StakeList(checksum_address=staker_address, registry=self.registry)
            stakes.refresh()

            if stakes.initial_period is NOT_STAKING:
                continue  # TODO: Skip this measurement for now

            start_date = datetime_at_period(stakes.initial_period, seconds_per_period=economics.seconds_per_period)
            start_date = start_date.datetime().timestamp()
            end_date = datetime_at_period(stakes.terminal_period, seconds_per_period=economics.seconds_per_period)
            end_date = end_date.datetime().timestamp()

            last_confirmed_period = agent.get_last_committed_period(staker_address)

            num_work_orders = 0  # len(node.work_orders())  # TODO: Only works for is_me with datastore attached

            # TODO: do we need to worry about how much information is in memory if number of nodes is
            #  large i.e. should I check for size of data and write within loop if too big
            data.append(self.NODE_LINE_PROTOCOL.format(
                measurement=self.NODE_MEASUREMENT,
                staker_address=staker_address,
                worker_address=worker,
                start_date=start_date,
                end_date=end_date,
                stake=staked_nu_tokens,
                locked_stake=locked_nu_tokens,
                current_period=current_period,
                last_confirmed_period=last_confirmed_period,
                timestamp=block_time,
                work_orders=num_work_orders
            ))

        success = self._influx_client.write_points(data,
                                                   database=self.INFLUX_DB_NAME,
                                                   time_precision='s',
                                                   batch_size=10000,
                                                   protocol='line')
        self.__collecting_nodes = False
        if not success:
            # TODO: What do we do here - Event hook for alerting?
            self.log.warn(f'Unable to write node information to database {self.INFLUX_DB_NAME} at '
                          f'{MayaDT(epoch=block_time)} | Period {current_period}')

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
            if not self._node_details_task.running:
                self.start()
        else:
            self.log.critical(f'Unhandled error: {cleaned_traceback}')

    def start(self, eager: bool = False):
        """Start the crawler if not already running"""
        if not self.is_running:
            self.log.info('Starting Crawler...')
            if self._influx_client is None:
                self._influx_client = InfluxDBClient(host=self._db_host, port=self._db_port, database=self.INFLUX_DB_NAME)
                self._initialize_influx()

            if self._crawler_client is None:
                from monitor.db import CrawlerStorageClient
                self._crawler_client = CrawlerStorageClient()

                # TODO: Maybe?
                # from monitor.db import CrawlerInfluxClient
                # self.crawler_influx_client = CrawlerInfluxClient()

            # start tasks
            node_learner_deferred = self._node_details_task.start(
                interval=random.randint(int(self._refresh_rate * (1 - self.REFRESH_RATE_WINDOW)), self._refresh_rate),
                now=eager)
            collection_deferred = self._stats_collection_task.start(
                interval=random.randint(self._refresh_rate, int(self._refresh_rate * (1 + self.REFRESH_RATE_WINDOW))),
                now=eager)

            # get known last event block
            self.__events_from_block = self._get_last_known_blocknumber()
            events_deferred = self._events_collection_task.start(interval=self._refresh_rate, now=eager)

            # hookup error callbacks
            node_learner_deferred.addErrback(self._handle_errors)
            collection_deferred.addErrback(self._handle_errors)
            events_deferred.addErrback(self._handle_errors)

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
            self._node_details_task.stop()
            self._events_collection_task.stop()
            self._stats_collection_task.stop()

            if self._influx_client is not None:
                self._influx_client.close()
                self._influx_client = None

    @property
    def is_running(self):
        """Returns True if currently running, False otherwise"""
        return self._node_details_task.running

    def _get_last_known_blocknumber(self):
        last_known_blocknumber = 0
        blocknumber_result = list(
            self._influx_client.query(f'SELECT MAX(block_number) from {self.EVENT_MEASUREMENT}').get_points())
        if len(blocknumber_result) > 0:
            last_known_blocknumber = blocknumber_result[0]['max']

        return last_known_blocknumber
