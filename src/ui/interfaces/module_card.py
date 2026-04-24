# -*- coding: utf-8 -*-
"""ModuleCard V3 — 现代SVG矢量图标 + 分类accent色"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor

from src.ui.assets.icons import get_icon_pixmap, MODULE_COLORS, COLOR_MUTED, get_util_icon

# 模块 → accent色分类映射
MODULE_ACCENT_MAP = {
    "feishu": "blue",
    "commission": "green",
    "exchange_rate": "orange",
    "shipping": "blue",
}


class ModuleCard(QWidget):
    """接口模块卡片容器 V3 — SVG 图标 + accent 分割线"""

    remove_requested = Signal(str)

    def __init__(self, module, content_widget: QWidget, parent=None):
        super().__init__(parent)
        self._module = module
        self.module_id = module.module_id
        self.setObjectName("moduleCard")

        accent = MODULE_ACCENT_MAP.get(module.module_id, "blue")
        self.setProperty("accent", accent)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(260)
        self._build_ui(module, content_widget)

    def _build_ui(self, module, content_widget):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        # ── 标题行: SVG图标 + 名称 + 关闭按钮 ──
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        # SVG 矢量图标（替代 emoji）
        icon_label = QLabel()
        icon_label.setObjectName("moduleIcon")
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_color = MODULE_COLORS.get(module.module_id, COLOR_MUTED)
        px = get_icon_pixmap(module.module_id, size=24, color=icon_color)
        if not px.isNull():
            icon_label.setPixmap(px)
        header_row.addWidget(icon_label)

        # 标题
        title_label = QLabel(module.name)
        title_label.setObjectName("moduleTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title_label)

        # 版本号标签
        version_label = QLabel(f"v{module.version}")
        version_label.setObjectName("moduleVersion")
        version_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(version_label)

        header_row.addStretch()

        # 关闭按钮
        self._btn_remove = QPushButton()
        self._btn_remove.setObjectName("moduleRemoveBtn")
        self._btn_remove.setFixedSize(24, 24)
        self._btn_remove.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_remove.setToolTip("移除此接口")
        close_px = get_util_icon("close", 14, "#9CA3AF")
        from PySide6.QtGui import QIcon
        self._btn_remove.setIcon(QIcon(close_px))
        self._btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.module_id))
        header_row.addWidget(self._btn_remove)

        outer.addLayout(header_row)

        # ── accent 色分割线 ──
        sep = QFrame()
        sep.setFixedHeight(2)
        sep.setObjectName("moduleAccentSep")
        outer.addWidget(sep)

        # ── 内容区 ──
        if content_widget:
            content_widget.setParent(self)
            outer.addWidget(content_widget)

    @property
    def module(self):
        return self._module
