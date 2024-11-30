from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import logging
import threading
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

class ExchangeRatesManager:
    def __init__(self, cache_file: str = 'exchange_rates_cache.json'):
        self._cache_file = Path(cache_file)
        self._rates: Dict = {}
        self._last_update: Optional[datetime] = None
        self._lock = threading.Lock()
        self._currencies: List[str] = [] 
        
        self._initialize_rates()
        self._start_update_thread()
    
    def _initialize_rates(self) -> None:
        """Initialize rates from cache file or download new ones"""
        if self._load_cache():
            time_diff = datetime.now() - self._last_update
            if time_diff > timedelta(hours=2):
                logger.info("Cached rates are too old, updating...")
                self._update_all_rates()
        else:
            logger.info("No valid cache found, downloading rates...")
            self._update_all_rates()
    
    def _load_cache(self) -> bool:
        """Load rates from cache file"""
        try:
            if not self._cache_file.exists():
                return False
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._rates = data['rates']
            self._last_update = datetime.fromisoformat(data['last_update'])
            logger.info(f"Loaded rates from cache, last update: {self._last_update}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load rates cache: {str(e)}")
            return False
    
    def _save_cache(self) -> None:
        """Save current rates to cache file"""
        try:
            data = { 'rates': self._rates, 'last_update': self._last_update.isoformat() }
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info("Rates cache saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save rates cache: {str(e)}")
    
    def _update_thread(self) -> None:
        """Background thread for periodic rates updates"""
        while True:
            time.sleep(12 * 60 * 60)  # Sleep for 5 hours
            self._update_all_rates()
    
    def _start_update_thread(self) -> None:
        """Start background update thread"""
        thread = threading.Thread(target=self._update_thread, daemon=True)
        thread.start()
        logger.info("Started rates update thread")
    
    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get exchange rate for currency pair"""
        with self._lock:
            try:
                return self._rates[from_currency][to_currency]
            except KeyError:
                logger.error(f"Rate not found for {from_currency}->{to_currency}")
                return None
    
    def _update_all_rates(self) -> None:
        """Update rates for all currencies"""
        logger.info("Starting full rates update")
        new_rates = {}
        
        try:
            url = "https://api.apilayer.com/currency_data/live"
            headers = {"apikey": os.getenv('API_KEY')}
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if not result.get('success'):
                logger.error(f"API request failed. Response: {result}")
                return
            
            # Get all currencies from API response
            usd_rates = {'USD': 1.0}  # Add base USD currency
            for key, value in result['quotes'].items():
                currency = key[3:]  # Remove 'USD' prefix from key
                usd_rates[currency] = value
            
            # Update list of available currencies
            self._currencies = list(usd_rates.keys())
            
            # Calculate cross-rates for ALL currencies
            for base in self._currencies:
                base_in_usd = 1.0 / usd_rates[base]
                rates = {}
                
                for target in self._currencies:
                    if target != base:
                        target_rate = usd_rates[target]
                        rates[target] = target_rate * base_in_usd
                
                new_rates[base] = rates
            
            with self._lock:
                self._rates = new_rates
                self._last_update = datetime.now()
                self._save_cache()
                logger.info(f"Successfully updated rates for {len(self._currencies)} currencies")
                
        except Exception as e:
            logger.error(f"Failed to update rates: {str(e)}")
    
    def get_available_currencies(self) -> List[str]:
        """Get list of all available currencies"""
        with self._lock:
            return self._currencies.copy() 