# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

from typing import Dict, Optional
import logging
from datetime import datetime
import threading
import time
import os

import requests
from telebot.types import User

from src.settings import settings
from src.storage import KeyValueStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


# Stand-in for a timestamp we could not read. Old enough to sort such entries to the
# bottom of every "recently active" list without dropping the entry itself.
UNKNOWN_TIMESTAMP = datetime(2000, 1, 1)

# How long close() waits for the reporting thread. The thread parks on the stop event
# between reports, so this only matters when it is inside an HTTP request (capped at
# 10 seconds by the request timeout below).
#
# Deliberately short: close() runs from bot.shutdown_managers(), i.e. from inside the
# SIGTERM handler, and docker's stop_grace_period covers the WHOLE shutdown. Waiting
# out a stalled POST here would spend the time the sqlite close needs and let SIGKILL
# land in the middle of it. The thread is a daemon and dies with the process anyway.
REPORTING_STOP_TIMEOUT = 2


def _parse_timestamp(value, field: str) -> datetime:
    """Read a stored ISO timestamp, tolerating anything that is not one.

    These strings come out of a JSON blob that outlives restarts and went through the
    pickleDB import, so one truncated or hand-edited value used to raise straight out
    of get_statistics — taking down /stats AND every iteration of the InfluxDB
    reporting loop for as long as the bad row stayed in the database.
    """
    if value is None:
        return UNKNOWN_TIMESTAMP
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    # The value itself is not logged: it is user-adjacent stored data.
    logger.warning(f"Unreadable '{field}' timestamp in statistics, falling back to {UNKNOWN_TIMESTAMP.date()}")
    return UNKNOWN_TIMESTAMP


class StatisticsManager:
    def __init__(self, db_file: str = settings.statistics_db_path):
        # This lock is NOT redundant now that KeyValueStore has one of its own.
        # The store makes each individual statement atomic; this lock makes the
        # read-modify-write sequences atomic (log_request reads 'users', mutates
        # the dict in Python and writes it back — two concurrent handlers without
        # this lock would silently lose one of the increments).
        # No deadlock risk: the order is always manager lock -> store lock, never
        # the reverse. The store never calls back into the manager, and the store
        # lock is released before each store method returns.
        self._lock = threading.Lock()
        self._db = KeyValueStore(db_file)

        # Initialize InfluxDB attributes
        self._influx_configured = False
        self._influx_params = None
        self._reporting_thread = None
        # An Event, not a flag: the reporting thread waits on it instead of sleeping,
        # so close() stops it at once instead of leaving it parked for a whole period.
        self._stop_reporting = threading.Event()
        self._influx_topic = None
        self._reporting_period = 300

        # No counter seeding here on purpose. Every read below already supplies its
        # own default ("total_requests", 0 / get('users') or {}), so writing zeroes
        # at startup bought nothing — and it actively broke recovery: KeyValueStore
        # decides whether to import the legacy JSON by looking at whether the table
        # is empty, and these five rows made it non-empty on the very first start.
        # A first start that failed to import (broken JSON) would then never retry.

        logger.info("Statistics manager initialized")
        self._initialize_influx()

    def _initialize_influx(self):
        # Initialize InfluxDB reporting
        self._influx_configured = False
        self._influx_params = None
        self._reporting_thread = None
        self._stop_reporting.clear()

        # Try to configure InfluxDB from settings
        influx_version = settings.influx_version
        if not influx_version:
            logger.info("INFLUX_VERSION not set, metrics reporting disabled")
            return
        else:
            logger.info(f"Influx version: {influx_version}")

        influx_topic = settings.influx_topic
        if not influx_topic:
            logger.error("INFLUX_TOPIC not set, metrics reporting disabled")
            return
        else:
            logger.info(f"Influx topic: {influx_topic}")
            self._influx_topic = str(influx_topic)  # Save as class attribute

        # Reporting period (default 300 seconds = 5 minutes). No int()/ValueError
        # handling here: pydantic already parsed it and a garbage value fails at
        # startup with a readable message.
        self._reporting_period = settings.influx_reporting_period
        if self._reporting_period < 100:  # Prevent too frequent reporting
            logger.warning("INFLUX_REPORTING_PERIOD too low, setting to 100 seconds minimum")
            self._reporting_period = 100
        logger.info(f"Influx reporting period: {self._reporting_period} seconds")

        influx_url = settings.influx_url
        if influx_version == '2':
            influx_token = settings.influx_token
            influx_org = settings.influx_org
            influx_bucket = settings.influx_bucket
            
            if all([influx_url, influx_token, influx_org, influx_bucket]):
                logger.info(f"Influx url: {influx_url}")
                logger.info(f"Influx org: {influx_org}")
                logger.info(f"Influx bucket: {influx_bucket}")
                self.configure_metrics_v2( str(influx_url), str(influx_token), str(influx_org), str(influx_bucket))
            else:
                logger.error("Missing required InfluxDB v2 configuration parameters")
        elif influx_version == '1.8':
            influx_db = settings.influx_db
            influx_user = settings.influx_user
            influx_password = settings.influx_password
            
            if all([influx_url, influx_db, influx_user, influx_password]):
                logger.info(f"Influx url: {influx_url}")
                logger.info(f"Influx db: {influx_db}")
                logger.info(f"Influx user: {influx_user}")
                self.configure_metrics_v1(str(influx_url), str(influx_db), str(influx_user), str(influx_password))

            else:
                logger.error("Missing required InfluxDB v1.8 configuration parameters")
        else:
            logger.error(f"Unsupported INFLUX_VERSION: {influx_version}. Must be '2' or '1.8'")
        

    def log_request(self, user: User, chat_id: Optional[int], chat_title: Optional[str], is_inline: bool = False) -> None:
        """Log a request from user in specific chat"""
        with self._lock:
            try:
                # Everything this request changes is collected here and written
                # as ONE transaction at the end. With pickledb every set() dumped
                # the whole file (twice, from two threads), so a single message
                # meant up to ten full rewrites of a file that grows with the
                # user count — all of it while holding this lock.
                updates: Dict = {}

                # Update total requests
                if is_inline:
                    total_inline = self._db.get('total_inline_requests', 0)
                    updates['total_inline_requests'] = total_inline + 1
                else:
                    total = self._db.get('total_requests', 0)
                    updates['total_requests'] = total + 1

                # Update user statistics
                if user.id:
                    users = self._db.get('users') or {}
                    user_id_str = str(user.id)
                    current_time = datetime.now().isoformat()
                    
                    if user_id_str not in users:
                        users[user_id_str] = {
                            'username': user.username,
                            'first_name': user.first_name,
                            'requests': 0,
                            'inline_requests': 0,
                            'first_seen': current_time,
                            'last_active': current_time
                        }
                    
                    if is_inline:
                        users[user_id_str]['inline_requests'] = users[user_id_str].get('inline_requests', 0) + 1
                    else:
                        users[user_id_str]['requests'] += 1
                    
                    # Update last active timestamp
                    users[user_id_str]['last_active'] = current_time
                    
                    if user.username:  # Update username if available
                        users[user_id_str]['username'] = user.username
                    if user.first_name:  # Update first_name if available
                        users[user_id_str]['first_name'] = user.first_name

                    updates['users'] = users

                # Update chat statistics
                if chat_id and chat_id != user.id:  # Don't log private chats as separate entries
                    chats = self._db.get('chats') or {}
                    chat_id_str = str(chat_id)
                    
                    if chat_id_str not in chats:
                        chats[chat_id_str] = {
                            'title': chat_title or 'Unknown',
                            'requests': 0,
                            'first_seen': datetime.now().isoformat()
                        }
                    
                    chats[chat_id_str]['requests'] += 1
                    if chat_title:  # Update chat title if available
                        chats[chat_id_str]['title'] = chat_title

                    updates['chats'] = chats

                # Update last update timestamp
                updates['last_update'] = datetime.now().isoformat()

                self._db.set_many(updates)

            except Exception as e:
                logger.error(f"Failed to log request: {e}")
    
    def get_statistics(self, stat_limit: int) -> Dict:
        """Get current statistics

        Args:
            stat_limit: Number of users and chats to return in top list.
        """
        with self._lock:
            users = self._db.get('users') or {}
            chats = self._db.get('chats') or {}
            
            # Prepare top users list with combined and separate stats
            top_users = [
                {
                    'display_name': data.get('first_name') or 'Unknown User',
                    'username': data.get('username'),
                    'requests': data['requests'],
                    'inline_requests': data.get('inline_requests', 0),
                    'total_requests': data['requests'] + data.get('inline_requests', 0),
                    'last_active': _parse_timestamp(data.get('last_active'), 'last_active'),
                    'first_seen': _parse_timestamp(data.get('first_seen'), 'first_seen')
                }
                for _user_id, data in users.items()
            ]
            
            # Sort by total requests and add time info to display
            if stat_limit > 0:
                top_users = sorted(top_users, key=lambda x: x['total_requests'], reverse=True)[:stat_limit]
            else:
                top_users = sorted(top_users, key=lambda x: x['total_requests'], reverse=True)

            for user in top_users:
                last_active_delta = datetime.now() - user['last_active']
                if last_active_delta.days > 0:
                    user['last_active_str'] = f"{last_active_delta.days}д назад"
                elif last_active_delta.seconds // 3600 > 0:
                    user['last_active_str'] = f"{last_active_delta.seconds // 3600}ч назад"
                else:
                    user['last_active_str'] = f"{last_active_delta.seconds // 60}м назад"

            # Prepare top chats list 
            top_chats = [
                {
                    'title': data['title'],
                    'requests': data['requests']
                }
                for _chat_id, data in chats.items()
            ]
            # Same "anything but a positive limit means all of them" rule as top_users
            # above: the metrics thread asks for stat_limit=-1, and a bare [:-1]
            # silently dropped the last chat from what it reported.
            top_chats = sorted(top_chats, key=lambda x: x['requests'], reverse=True)
            if stat_limit > 0:
                top_chats = top_chats[:stat_limit]

            # Return statistics dictionary
            return {
                'total_requests': self._db.get('total_requests', 0),
                'total_inline_requests': self._db.get('total_inline_requests', 0),
                'unique_users': len(users),
                'unique_chats': len(chats),
                'top_users': top_users,
                'top_chats': top_chats
            }
    
    def configure_metrics_v2(self, influx_url: str, influx_token: str, influx_org: str, influx_bucket: str):
        """Configure InfluxDB 2.x metrics reporting"""
        self._influx_params = {
            "url": f"{influx_url}/api/v2/write",
            "params": {
                "org": influx_org,
                "bucket": influx_bucket,
                "precision": "s"
            },
            "headers": {
                "Authorization": f"Token {influx_token}",
                "Content-Type": "text/plain; charset=utf-8"
            }
        }
        self._start_reporting()

    def configure_metrics_v1(self, influx_url: str, influx_db: str, influx_user: str, influx_password: str):
        """Configure InfluxDB 1.8 metrics reporting"""
        self._influx_params = {
            "url": f"{influx_url}/write",
            "params": {
                "db": influx_db,
                "precision": "s"
            },
            "auth": (influx_user, influx_password),
            "headers": {
                "Content-Type": "text/plain; charset=utf-8"
            }
        }
        self._start_reporting()

    def _start_reporting(self):
        """Start metrics reporting thread"""
        self._influx_configured = True
        if self._reporting_thread is None:
            self._reporting_thread = threading.Thread(target=self._report_metrics)
            self._reporting_thread.daemon = True
            self._reporting_thread.start()
            #logger.info("Metrics reporting thread started")

    def _report_metrics(self):
        """Report metrics to InfluxDB periodically"""
        logger.info("Starting metrics reporting thread")
        while not self._stop_reporting.is_set():
            try:

                if not self._influx_configured or not self._influx_params:
                    self._stop_reporting.wait(self._reporting_period)
                    logger.info(f"Waiting for InfluxDB to be configured... (period: {self._reporting_period}s)")
                    continue
                
                logger.info("[Influx] Getting statistics")
                stats = self.get_statistics(stat_limit=-1)
                timestamp = int(time.time())
                
                line = f"{self._influx_topic} total_requests={stats['total_requests']}i,total_inline_requests={stats['total_inline_requests']}i,unique_users={stats['unique_users']}i,unique_chats={stats['unique_chats']}i {timestamp}"
                
                kwargs = {
                    "url": self._influx_params["url"],
                    "params": self._influx_params["params"],
                    "headers": self._influx_params["headers"],
                    "data": line,
                    "timeout": 10
                }
                
                # Add auth for v1.8 if present
                if "auth" in self._influx_params:
                    kwargs["auth"] = self._influx_params["auth"]
                
                response = requests.post(**kwargs)
                
                if response.status_code == 204:
                    logger.info(f"Successfully reported metrics to InfluxDB (period: {self._reporting_period}s)")
                else:
                    logger.error(f"Failed to report metrics to InfluxDB. Status: {response.status_code}, Response: {response.text}")
                    
            except Exception as e:
                logger.error(f"Error reporting metrics to InfluxDB: {str(e)}")

            self._stop_reporting.wait(self._reporting_period)

    def close(self) -> None:
        """Stop reporting and close the store. Public on purpose — see bot.shutdown_managers.

        The stop event is set BEFORE the connection goes away: _report_metrics reads
        the database (get_statistics) and posts first, waiting only afterwards, so a
        connection closed under it raises "Cannot operate on a closed database". The
        broad except in that loop keeps it harmless, but it would still print an
        ERROR on every clean shutdown. Joining the thread first closes even that gap
        in the normal case.

        This is the ONLY way the reporting thread is stopped. There used to be a
        __del__ doing it as well, which is not a mechanism to rely on: it may never
        run (a reference cycle, or interpreter exit), and when it does run during
        shutdown the module globals it touches may already be gone. Safe to call more
        than once — the signal path calls it and main()'s finally calls it again.
        """
        self._stop_reporting.set()
        thread = self._reporting_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=REPORTING_STOP_TIMEOUT)
        self._db.close()
