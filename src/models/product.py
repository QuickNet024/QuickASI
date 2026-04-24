# -*- coding: utf-8 -*-
"""飞书产品数据模型"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Product:
    """飞书产品数据模型"""
    id: Optional[int] = None
    sku_code: str = ""           # SKU-货号
    sheet_name: str = ""         # 来源sheet名
    distribution_price: float = 0.0  # 分销价格 (RUB)
    dimensions: str = ""         # 长*宽*高(cm) 如 "51*14*5"
    weight: float = 0.0          # 包装重量
    category: str = ""           # 类目
    chinese_name: str = ""       # 中文名称
    brand: str = ""              # 品牌
    inventory: int = 0           # 库存数量
    inventory_status: str = ""   # 库存状态(货源充足/货源紧缺/停止上架)
    synced_at: Optional[datetime] = None
    # New fields (appended — positional indexing in DB)
    image_file_token: str = ""
    image_local_path: str = ""
    original_price: float = 0.0
    supplier: str = ""
    remarks: str = ""
    # V2: 原始同步数据（JSON，存飞书行的完整原始值）
    raw_sync_data: str = ""
