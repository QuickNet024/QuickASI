# -*- coding: utf-8 -*-
"""顶部工作台栏。"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel


class TopBar(QWidget):
    """商业化工作台顶部栏，提供页面上下文与状态感知。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(72)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.page_title = QLabel("店铺运营工作台")
        self.page_title.setObjectName("pageTitle")
        title_col.addWidget(self.page_title)

        self.page_subtitle = QLabel("围绕导入、匹配、测算、导出的一体化运营流程")
        self.page_subtitle.setObjectName("pageSubtitle")
        title_col.addWidget(self.page_subtitle)

        layout.addLayout(title_col, stretch=1)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)

        self.context_badge = QLabel("当前模块")
        self.context_badge.setObjectName("contextBadge")
        meta_col.addWidget(self.context_badge)

        self.context_hint = QLabel("准备开始")
        self.context_hint.setObjectName("contextHint")
        meta_col.addWidget(self.context_hint)

        layout.addLayout(meta_col)

    def set_context(self, title: str, subtitle: str, badge: str = "", hint: str = ""):
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        self.context_badge.setText(badge or "当前模块")
        self.context_hint.setText(hint or "准备开始")

    def refresh_theme(self, theme: str):
        """主题样式由 QSS 接管。"""
        _ = theme
