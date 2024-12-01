from typing import Dict, Optional
import logging
from datetime import datetime
import threading
import pickledb
from telebot.types import User
from pathlib import Path

logger = logging.getLogger(__name__)

class StatisticsManager:
    def __init__(self, db_file: str = 'data/statistics.json'):
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = pickledb.load(db_file, auto_dump=True)
        
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
    
    def get_statistics(self) -> Dict:
        """Get current statistics"""
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
                for user_id, data in users.items()
            ]
            
            # Sort by total requests and add time info to display
            top_users = sorted(top_users, key=lambda x: x['total_requests'], reverse=True)[:10]
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
                for chat_id, data in chats.items()
            ]
            top_chats = sorted(top_chats, key=lambda x: x['requests'], reverse=True)[:10]

            # Return statistics dictionary
            return {
                'total_requests': self._db.get('total_requests'),
                'total_inline_requests': self._db.get('total_inline_requests'),
                'unique_users': len(users),
                'unique_chats': len(chats),
                'top_users': top_users,
                'top_chats': top_chats
            }
