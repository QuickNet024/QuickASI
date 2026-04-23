# -*- coding: utf-8 -*-
"""汇率服务 - 从API获取并缓存汇率"""

import requests
import logging
from typing import Optional, Dict
from datetime import datetime

from src.config import Config
from src.models.database import DatabaseManager

logger = logging.getLogger(__name__)


class ExchangeRateService:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()
        self.api_key = Config.EXCHANGE_RATE_API_KEY
        self.api_url = Config.EXCHANGE_RATE_API_URL.format(key=self.api_key)

    def fetch_and_save(self) -> Optional[Dict]:
        """Fetch latest rates from API and save to DB. Returns rate dict or None."""
        try:
            resp = requests.get(self.api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("result") != "success":
                logger.error(f"Exchange rate API error: {data}")
                return None

            rates = data.get("conversion_rates", {})
            usd_to_cny = rates.get("CNY", 0)
            usd_to_rub = rates.get("RUB", 0)

            if usd_to_cny <= 0 or usd_to_rub <= 0:
                return None

            # Cross rate: 1 CNY = RUB_per_USD / CNY_per_USD RUB
            cny_to_rub = usd_to_rub / usd_to_cny
            rub_to_cny = usd_to_cny / usd_to_rub

            self.db.save_exchange_rate(cny_to_rub, rub_to_cny)
            return {"cny_to_rub": cny_to_rub, "rub_to_cny": rub_to_cny, "updated_at": datetime.now()}
        except Exception as e:
            logger.error(f"Failed to fetch exchange rate: {e}")
            return None

    def get_cached_rate(self) -> Optional[Dict]:
        """Get cached exchange rate from DB."""
        return self.db.get_exchange_rate()

    def get_cny_to_rub(self) -> float:
        """Get CNY→RUB rate, returns 0 if not available."""
        rate = self.get_cached_rate()
        return rate["cny_to_rub"] if rate else 0.0
