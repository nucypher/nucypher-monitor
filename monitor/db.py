import os
import sqlite3
from collections import OrderedDict
from typing import Dict, List

from maya import MayaDT
from monitor.crawler import CrawlerStorage
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
