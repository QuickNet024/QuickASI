# -*- coding: utf-8 -*-
"""产品匹配服务 - 将卖家SKU匹配到飞书产品"""

import re
import logging
from typing import Optional, Tuple, List

from src.models.database import DatabaseManager
from src.config import Config
from src.models.product import Product

logger = logging.getLogger(__name__)


class ProductMatcher:
    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager(Config.DB_FEISHU_PATH, init_tables=["products"])
        self._all_products = None   # 缓存
        self._sku_index = {}        # {sku_code: Product} 精确匹配
        self._prefix_index = {}     # {sheet_prefix: [Product]} 前缀匹配

    def preload_all(self):
        """一次性加载所有产品到内存，构建查找索引。消除逐行DB查询。"""
        if self._all_products is not None:
            return
        self._all_products = self.db.get_all_products()
        self._sku_index = {}
        self._prefix_index = {}
        for p in self._all_products:
            # Normalize: strip spaces from sku_code for matching
            normalized = p.sku_code.replace(" ", "")
            p.sku_code = normalized
            self._sku_index[normalized] = p
            if p.sheet_name and "-" in p.sheet_name:
                prefix = p.sheet_name.split("-")[-1]
                self._prefix_index.setdefault(prefix, []).append(p)

    @staticmethod
    def parse_seller_sku(seller_sku: str) -> Tuple[str, str]:
        """Parse seller SKU like "3C5-YX-JC-530-白" → ("3C5", "3C5-YX-JC-530-白")
        1. Split by "-" → first segment = sheet prefix
        2. If last segment matches F{digits}, remove it → SKU-货号
        3. Strip all internal spaces for robust matching
        """
        if not seller_sku:
            return "", ""
        seller_sku = seller_sku.strip()
        parts = [p.strip() for p in seller_sku.split("-")]
        sheet_prefix = parts[0]
        # Remove last -F{N} or -修改{N} suffix
        while len(parts) > 1 and (re.match(r'^F\d+$', parts[-1]) or re.match(r'^修改\d+$', parts[-1])):
            parts = parts[:-1]
        sku_code = "-".join(parts)
        # Remove ALL spaces for matching
        sku_code = sku_code.replace(" ", "")
        return sheet_prefix, sku_code

    def match_product(self, seller_sku: str) -> Optional[Product]:
        """Match a seller SKU — uses preloaded memory index if available, falls back to DB."""
        sheet_prefix, sku_code = self.parse_seller_sku(seller_sku)
        if not sheet_prefix:
            return None

        # 内存查找路径（preload 后使用）
        if self._all_products is not None:
            # 精确匹配
            if sku_code in self._sku_index:
                return self._sku_index[sku_code]
            # 前缀范围匹配
            candidates = self._prefix_index.get(sheet_prefix, [])
            for p in candidates:
                if p.sku_code == sku_code:
                    return p
            # Fuzzy: check if core product name (without prefix) is a substring
            # More specific than generic substring, so try first
            prefix_sep = sheet_prefix + "-"
            if sku_code.startswith(prefix_sep):
                seller_core = sku_code[len(prefix_sep):]
                if seller_core:
                    for p in candidates:
                        if seller_core in p.sku_code:
                            return p
            for p in candidates:
                if sku_code in p.sku_code or p.sku_code in sku_code:
                    return p
            return None

        # 回退: DB查询（未preload时）
        candidates = self.db.get_products_by_sheet_prefix(sheet_prefix)
        for p in candidates:
            if p.sku_code.replace(" ", "") == sku_code:
                return p
        # Fuzzy: core-name containment (more specific, try first)
        prefix_sep = sheet_prefix + "-"
        if sku_code.startswith(prefix_sep):
            seller_core = sku_code[len(prefix_sep):]
            if seller_core:
                for p in candidates:
                    p_norm = p.sku_code.replace(" ", "")
                    if seller_core in p_norm:
                        return p
        for p in candidates:
            p_norm = p.sku_code.replace(" ", "")
            if sku_code in p_norm or p_norm in sku_code:
                return p
        return None

    def match_batch(self, seller_skus: List[str]) -> dict:
        """Match multiple SKUs. Returns {sku: Product or None}"""
        results = {}
        for sku in seller_skus:
            results[sku] = self.match_product(sku)
        return results
