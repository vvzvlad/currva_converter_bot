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
from pathlib import Path

import requests
import pickledb
from telebot.types import User

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


class StatisticsManager:
    def __init__(self, db_file: str = 'data/statistics.json'):
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = pickledb.load(db_file, auto_dump=True)
        
        # Initialize InfluxDB attributes
        self._influx_configured = False
        self._influx_params = None
        self._reporting_thread = None
        self._stop_reporting = False
        self._influx_topic = None
        self._reporting_period = 300
        
        # Initialize default values if DB is empty
        with self._lock:
            if not self._db.get('total_requests'):
                self._db.set('total_requests', 0)
            if not self._db.get('total_inline_requests'):
                self._db.set('total_inline_requests', 0)
            if not self._db.get('users'):
                self._db.set('users', {})
            if not self._db.get('chats'):
                self._db.set('chats', {})
            if not self._db.get('last_update'):
                self._db.set('last_update', datetime.now().isoformat())
        
        logger.info("Statistics manager initialized")
        self._initialize_influx()

    def _initialize_influx(self):
        # Initialize InfluxDB reporting
        self._influx_configured = False
        self._influx_params = None
        self._reporting_thread = None
        self._stop_reporting = False

        # Try to configure InfluxDB from environment variables
        influx_version = os.getenv('INFLUX_VERSION')
        if not influx_version:
            logger.info("INFLUX_VERSION not set, metrics reporting disabled")
            return
        else:
            logger.info(f"Influx version: {influx_version}")

        influx_topic = os.getenv('INFLUX_TOPIC')
        if not influx_topic:
            logger.error("INFLUX_TOPIC not set, metrics reporting disabled")
            return
        else:
            logger.info(f"Influx topic: {influx_topic}")
            self._influx_topic = str(influx_topic)  # Save as class attribute
            
        # Get reporting period from env (default 300 seconds = 5 minutes)
        try:
            self._reporting_period = int(os.getenv('INFLUX_REPORTING_PERIOD', '300'))
            if self._reporting_period < 10:  # Prevent too frequent reporting
                logger.warning("INFLUX_REPORTING_PERIOD too low, setting to 100 seconds minimum")
                self._reporting_period = 100
        except ValueError:
            logger.error("Invalid INFLUX_REPORTING_PERIOD value, using default 300 seconds")
            self._reporting_period = 300
        logger.info(f"Influx reporting period: {self._reporting_period} seconds")
            
        influx_url = os.getenv('INFLUX_URL')
        if influx_version == '2':
            influx_token = os.getenv('INFLUX_TOKEN')
            influx_org = os.getenv('INFLUX_ORG')
            influx_bucket = os.getenv('INFLUX_BUCKET')
            
            if all([influx_url, influx_token, influx_org, influx_bucket]):
                logger.info(f"Influx url: {influx_url}")
                logger.info(f"Influx token: {influx_token}")
                logger.info(f"Influx org: {influx_org}")
                logger.info(f"Influx bucket: {influx_bucket}")
                self.configure_metrics_v2( str(influx_url), str(influx_token), str(influx_org), str(influx_bucket))
            else:
                logger.error("Missing required InfluxDB v2 configuration parameters")
        elif influx_version == '1.8':
            influx_db = os.getenv('INFLUX_DB')
            influx_user = os.getenv('INFLUX_USER')
            influx_password = os.getenv('INFLUX_PASSWORD')
            
            if all([influx_url, influx_db, influx_user, influx_password]):
                logger.info(f"Influx url: {influx_url}")
                logger.info(f"Influx db: {influx_db}")
                logger.info(f"Influx user: {influx_user}")
                logger.info(f"Influx password: {influx_password}")
                self.configure_metrics_v1(str(influx_url), str(influx_db), str(influx_user), str(influx_password))

            else:
                logger.error("Missing required InfluxDB v1.8 configuration parameters")
        else:
            logger.error(f"Unsupported INFLUX_VERSION: {influx_version}. Must be '2' or '1.8'")
        

    def log_request(self, user: User, chat_id: Optional[int], chat_title: Optional[str], is_inline: bool = False) -> None:
        """Log a request from user in specific chat"""
        with self._lock:
            try:
                # Update total requests
                if is_inline:
                    total_inline = self._db.get('total_inline_requests')
                    self._db.set('total_inline_requests', total_inline + 1)
                else:
                    total = self._db.get('total_requests')
                    self._db.set('total_requests', total + 1)
                
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
                    
                    self._db.set('users', users)
                
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
                    
                    self._db.set('chats', chats)
                
                # Update last update timestamp
                self._db.set('last_update', datetime.now().isoformat())
                
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
                    'last_active': datetime.fromisoformat(data.get('last_active', '2000-01-01T00:00:00')),
                    'first_seen': datetime.fromisoformat(data.get('first_seen', '2000-01-01T00:00:00'))
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
            top_chats = sorted(top_chats, key=lambda x: x['requests'], reverse=True)[:stat_limit]

            # Return statistics dictionary
            return {
                'total_requests': self._db.get('total_requests'),
                'total_inline_requests': self._db.get('total_inline_requests'),
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
        while not self._stop_reporting:
            try:

                if not self._influx_configured or not self._influx_params:
                    time.sleep(self._reporting_period)
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
            
            time.sleep(self._reporting_period)

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._stop_reporting = True
        if self._reporting_thread:
            self._reporting_thread.join(timeout=1)