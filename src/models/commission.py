# -*- coding: utf-8 -*-
"""WB佣金数据模型"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Commission:
    """WB佣金数据模型（DEPRECATED — 旧单表架构，保留向后兼容）"""
    id: Optional[int] = None
    category: str = ""    # 品类
    product: str = ""     # 商品
    rate: float = 0.0     # 佣金率%
    source: str = "wb_fbs"  # 来源
    platform: str = "wb"  # 平台: wb, ozon, market
    shop_type: str = "local"  # 店铺类型: local, cross_border


@dataclass
class CommissionTableInfo:
    """动态佣金表元数据"""
    table_name: str         # e.g. "commission_wb_local"
    platform: str           # "wb", "ozon", "market"
    shop_type: str          # "local", "cross_border"
    source_file: str        # 原始Excel文件名
    column_headers: str     # JSON数组: ["品类", "商品", "WB仓库，%", ...]
    rate_columns: str       # JSON数组: ["rate_col_0", "rate_col_1", ...]
    row_count: int
    imported_at: str        # ISO时间戳
