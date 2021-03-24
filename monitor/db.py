import os
import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List

from influxdb import InfluxDBClient
from maya import MayaDT

from monitor.crawler import CrawlerStorage, Crawler
from monitor.utils import collector
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class CrawlerStorageClient:

    DB_FILE_NAME = CrawlerStorage.DB_FILE_NAME
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DB_FILE_NAME)

    def __init__(self, db_filepath: str = DEFAULT_DB_FILEPATH):
        self._db_filepath = db_filepath

    def get_known_nodes_metadata(self) -> Dict:
        # dash threading means that connection needs to be established in same thread as use
        db_conn = sqlite3.connect(self._db_filepath)
        try:
            result = db_conn.execute(f"SELECT * FROM {CrawlerStorage.NODE_DB_NAME} ORDER BY staker_address")

            # TODO use `pandas` package instead to automatically get dict?
            known_nodes = OrderedDict()
            column_names = [description[0] for description in result.description]
            for row in result:
                node_info = dict()
                staker_address = row[0]
                for idx, value in enumerate(row):
                    node_info[column_names[idx]] = row[idx]
                known_nodes[staker_address] = node_info

            return known_nodes
        finally:
            db_conn.close()

    @collector(label="Previous Fleet States")
    def get_previous_states_metadata(self, limit: int = 20) -> List[Dict]:
        # dash threading means that connection needs to be established in same thread as use
        db_conn = sqlite3.connect(self._db_filepath)
        states_dict_list = []
        try:
            result = db_conn.execute(f"SELECT * FROM {CrawlerStorage.STATE_DB_NAME} "
                                     f"ORDER BY datetime(updated) DESC LIMIT {limit}")

            # TODO use `pandas` package instead to automatically get dict?
            column_names = [description[0] for description in result.description]
            for row in result:
                state_info = dict()
                for idx, value in enumerate(row):
                    column_name = column_names[idx]
                    if column_name == 'updated':
                        # convert column from rfc3339 (for sorting) back to rfc2822
                        # TODO does this matter for displaying? - it doesn't, but rfc2822 is easier on the eyes
                        state_info[column_name] = MayaDT.from_rfc3339(row[idx]).rfc2822()
                    else:
                        state_info[column_name] = row[idx]
                states_dict_list.append(state_info)

            return states_dict_list
        finally:
            db_conn.close()

    @collector(label="Latest Teacher")
    def get_current_teacher_checksum(self):
        db_conn = sqlite3.connect(self._db_filepath)
        try:
            result = db_conn.execute(f"SELECT checksum_address from {CrawlerStorage.TEACHER_DB_NAME} LIMIT 1")
            for row in result:
                return row[0]

            return None
        finally:
            db_conn.close()


class CrawlerInfluxClient:
    """
    Performs operations on data in the Crawler DB.

    Helpful for data intensive long-running graphing calculations on historical data.
    """
    def __init__(self, host, port, database):
        self._client = InfluxDBClient(host=host, port=port, database=database)

    def get_historical_locked_tokens_over_range(self, days: int):
        range_begin, range_end = self._get_range_bookends(days)
        results = list(self._client.query(f"SELECT SUM(locked_stake) "
                                          f"FROM ("
                                          f"SELECT staker_address, current_period, "
                                          f"LAST(locked_stake) "
                                          f"AS locked_stake "
                                          f"FROM {Crawler.NODE_MEASUREMENT} "
                                          f"WHERE time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' "
                                          f"AND "
                                          f"time < '{MayaDT.from_datetime(range_end).rfc3339()}' "
                                          f"GROUP BY staker_address, time(1d)"
                                          f") "
                                          f"GROUP BY time(1d)").get_points())

        # Note: all days may not have values eg. days before DB started getting populated
        # As time progresses this should be less of an issue
        locked_tokens_dict = OrderedDict()
        for r in results:
            locked_stake = r['sum']
            # Dash accepts datetime objects for graphs
            locked_tokens_dict[MayaDT.from_rfc3339(r['time']).datetime()] = locked_stake if locked_stake else 0

        return locked_tokens_dict

    def get_historical_num_stakers_over_range(self, days: int):
        range_begin, range_end = self._get_range_bookends(days)
        results = list(self._client.query(f"SELECT COUNT(staker_address) FROM "
                                          f"("
                                            f"SELECT staker_address, LAST(locked_stake)"
                                            f"FROM {Crawler.NODE_MEASUREMENT} WHERE "
                                            f"time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
                                            f"time < '{MayaDT.from_datetime(range_end).rfc3339()}' "
                                            f"GROUP BY staker_address, time(1d)"
                                          f") "
                                          "GROUP BY time(1d)").get_points())   # 1 day measurements

        # Note: all days may not have values eg. days before DB started getting populated
        # As time progresses this should be less of an issue
        num_stakers_dict = OrderedDict()
        for r in results:
            locked_stake = r['count']
            # Dash accepts datetime objects for graphs
            num_stakers_dict[MayaDT.from_rfc3339(r['time']).datetime()] = locked_stake if locked_stake else 0

        return num_stakers_dict

    def get_historical_work_orders_over_range(self, days: int):
        range_begin, range_end = self._get_range_bookends(days)
        results = list(self._client.query(f"SELECT SUM(work_orders) FROM "
                                          f"("
                                            f"SELECT staker_address, LAST(work_orders)"
                                            f"FROM {Crawler.NODE_MEASUREMENT} WHERE "
                                            f"time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
                                            f"time < '{MayaDT.from_datetime(range_end).rfc3339()}' "
                                            f"GROUP BY staker_address, time(1d)"
                                          f") "
                                          "GROUP BY time(1d)").get_points())   # 1 day measurements
        work_orders_dict = OrderedDict()
        for r in results:
            num_work_orders = r['sum']
            work_orders_dict[MayaDT.from_rfc3339(r['time']).datetime()] = num_work_orders if num_work_orders else 0

        return work_orders_dict

    def get_historical_events(self, days: int) -> List:
        range_begin, range_end = self._get_range_bookends(days)
        results = list(self._client.query(f"SELECT * FROM {Crawler.EVENT_MEASUREMENT} WHERE "
                                          f"time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
                                          f"time < '{MayaDT.from_datetime(range_end).rfc3339()}' "
                                          f"ORDER BY time DESC").get_points())  # decreasing order
        return results

    def close(self):
        self._client.close()

    @staticmethod
    def _get_range_bookends(days: int):
        today = datetime.utcnow()
        range_end = datetime(year=today.year, month=today.month, day=today.day,
                             hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)  # include today
        range_begin = range_end - timedelta(days=days)

        return range_begin, range_end
