from typing import Dict, Optional
import logging
from datetime import datetime
import threading
import pickledb

logger = logging.getLogger(__name__)

class StatisticsManager:
    def __init__(self, db_file: str = 'data/statistics.json'):
        # Create data directory if it doesn't exist
        from pathlib import Path
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = pickledb.load(db_file, auto_dump=True)
        
        # Initialize default values if DB is empty
        with self._lock:
            if not self._db.get('total_requests'):
                self._db.set('total_requests', 0)
            if not self._db.get('users'):
                self._db.set('users', {})
            if not self._db.get('chats'):
                self._db.set('chats', {})
            if not self._db.get('last_update'):
                self._db.set('last_update', datetime.now().isoformat())
        
        logger.info("Statistics manager initialized")
    
    def log_request(self, user_id: int, username: Optional[str], first_name: Optional[str],
                    chat_id: Optional[int], chat_title: Optional[str]) -> None:
        """Log a request from user in specific chat"""
        with self._lock:
            try:
                # Update total requests
                total = self._db.get('total_requests')
                self._db.set('total_requests', total + 1)
                
                # Update user statistics
                if user_id:
                    users = self._db.get('users') or {}
                    user_id_str = str(user_id)
                    
                    if user_id_str not in users:
                        users[user_id_str] = {
                            'username': username,
                            'first_name': first_name,
                            'requests': 0,
                            'first_seen': datetime.now().isoformat()
                        }
                    
                    users[user_id_str]['requests'] += 1
                    if username:  # Update username if available
                        users[user_id_str]['username'] = username
                    if first_name:  # Update first_name if available
                        users[user_id_str]['first_name'] = first_name
                    
                    self._db.set('users', users)
                
                # Update chat statistics
                if chat_id and chat_id != user_id:  # Don't log private chats as separate entries
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
            
            # Prepare top users list
            top_users = [
                {
                    'display_name': data.get('username') or data.get('first_name') or 'Unknown User',
                    'requests': data['requests']
                }
                for user_id, data in users.items()
            ]
            top_users = sorted(top_users, key=lambda x: x['requests'], reverse=True)[:10]

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
                'unique_users': len(users),
                'unique_chats': len(chats),
                'top_users': top_users,
                'top_chats': top_chats
            }