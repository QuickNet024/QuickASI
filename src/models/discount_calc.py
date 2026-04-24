# -*- coding: utf-8 -*-
"""折扣推算数据模型"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ImportRow:
    """Excel导入的原始行数据"""
    id: Optional[int] = None
    row_number: int = 0           # Excel中的行号 (1-based)
    brand: str = ""               # A: 品牌
    category: str = ""            # B: 类目
    wb_article: str = ""          # C: WB货号
    seller_sku: str = ""          # D: 卖家货号 (匹配关键字)
    barcode: str = ""             # E: 条码
    wb_stock: str = ""            # F: WB库存
    seller_stock: str = ""        # G: 卖家库存
    turnover: str = ""            # H: 周转率
    current_price: str = ""       # I: 当前价格
    new_price: Optional[float] = None   # J: 新价格
    current_discount: Optional[int] = None  # K: 当前折扣
    new_discount: Optional[int] = None      # L: 新折扣
    import_batch: str = ""        # 导入批次ID (ISO时间戳)


@dataclass
class CalcResultRow:
    """计算结果行"""
    id: Optional[int] = None
    import_row_id: int = 0        # 关联 ImportRow.id
    # 匹配结果
    sku_matched: bool = False     # 货号是否匹配
    category_matched: bool = False # 类目是否匹配
    matched_product_id: Optional[int] = None  # 匹配到的飞书产品ID
    # 匹配到的数据
    product_cost: Optional[float] = None      # 分销价格 (RUB)
    product_category: str = ""                # 匹配到的产品类目
    dimensions: str = ""                      # 尺寸
    weight: Optional[float] = None            # 重量 (kg)
    inventory: Optional[int] = None           # 库存
    inventory_status: str = ""                # 库存状态(货源充足/停止上架/货源紧缺)
    seller_stock: str = ""                    # 卖家库存 (from import raw data)
    wb_stock: str = ""                        # 平台库存/WB库存 (from import raw data)
    commission_rate: Optional[float] = None   # 佣金率
    commission_source: str = ""               # 佣金匹配来源: "商品级"/"品类级"/"未匹配(默认30%)"
    # 计算结果
    discounted_price: Optional[float] = None  # 折后价格
    shipping_fee: Optional[float] = None      # 运费
    breakeven: Optional[float] = None         # 盈亏平衡点
    profit: Optional[float] = None            # 盈亏额
    max_discount: Optional[int] = None        # 建议最大折扣
    min_price: Optional[float] = None         # 建议最低价
    target_discount: Optional[int] = None     # 目标折扣
    target_price: Optional[float] = None      # 目标价格
    # 元数据
    calc_batch: str = ""          # 计算批次ID
