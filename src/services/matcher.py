# -*- coding: utf-8 -*-
"""产品匹配服务 - 将卖家SKU匹配到飞书产品"""

import re
import logging
from typing import Optional, Tuple, List

from src.models.database import DatabaseManager
from src.models.product import Product

logger = logging.getLogger(__name__)


class ProductMatcher:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    @staticmethod
    def parse_seller_sku(seller_sku: str) -> Tuple[str, str]:
        """Parse seller SKU like "3C5-YX-JC-530-白-F4" → ("3C5", "3C5-YX-JC-530-白")
        1. Split by "-" → first segment = sheet prefix
        2. If last segment matches F{digits}, remove it → SKU-货号
        """
        if not seller_sku:
            return "", ""
        seller_sku = seller_sku.strip()
        parts = [p.strip() for p in seller_sku.split("-")]
        sheet_prefix = parts[0]
        # Remove last -F{N} segment
        if len(parts) > 1 and re.match(r'^F\d+$', parts[-1]):
            sku_code = "-".join(parts[:-1])
        else:
            sku_code = seller_sku
        return sheet_prefix, sku_code

    def match_product(self, seller_sku: str) -> Optional[Product]:
        """Match a seller SKU from uploaded Excel to a Feishu product.
        Returns the matched Product or None."""
        sheet_prefix, sku_code = self.parse_seller_sku(seller_sku)
        if not sheet_prefix:
            return None

        # Find products from sheets containing this prefix
        candidates = self.db.get_products_by_sheet_prefix(sheet_prefix)

        # Exact match on sku_code
        for p in candidates:
            if p.sku_code == sku_code:
                return p

        # Try partial match (sku_code contains or is contained)
        for p in candidates:
            if sku_code in p.sku_code or p.sku_code in sku_code:
                return p

        return None

    def match_batch(self, seller_skus: List[str]) -> dict:
        """Match multiple SKUs. Returns {sku: Product or None}"""
        results = {}
        for sku in seller_skus:
            results[sku] = self.match_product(sku)
        return results
