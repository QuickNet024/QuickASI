# -*- coding: utf-8 -*-
"""接口模块注册中心 — 管理模块的注册/启用/禁用/持久化"""

import json
import logging
from typing import List, Optional, Dict, Type

from src.ui.interfaces.base import InterfaceModule

logger = logging.getLogger(__name__)


class InterfaceRegistry:
    """接口模块注册中心（单例模式）。
    
    负责：
    - 注册所有可用的模块类
    - 查询已启用 / 可添加的模块
    - 将启用/禁用状态持久化到数据库
    """

    _instance: Optional['InterfaceRegistry'] = None
    _modules: Dict[str, Type[InterfaceModule]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ═══ 注册 ═══════════════════════════════════

    @classmethod
    def register(cls, module_class: Type[InterfaceModule]):
        """注册一个模块类。通常在模块文件底部调用。"""
        try:
            instance = module_class()
            cls._modules[instance.module_id] = module_class
            logger.debug(f"Registered interface module: {instance.module_id} ({instance.name})")
        except Exception as e:
            logger.warning(f"Failed to register module: {e}")

    @classmethod
    def unregister(cls, module_id: str):
        """取消注册模块"""
        cls._modules.pop(module_id, None)

    # ═══ 查询 ═══════════════════════════════════

    def get_all_module_ids(self) -> List[str]:
        """返回所有已注册的模块 ID"""
        return list(self._modules.keys())

    def get_module(self, module_id: str) -> Optional[InterfaceModule]:
        """根据 ID 获取模块实例"""
        cls = self._modules.get(module_id)
        return cls() if cls else None

    def get_enabled_modules(self, db) -> List[InterfaceModule]:
        """返回已启用的模块实例列表"""
        enabled_ids = self._get_enabled_ids(db)
        if enabled_ids is None:
            # 首次运行 — 默认全部启用
            return [cls() for cls in self._modules.values()]
        return [self._modules[mid]() for mid in enabled_ids if mid in self._modules]

    def get_available_modules(self, db) -> List[InterfaceModule]:
        """返回尚未启用的模块列表（可用于"添加接口"）"""
        enabled_ids = self._get_enabled_ids(db)
        if enabled_ids is None:
            return []
        return [cls() for mid, cls in self._modules.items() if mid not in enabled_ids]

    # ═══ 启用/禁用 ═════════════════════════════

    def enable_module(self, db, module_id: str):
        """启用模块"""
        enabled = self._get_enabled_ids(db)
        if enabled is None:
            # 首次操作 — 用所有已注册模块初始化，再确保目标在内
            enabled = list(self._modules.keys())
        if module_id not in enabled:
            enabled.append(module_id)
        db.save_config("enabled_interfaces", json.dumps(enabled, ensure_ascii=False))
        logger.info(f"Enabled interface: {module_id}")

    def disable_module(self, db, module_id: str):
        """禁用模块"""
        enabled = self._get_enabled_ids(db)
        if enabled is None:
            # 首次操作 — 用所有已注册模块初始化，再移除目标
            enabled = list(self._modules.keys())
        if module_id in enabled:
            enabled.remove(module_id)
        db.save_config("enabled_interfaces", json.dumps(enabled, ensure_ascii=False))
        logger.info(f"Disabled interface: {module_id}")

    def is_enabled(self, db, module_id: str) -> bool:
        """检查模块是否启用"""
        enabled = self._get_enabled_ids(db)
        if enabled is None:
            return True  # 默认全部启用
        return module_id in enabled

    # ═══ 内部方法 ═══════════════════════════════

    def _get_enabled_ids(self, db) -> Optional[List[str]]:
        """从数据库读取已启用的模块 ID 列表"""
        try:
            raw = db.get_config("enabled_interfaces")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to read enabled_interfaces: {e}")
        return None
