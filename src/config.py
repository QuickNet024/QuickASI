# -*- coding: utf-8 -*-
"""
WB亏损计算系统 - 配置模块
"""


class Config:
    """全局配置参数"""

    # ── 飞书API配置 ──
    FEISHU_APP_ID = "cli_a900afabcc38dcc7"
    FEISHU_APP_SECRET = "HInGDbnLXtmW3U2MrADDmdsvbk7pRtGL"
    FEISHU_SPREADSHEET_TOKEN = "HUWasGeIXhWGXitg320cEg5snyc"
    FEISHU_EXCLUDE_SHEETS = ["货盘公告", "汇率"]

    # ── 汇率API ──
    EXCHANGE_RATE_API_KEY = "81a7d8d9d546ae6edb4546c1"
    EXCHANGE_RATE_API_URL = "https://v6.exchangerate-api.com/v6/{key}/latest/USD"

    # ── 计算参数默认值 (来自index.html) ──
    DEFAULT_PARAMS = {
        "risk_rate": 1.00,           # 汇率风险系数
        "dropship_fee": 10.0,        # 代发费 (RUB)
        "pack_fee": 0.0,             # 包装费 (RUB)
        "scan_fee": 1.0,             # 平台扫码费 (RUB)
        "return_process_fee": 10.0,  # 退货处理费 (RUB)
        "residual_loss_rate": 15.0,  # 退货残值损失率 (%)
        "damage_rate": 2.0,          # 货损率 (%)
        "return_rate": 15.0,         # 退货率 (%)
        "commission_rate": 10.0,     # 平台佣金率 (%)
        "commission_discount": 0.0,  # 佣金优惠减免率 (%)
        "withdraw_fee": 1.0,         # 提现手续费 (%)
        "ad_fixed": 0.0,             # 广告固定支出
        "ad_percent": 2.5,           # 广告费率ACOS (%)
        "ops_rate": 3.0,             # 运营成本率 (%)
        "member_disc": 3.0,          # 会员折扣率 (%)
        "target_profit_rate": 10.0,  # 目标利润率 (%)
        "default_commission": 30.0,  # 默认佣金率(未匹配时) (%)
    }

    # ── 默认计算参数 (when matching fails) ──
    DEFAULT_DIMENSIONS = "30*20*10"      # Default dimensions string
    DEFAULT_WEIGHT = 0.5                 # Default weight in kg
    DEFAULT_COMMISSION_RATE = 30.0       # Default commission rate (%)

    # ── 计算模式 ──
    CALC_MODE_CROSS_BORDER = "cross_border"  # 跨境店铺 CNY
    CALC_MODE_LOCAL = "local"                 # 本土店铺 RUB

    # ── WB平台约束 ──
    DISCOUNT_MIN = 0
    DISCOUNT_MAX = 95
    PRICE_MIN = 5
    PRICE_MAX = 850000

    # ── 数据库（独立数据库） ──
    DB_DIR = "data"
    DB_APP_PATH = "data/app.db"
    DB_FEISHU_PATH = "data/feishu.db"
    DB_COMMISSION_PATH = "data/commission.db"
    DB_EXCHANGE_RATE_PATH = "data/exchange_rate.db"
    DB_DISCOUNT_CALC_PATH = "data/discount_calc.db"
    DB_SHIPPING_PATH = "data/shipping.db"
    # 旧路径（仅迁移参考，不再使用）
    DB_PATH = "data/loss_calc.db"
