# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

from typing import List, Optional
import logging
from pathlib import Path
import time
import os

import pickledb

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


class UserSettingsManager:
    def __init__(self, db_file: str = 'data/user_settings.json'):
        self._db_file = Path(db_file)
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._db = pickledb.load(str(self._db_file), auto_dump=True)
        logger.info("User settings manager initialized")

    def get_currencies(self, entity_id: int, is_chat: bool = False) -> Optional[List[str]]:
        """Get list of currencies for user or chat"""
        prefix = "chat" if is_chat else "user"
        key = f"{prefix}:{entity_id}:currencies"
        if self._db.exists(key):
            currencies = self._db.get(key)
            return list(currencies) if currencies else None
        return None

    def set_currencies(self, entity_id: int, currencies: List[str], is_chat: bool = False) -> None:
        """Set list of currencies for user or chat"""
        prefix = "chat" if is_chat else "user"
        key = f"{prefix}:{entity_id}:currencies"
        self._db.set(key, currencies)
        logger.info(f"Updated currencies for {prefix} {entity_id}: {currencies}")

    def is_chat_disabled(self, chat_id: int) -> bool:
        """Check if chat is currently disabled"""
        key = f"chat:{chat_id}:disabled_until"
        if not self._db.exists(key):
            return False
            
        disabled_until = self._db.get(key)
        if disabled_until > time.time():
            return True
            
        # Clean up expired state
        self._db.rem(key)
        return False

    def set_chat_disabled(self, chat_id: int, duration_seconds: int) -> None:
        """Set chat to be disabled for specified duration"""
        key = f"chat:{chat_id}:disabled_until"
        disabled_until = time.time() + duration_seconds
        self._db.set(key, disabled_until)
        logger.info(f"Chat {chat_id} will be disabled until {disabled_until}")
