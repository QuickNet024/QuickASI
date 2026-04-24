# -*- coding: utf-8 -*-
"""数据接口面板 — 插件式卡片网格布局
每个接口由 InterfaceModule 子类独立封装，通过 InterfaceRegistry 管理启用/禁用。
SyncWidget 只负责布局和卡片容器的增删。
"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QSizePolicy,
    QScrollArea, QFrame, QDialog, QDialogButtonBox,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal

from src.models.database import DatabaseManager
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry
from src.ui.interfaces.module_card import ModuleCard
from src.ui.assets.icons import get_util_icon

logger = logging.getLogger(__name__)


# ═══ 接口管理对话框 ══════════════════════════════

class _ManageInterfacesDialog(QDialog):
    """显示所有已注册接口模块，可启用/禁用"""

    def __init__(self, all_modules, enabled_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("接口管理")
        self.setMinimumWidth(400)
        self.setMinimumHeight(280)
        self._modules = all_modules
        self._initial_enabled = set(enabled_ids)
        self._current_enabled = set(enabled_ids)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel("选择要启用的接口：")
        layout.addWidget(hint)

        from PySide6.QtWidgets import QCheckBox
        from src.ui.assets.icons import get_icon_pixmap, MODULE_COLORS, COLOR_MUTED
        self._checkboxes = {}
        for m in self._modules:
            cb = QCheckBox(f"  {m.name}")
            cb.setChecked(m.module_id in self._current_enabled)
            # 设置 SVG 图标
            color = MODULE_COLORS.get(m.module_id, COLOR_MUTED)
            px = get_icon_pixmap(m.module_id, size=16, color=color)
            if not px.isNull():
                cb.setIcon(px)
            layout.addWidget(cb)
            self._checkboxes[m.module_id] = cb

        layout.addSpacing(8)
        self._lbl_hint = QLabel("")
        self._lbl_hint.setProperty("class", "stat-label")
        self._update_hint()
        layout.addWidget(self._lbl_hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _update_hint(self):
        on = sum(1 for cb in self._checkboxes.values() if cb.isChecked())
        total = len(self._checkboxes)
        self._lbl_hint.setText(f"已启用 {on}/{total} 个接口")

    def get_changes(self):
        """返回 (to_enable: set, to_disable: set)"""
        new_enabled = {mid for mid, cb in self._checkboxes.items() if cb.isChecked()}
        to_enable = new_enabled - self._initial_enabled
        to_disable = self._initial_enabled - new_enabled
        return to_enable, to_disable


# ═══ 主面板 — 插件式卡片网格 ═════════════════════

class SyncWidget(QWidget):
    """数据接口页面 — 插件式卡片网格布局，自适应宽度。

    使用 InterfaceRegistry 发现和加载模块，支持动态添加/删除。
    """

    sync_started = Signal()
    sync_finished = Signal()
    stats_changed = Signal()

    CARD_MIN_WIDTH = 260

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._module_cards: list = []   # [ModuleCard, ...]
        self._signals = ModuleSignals()
        self._connect_signals()
        self._build_ui()
        self._load_modules()

    # ── UI 构建 ──────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._grid_container = QWidget()
        self._grid_container.setObjectName("syncGridContainer")
        self._grid_layout = QVBoxLayout(self._grid_container)
        self._grid_layout.setSpacing(16)

        # "管理接口" 按钮（放在网格底部）
        self._btn_add = QPushButton(" 管理接口")
        self._btn_add.setObjectName("btnAddInterface")
        self._btn_add.setFixedHeight(40)
        self._btn_add.setProperty("class", "btn-icon")
        self._btn_add.setIcon(get_util_icon("settings", 16))
        self._btn_add.clicked.connect(self._on_manage_interfaces)

        scroll.setWidget(self._grid_container)
        outer.addWidget(scroll)

    def _connect_signals(self):
        """将 ModuleSignals 转发为 SyncWidget 自身信号"""
        self._signals.sync_finished.connect(lambda: self.sync_finished.emit())
        self._signals.sync_started.connect(lambda: self.sync_started.emit())
        self._signals.stats_changed.connect(lambda: self.stats_changed.emit())

    # ── 模块加载 ──────────────────────────────────

    def _load_modules(self):
        """从注册中心加载已启用的模块并创建卡片"""
        # 触发自动注册：导入 interfaces 包
        try:
            import src.ui.interfaces  # noqa: F401
        except ImportError:
            pass

        registry = InterfaceRegistry()
        enabled = registry.get_enabled_modules(self.db)

        for module in enabled:
            self._create_card(module)

        self._refresh_layout()

    def _create_card(self, module: InterfaceModule):
        """为模块创建 ModuleCard 并加入列表"""
        try:
            content = module.create_widget(self.db, self._signals)
            card = ModuleCard(module, content)
            card.remove_requested.connect(self._on_remove_interface)
            self._module_cards.append(card)
        except Exception as e:
            logger.error(f"Failed to create card for {module.module_id}: {e}")

    def _remove_card(self, module_id: str):
        """从列表中移除指定模块的卡片"""
        for i, card in enumerate(self._module_cards):
            if card.module_id == module_id:
                card.setParent(None)
                card.deleteLater()
                self._module_cards.pop(i)
                break
        self._refresh_layout()

    # ── 布局刷新 ──────────────────────────────────

    def _refresh_layout(self):
        """重新排列所有卡片到网格中"""
        # 清空旧布局
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().setParent(self._grid_container)
            elif item.widget():
                item.widget().setParent(self._grid_container)

        # 计算列数
        w = max(self.width() - 40, self.CARD_MIN_WIDTH)
        cols = max(2, min(4, w // self.CARD_MIN_WIDTH))

        # 排列卡片
        row = None
        for i, card in enumerate(self._module_cards):
            if i % cols == 0:
                row = QHBoxLayout()
                row.setSpacing(16)
                self._grid_layout.addLayout(row)
            card.setMinimumWidth(self.CARD_MIN_WIDTH)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row.addWidget(card)

        if row:
            row.addStretch()

        # 底部添加按钮
        self._grid_layout.addWidget(self._btn_add)
        self._grid_layout.addStretch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        old_size = getattr(self, '_last_resize_size', None)
        new_size = event.size()
        # Only refresh if width changed significantly (more than CARD_MIN_WIDTH/2)
        if old_size is None or abs(new_size.width() - old_size.width()) >= 100:
            self._last_resize_size = new_size
            self._refresh_layout()

    # ── 事件处理 ──────────────────────────────────

    def _on_manage_interfaces(self):
        """打开接口管理对话框 — 显示所有模块，可启用/禁用"""
        registry = InterfaceRegistry()
        all_modules = [registry.get_module(mid) for mid in registry.get_all_module_ids()]
        all_modules = [m for m in all_modules if m is not None]

        enabled_ids = set()
        enabled_mods = registry.get_enabled_modules(self.db)
        for m in enabled_mods:
            enabled_ids.add(m.module_id)

        dlg = _ManageInterfacesDialog(all_modules, enabled_ids, self)
        if dlg.exec() == QDialog.Accepted:
            to_enable, to_disable = dlg.get_changes()

            # 禁用模块
            for mid in to_disable:
                registry.disable_module(self.db, mid)
                self._remove_card(mid)

            # 启用模块
            for mid in to_enable:
                module = registry.get_module(mid)
                if module:
                    registry.enable_module(self.db, mid)
                    self._create_card(module)

            if to_enable or to_disable:
                self._refresh_layout()

    def _on_remove_interface(self, module_id: str):
        """禁用并移除指定接口"""
        reply = QMessageBox.question(
            self, "移除接口",
            f"确定要移除此接口吗？\n数据不会被删除，只是从页面隐藏。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            registry = InterfaceRegistry()
            registry.disable_module(self.db, module_id)
            self._remove_card(module_id)

    # ── 公共接口 ──────────────────────────────────

    def set_theme(self, theme):
        """QSS 自动处理主题，此处无需操作"""
        pass

    def update_calc_stats(self, profit_count, loss_count, unmatched_count):
        pass

    def should_sync_images(self) -> bool:
        """查找飞书模块的内容 widget 中的同步图片 checkbox"""
        for card in self._module_cards:
            if card.module_id == "feishu":
                content = card.findChild(QCheckBox)
                if content:
                    return content.isChecked()
        return False

    def stop_all_workers(self):
        """Stop all worker threads in module cards gracefully."""
        for card in self._module_cards:
            # Find the content widget inside the card
            for child in card.findChildren(QWidget):
                if hasattr(child, 'stop_worker'):
                    child.stop_worker()
                    break
