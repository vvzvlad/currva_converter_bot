from typing import Dict, List, Optional
import logging
import pickledb
from pathlib import Path

logger = logging.getLogger(__name__)

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
