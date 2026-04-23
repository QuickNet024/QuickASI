# -*- coding: utf-8 -*-
"""数据接口模块包 — 插件式架构，每个接口独立封装"""

from src.ui.interfaces.base import InterfaceModule
from src.ui.interfaces.registry import InterfaceRegistry
from src.ui.interfaces.module_card import ModuleCard

# 导入所有模块以触发自动注册
from src.ui.interfaces.feishu_module import FeishuModule
from src.ui.interfaces.commission_module import CommissionModule
from src.ui.interfaces.exchange_rate_module import ExchangeRateModule

__all__ = [
    "InterfaceModule",
    "InterfaceRegistry",
    "ModuleCard",
    "FeishuModule",
    "CommissionModule",
    "ExchangeRateModule",
]
