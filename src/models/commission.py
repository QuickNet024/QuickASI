# -*- coding: utf-8 -*-
"""WB佣金数据模型"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Commission:
    """WB佣金数据模型"""
    id: Optional[int] = None
    category: str = ""    # 品类
    product: str = ""     # 商品
    rate: float = 0.0     # 佣金率%
    source: str = "wb_fbs"  # 来源
    platform: str = "wb"  # 平台: wb, ozon, market
    shop_type: str = "local"  # 店铺类型: local, cross_border
