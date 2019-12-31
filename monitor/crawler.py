import os

import requests
from influxdb import InfluxDBClient
from maya import MayaDT
from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    StakingEscrowAgent,
)
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.storages import SQLiteForgetfulNodeStorage
from nucypher.network.nodes import FleetStateTracker
from nucypher.network.nodes import Learner
from twisted.internet import task
from twisted.logger import Logger


class CrawlerNodeStorage(SQLiteForgetfulNodeStorage):
    _name = 'crawler'

    DB_FILE_NAME = 'crawler-storage.sqlite'
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DB_FILE_NAME)

    STATE_DB_NAME = 'fleet_state'
    STATE_DB_SCHEMA = [('nickname', 'text primary key'), ('symbol', 'text'),
                       ('color_hex', 'text'), ('color_name', 'text'), ('updated', 'text')]

    TEACHER_DB_NAME = 'teacher'
    TEACHER_ID = 'current_teacher'
    TEACHER_DB_SCHEMA = [('id', 'text primary key'), ('checksum_address', 'text')]

    def __init__(self, storage_filepath: str = DEFAULT_DB_FILEPATH, *args, **kwargs):
        super().__init__(db_filepath=storage_filepath, federated_only=False, *args, **kwargs)

    def init_db_tables(self):
        with self.db_conn:
            # ensure table is empty
            for table in [self.STATE_DB_NAME, self.TEACHER_DB_NAME]:
                self.db_conn.execute(f"DROP TABLE IF EXISTS {table}")

            # create fresh new state table (same column names as FleetStateTracker.abridged_state_details)
            state_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.STATE_DB_SCHEMA)
            self.db_conn.execute(f"CREATE TABLE {self.STATE_DB_NAME} ({state_schema})")

            # create new teacher table
            teacher_schema = ", ".join(f"{schema[0]} {schema[1]}" for schema in self.TEACHER_DB_SCHEMA)
            self.db_conn.execute(f"CREATE TABLE {self.TEACHER_DB_NAME} ({teacher_schema})")
        super().init_db_tables()

    def clear(self, metadata: bool = True, certificates: bool = True) -> None:
        if metadata is True:
            with self.db_conn:
                # TODO: do we need to clear the states table here?
                for table in [self.STATE_DB_NAME, self.TEACHER_DB_NAME]:
                    self.db_conn.execute(f"DELETE FROM {table}")

        super().clear(metadata=metadata, certificates=certificates)

    def store_state_metadata(self, state):
        self.__write_state_metadata(state)

    def __write_state_metadata(self, state):
        from nucypher.network.nodes import FleetStateTracker
        state_dict = FleetStateTracker.abridged_state_details(state)
        # convert updated timestamp format for supported sqlite3 sorting
        state_dict['updated'] = state.updated.rfc3339()
        db_row = (state_dict['nickname'], state_dict['symbol'], state_dict['color_hex'],
                  state_dict['color_name'], state_dict['updated'])
        with self.db_conn:
            self.db_conn.execute(f'REPLACE INTO {self.STATE_DB_NAME} VALUES(?,?,?,?,?)', db_row)
            # TODO we should limit the size of this table - no reason to store really old state values

    def store_current_teacher(self, teacher_checksum: str):
        with self.db_conn:
            self.db_conn.execute(f'REPLACE INTO {self.TEACHER_DB_NAME} VALUES (?,?)',
                                 (self.TEACHER_ID, teacher_checksum))


class Crawler(Learner):
    """
    Obtain Blockchain information for Monitor and output to a DB.
    """

    _SHORT_LEARNING_DELAY = .5
    _LONG_LEARNING_DELAY = 30
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    DEFAULT_REFRESH_RATE = 60  # seconds

    # InfluxDB Line Protocol Format (note the spaces, commas):
    # +-----------+--------+-+---------+-+---------+
    # |measurement|,tag_set| |field_set| |timestamp|
    # +-----------+--------+-+---------+-+---------+
    BLOCKCHAIN_DB_MEASUREMENT = 'crawler_node_info'
    BLOCKCHAIN_DB_LINE_PROTOCOL = '{measurement},staker_address={staker_address} ' \
                                      'worker_address="{worker_address}",' \
                                      'start_date={start_date},' \
                                      'end_date={end_date},' \
                                      'stake={stake},' \
                                      'locked_stake={locked_stake},' \
                                      'current_period={current_period}i,' \
                                      'last_confirmed_period={last_confirmed_period}i ' \
                                  '{timestamp}'
    BLOCKCHAIN_DB_NAME = 'network'

    BLOCKCHAIN_DB_RETENTION_POLICY_NAME = 'network_info_retention'
    BLOCKCHAIN_DB_RETENTION_POLICY_PERIOD = '5w'  # 5 weeks of data
    BLOCKCHAIN_DB_RETENTION_POLICY_REPLICATION = '1'

    def __init__(self,
                 registry,
                 blockchain_db_host: str,
                 blockchain_db_port: int,
                 node_storage_filepath: str = CrawlerNodeStorage.DEFAULT_DB_FILEPATH,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True,
                 *args, **kwargs):

        self.registry = registry
        self.federated_only = False
        node_storage = CrawlerNodeStorage(storage_filepath=node_storage_filepath)

        class MonitoringTracker(FleetStateTracker):
            def record_fleet_state(self, *args, **kwargs):
                new_state_or_none = super().record_fleet_state(*args, **kwargs)
                if new_state_or_none:
                    _, new_state = new_state_or_none
                    node_storage.store_state_metadata(new_state)

        self.tracker_class = MonitoringTracker

        super().__init__(save_metadata=True, node_storage=node_storage, *args, **kwargs)
        self.log = Logger(self.__class__.__name__)
        self.log.info(f"Storing node metadata in DB: {node_storage.db_filepath}")
        self.log.info(f"Storing blockchain metadata in DB: {blockchain_db_host}:{blockchain_db_port}")

        self._refresh_rate = refresh_rate
        self._restart_on_error = restart_on_error

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Crawler Tasks
        self._nodes_contract_info_learning_task = task.LoopingCall(self._learn_about_nodes_contract_info)

        # initialize InfluxDB
        self._db_host = blockchain_db_host
        self._db_port = blockchain_db_port
        self._blockchain_db_client = None

    def _ensure_blockchain_db_exists(self):
        try:
            db_list = self._blockchain_db_client.get_list_database()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"No connection to InfluxDB at {self._db_host}:{self._db_port}")
        found_db = (list(filter(lambda db: db['name'] == self.BLOCKCHAIN_DB_NAME, db_list)))
        if len(found_db) == 0:
            # db not previously created
            self.log.info(f'Database {self.BLOCKCHAIN_DB_NAME} not found, creating it')
            self._blockchain_db_client.create_database(self.BLOCKCHAIN_DB_NAME)
            # TODO: review defaults for retention policy
            self._blockchain_db_client.create_retention_policy(name=self.BLOCKCHAIN_DB_RETENTION_POLICY_NAME,
                                                               duration=self.BLOCKCHAIN_DB_RETENTION_POLICY_PERIOD,
                                                               replication=self.BLOCKCHAIN_DB_RETENTION_POLICY_REPLICATION,
                                                               database=self.BLOCKCHAIN_DB_NAME,
                                                               default=True)
        else:
            self.log.info(f'Database {self.BLOCKCHAIN_DB_NAME} already exists, no need to create it')

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

    def _learn_about_nodes_contract_info(self):
        agent = self.staking_agent

        block_time = agent.blockchain.client.w3.eth.getBlock('latest').timestamp  # precision in seconds
        current_period = agent.get_current_period()

        nodes_dict = self.known_nodes.abridged_nodes_dict()
        self.log.info(f'Processing {len(nodes_dict)} nodes at '
                      f'{MayaDT(epoch=block_time)} | Period {current_period}')
        data = []
        for staker_address in nodes_dict:
            worker = agent.get_worker_from_staker(staker_address)

            stake = agent.owned_tokens(staker_address)
            staked_nu_tokens = float(NU.from_nunits(stake).to_tokens())
            locked_nu_tokens = float(NU.from_nunits(agent.get_locked_tokens(
                staker_address=staker_address)).to_tokens())

            economics = TokenEconomicsFactory.get_economics(registry=self.registry)
            stakes = StakeList(checksum_address=staker_address, registry=self.registry)
            stakes.refresh()

            # store dates as floats for comparison purposes
            start_date = datetime_at_period(stakes.initial_period,
                                            seconds_per_period=economics.seconds_per_period).datetime().timestamp()
            end_date = datetime_at_period(stakes.terminal_period,
                                          seconds_per_period=economics.seconds_per_period).datetime().timestamp()

            last_confirmed_period = agent.get_last_active_period(staker_address)

            # TODO: do we need to worry about how much information is in memory if number of nodes is
            #  large i.e. should I check for size of data and write within loop if too big
            data.append(self.BLOCKCHAIN_DB_LINE_PROTOCOL.format(
                measurement=self.BLOCKCHAIN_DB_MEASUREMENT,
                staker_address=staker_address,
                worker_address=worker,
                start_date=start_date,
                end_date=end_date,
                stake=staked_nu_tokens,
                locked_stake=locked_nu_tokens,
                current_period=current_period,
                last_confirmed_period=last_confirmed_period,
                timestamp=block_time
            ))

        if not self._blockchain_db_client.write_points(data,
                                                       database=self.BLOCKCHAIN_DB_NAME,
                                                       time_precision='s',
                                                       batch_size=10000,
                                                       protocol='line'):
            # TODO: what do we do here
            self.log.warn(f'Unable to write to database {self.BLOCKCHAIN_DB_NAME} at '
                          f'{MayaDT(epoch=block_time)} | Period {current_period}')

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f'Unhandled error: {cleaned_traceback}. Attempting to restart crawler')
            if not self._nodes_contract_info_learning_task.running:
                self.start()
        else:
            self.log.critical(f'Unhandled error: {cleaned_traceback}')

    def start(self):
        """Start the crawler if not already running"""
        if not self.is_running:
            self.log.info('Starting Monitor Crawler')
            if self._blockchain_db_client is None:
                self._blockchain_db_client = InfluxDBClient(host=self._db_host,
                                                            port=self._db_port,
                                                            database=self.BLOCKCHAIN_DB_NAME)
                self._ensure_blockchain_db_exists()

            # start tasks
            node_learner_deferred = self._nodes_contract_info_learning_task.start(interval=self._refresh_rate,
                                                                                  now=False)

            # hookup error callbacks
            node_learner_deferred.addErrback(self._handle_errors)

            self.start_learning_loop(now=False)

    def stop(self):
        """Stop the crawler if currently running"""
        if self.is_running:
            self.log.info('Stopping Monitor Crawler')

            # stop tasks
            self._nodes_contract_info_learning_task.stop()

            if self._blockchain_db_client is not None:
                self._blockchain_db_client.close()
                self._blockchain_db_client = None

            # TODO: should I delete the NodeStorage to close the sqlite db connection here?

    @property
    def is_running(self):
        """Returns True if currently running, False otherwise"""
        return self._nodes_contract_info_learning_task.running
