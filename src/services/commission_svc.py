# -*- coding: utf-8 -*-
"""WB佣金匹配服务 — 支持多平台多店铺类型"""

import openpyxl
import logging
from typing import Optional

from src.config import Config
from src.models.database import DatabaseManager
from src.models.commission import Commission

logger = logging.getLogger(__name__)


class CommissionService:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def import_from_excel(self, file_path: str,
                          platform: str = "wb",
                          shop_type: str = "local") -> int:
        """Import commission table from Excel file.
        
        Args:
            file_path: Excel文件路径
            platform: 平台标识 ('wb', 'ozon', 'market')
            shop_type: 店铺类型 ('local', 'cross_border')
        """
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        commissions = []
        for row in rows:
            if not row or len(row) < 3:
                continue
            category = str(row[0] or "").strip()
            product = str(row[1] or "").strip()
            rate_str = str(row[2] or "0").strip()
            # Handle European format "10,0" → "10.0"
            rate_str = rate_str.replace(",", ".")
            try:
                rate = float(rate_str)
            except ValueError:
                continue
            commissions.append(Commission(
                category=category, product=product, rate=rate,
                platform=platform, shop_type=shop_type,
                source=f"{platform}_{shop_type}",
            ))
        wb.close()

        self.db.clear_commissions_by_type(platform, shop_type)
        return self.db.insert_commissions_batch(commissions)

    def sync_from_api(self, platform: str = "wb",
                      shop_type: str = "local") -> int:
        """通过 API 同步佣金数据（预留接口）。

        目前为占位实现，返回 0 并提示暂不支持。
        未来可对接 WB / OZON / MARKET 的佣金 API。
        """
        logger.info(f"Commission API sync requested: {platform}/{shop_type}")
        raise NotImplementedError(
            f"佣金 API 同步暂未开放 ({platform.upper()} "
            f"{'本土' if shop_type == 'local' else '跨境'})。\n"
            f"请使用「导入佣金表」从 Excel 文件导入数据。"
        )

    def find_commission_rate(self, category_name: str,
                             platform: str = "wb",
                             shop_type: str = "local") -> tuple:
        """Find commission rate for a category. Returns (rate, matched, source).
        Priority: match 'product' column first, then 'category' column.
        Default: 30% if no match."""
        # 1. Try matching product column (filtered by platform + shop_type)
        rate = self.db.find_commission_by_product(category_name, platform, shop_type)
        if rate is not None:
            return rate, True, "product"

        # 2. Try matching category column (filtered by platform + shop_type)
        rate = self.db.find_commission_by_category(category_name, platform, shop_type)
        if rate is not None:
            return rate, True, "category"

        # 3. Default
        return Config.DEFAULT_PARAMS["default_commission"], False, "default"
