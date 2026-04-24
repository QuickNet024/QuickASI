# -*- coding: utf-8 -*-
"""独立运费服务 — 配置持久化到 shipping.db"""

import math
import logging
from typing import Optional
from src.models.database import DatabaseManager
from src.config import Config

logger = logging.getLogger(__name__)

# Default shipping configs
_DEFAULTS = {
    "wb_cross_border": {"base_fee": 8.0, "rate_per_unit": 2.0, "ceil_volume": True},
    "wb_local": {"base_fee": 32.0, "rate_per_unit": 14.0, "ceil_volume": True},
}


class ShippingService:
    """独立运费服务 — 配置持久化到 shipping.db"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager(Config.DB_SHIPPING_PATH, init_tables=["app_config"])

    def calc_fee(self, l: float, w: float, h: float, shop_type: str = "wb_cross_border") -> float:
        """Calculate shipping fee based on dimensions and shop type.

        Args:
            l, w, h: dimensions in cm
            shop_type: "wb_cross_border" or "wb_local"
        Returns:
            Shipping fee in the shop's currency (¥ for cross_border, ₽ for local)
        """
        volume_l = l * w * h / 1000  # Volume in liters

        if shop_type == "wb_local":
            # WB本土: ≤1L fixed 32₽, >1L = 46 + (ceil(vol)-1)×14
            if volume_l <= 1:
                return 32.0
            v = math.ceil(volume_l)
            return 46 + (v - 1) * 14

        # WB跨境 (default): 首升base_fee + (ceil(vol)-1)×rate
        config = self.get_config(shop_type)
        v = math.ceil(volume_l) if config["ceil_volume"] else volume_l
        return config["base_fee"] + max(0, v - 1) * config["rate_per_unit"]

    def calc_fee_with_config(self, l: float, w: float, h: float, shop_type: str = "wb_cross_border") -> tuple:
        """Calculate shipping fee and return (fee, shop_type, currency).

        Returns:
            (shipping_fee: float, shop_type: str, currency: str)
        """
        fee = self.calc_fee(l, w, h, shop_type)
        currency = "RUB" if shop_type == "wb_local" else "CNY"
        return (fee, shop_type, currency)

    def get_config(self, shop_type: str = "wb_cross_border") -> dict:
        """Get shipping config for a shop type from DB, with defaults."""
        defaults = _DEFAULTS.get(shop_type, _DEFAULTS["wb_cross_border"])
        try:
            saved = self.db.get_all_config()
            result = dict(defaults)
            for key in result:
                db_key = f"shipping_{shop_type}_{key}"
                if db_key in saved:
                    try:
                        val = saved[db_key]
                        if key == "ceil_volume":
                            result[key] = val.lower() == "true" if isinstance(val, str) else bool(val)
                        else:
                            result[key] = float(val)
                    except (ValueError, TypeError):
                        pass
            return result
        except Exception:
            return dict(defaults)

    def save_config(self, shop_type: str, base_fee: float, rate_per_unit: float, ceil_volume: bool = True):
        """Save shipping config for a shop type to DB."""
        self.db.save_config(f"shipping_{shop_type}_base_fee", str(base_fee))
        self.db.save_config(f"shipping_{shop_type}_rate_per_unit", str(rate_per_unit))
        self.db.save_config(f"shipping_{shop_type}_ceil_volume", str(ceil_volume))
        logger.info(f"Shipping config saved for {shop_type}: base={base_fee}, rate={rate_per_unit}")

    def get_currency(self, shop_type: str) -> str:
        """Get currency for a shop type."""
        return "RUB" if shop_type == "wb_local" else "CNY"

    @staticmethod
    def detect_shop_type(commission_table: str) -> str:
        """Detect shop type from commission table name."""
        if "local" in (commission_table or ""):
            return "wb_local"
        return "wb_cross_border"
