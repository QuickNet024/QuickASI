# -*- coding: utf-8 -*-
"""接口模块抽象基类 — 所有数据接口模块的父类"""

from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QObject, Signal

from src.version import get_module_version


class InterfaceModule(ABC):
    """数据接口模块基类。
    
    每个数据接口（飞书、佣金、汇率等）都应继承此类，
    实现 module_id / name / create_widget 等接口。
    """

    @property
    @abstractmethod
    def module_id(self) -> str:
        """唯一标识符，如 'feishu', 'commission', 'exchange_rate'"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """显示名称，如 '飞书数据'"""
        pass

    @property
    def description(self) -> str:
        """可选的描述文字"""
        return ""

    @property
    def icon_text(self) -> str:
        """图标字符（emoji），用于卡片标题"""
        return "📦"

    @property
    def version(self) -> str:
        """模块版本号，从 src.version 自动获取"""
        return get_module_version(self.module_id)

    @abstractmethod
    def create_widget(self, db, signals: 'ModuleSignals' = None) -> QWidget:
        """创建并返回此模块的内容 QWidget。
        
        Args:
            db: DatabaseManager 实例
            signals: ModuleSignals 实例，用于向上传递信号
        """
        pass


class ModuleSignals(QObject):
    """模块信号容器 — 用于从子模块向 SyncWidget 传递事件"""
    sync_finished = Signal()
    sync_started = Signal()
    rate_updated = Signal(float)
    stats_changed = Signal()
