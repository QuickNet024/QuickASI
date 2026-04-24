# -*- coding: utf-8 -*-
"""侧边栏导航 — 主题切换在左下角"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpacerItem, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


# 导航项
_NAV_ITEMS = [
    "数据接口",
    "产品数据",
    "佣金数据",
    "折扣推算",
    "参数设置",
]

# 主题颜色
_THEMES = {
    "light": {
        "sidebar_bg": "#FFFFFF",
        "sidebar_border": "#E8EAED",
        "nav_text": "#5F6368",
        "nav_text_hover": "#202124",
        "nav_bg_hover": "#F1F3F4",
        "nav_selected_bg": "#E8F0FE",
        "nav_selected_text": "#1A73E8",
        "nav_selected_indicator": "#1A73E8",
        "title_color": "#202124",
        "title2_color": "#80868B",
        "theme_btn_bg": "#F1F3F4",
        "theme_btn_bg_hover": "#E8EAED",
        "theme_btn_text": "#5F6368",
        "theme_btn_border": "#DADCE0",
    },
    "dark": {
        "sidebar_bg": "#202124",
        "sidebar_border": "#3C4043",
        "nav_text": "#9AA0A6",
        "nav_text_hover": "#E8EAED",
        "nav_bg_hover": "#3C4043",
        "nav_selected_bg": "#37373D",
        "nav_selected_text": "#8AB4F8",
        "nav_selected_indicator": "#8AB4F8",
        "title_color": "#E8EAED",
        "title2_color": "#9AA0A6",
        "theme_btn_bg": "#3C4043",
        "theme_btn_bg_hover": "#4A4A50",
        "theme_btn_text": "#9AA0A6",
        "theme_btn_border": "#555555",
    },
}


class SideBar(QWidget):
    """左侧垂直侧边栏 — 导航 + 底部主题切换"""

    currentChanged = Signal(int)
    themeToggleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(180)
        self._current_index = 0
        self._buttons = []
        self._indicators = []
        self._theme = "light"
        self._build_ui()

    def count(self) -> int:
        return len(self._buttons)

    def current_index(self) -> int:
        return self._current_index

    def set_current_index(self, index: int):
        if 0 <= index < len(self._buttons) and index != self._current_index:
            self._select(index)

    def refresh_theme(self, theme: str):
        self._theme = theme
        self._apply_colors()
        self._apply_selected_style(self._current_index)
        self._update_theme_btn(theme)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题区 ──
        title_box = QWidget()
        title_lay = QVBoxLayout(title_box)
        title_lay.setContentsMargins(20, 18, 20, 10)
        title_lay.setSpacing(1)

        self._title_label = QLabel("WB Calculator")
        self._title_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lay.addWidget(self._title_label)

        self._subtitle_label = QLabel("Wildberries 亏损计算")
        self._subtitle_label.setFont(QFont("Microsoft YaHei", 8))
        title_lay.addWidget(self._subtitle_label)
        layout.addWidget(title_box)

        # 分割线
        self._separator = QFrame()
        self._separator.setFixedHeight(1)
        layout.addWidget(self._separator)

        # ── 导航按钮 ──
        nav_box = QWidget()
        nav_lay = QVBoxLayout(nav_box)
        nav_lay.setContentsMargins(8, 8, 8, 0)
        nav_lay.setSpacing(2)

        for i, label in enumerate(_NAV_ITEMS):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(0)

            indicator = QLabel("")
            indicator.setFixedWidth(3)
            indicator.setFixedHeight(24)
            row_l.addWidget(indicator)

            btn = QPushButton(f"  {label}")
            btn.setObjectName("navItem")
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("Microsoft YaHei", 9))
            btn.clicked.connect(lambda checked, idx=i: self._select(idx))
            row_l.addWidget(btn)

            nav_lay.addWidget(row_w)
            self._buttons.append(btn)
            self._indicators.append(indicator)

        nav_lay.addStretch()
        layout.addWidget(nav_box, stretch=1)

        # ── 底部: 主题切换按钮 ──
        bottom_box = QWidget()
        bottom_lay = QVBoxLayout(bottom_box)
        bottom_lay.setContentsMargins(12, 8, 12, 12)
        bottom_lay.setSpacing(0)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        self._bottom_sep = sep2
        bottom_lay.addWidget(sep2)

        self._btn_theme = QPushButton()
        self._btn_theme.setFixedHeight(36)
        self._btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_theme.setFont(QFont("Segoe UI", 10))
        self._btn_theme.clicked.connect(lambda: self.themeToggleRequested.emit())
        bottom_lay.addWidget(sep2)
        bottom_lay.addSpacing(8)
        bottom_lay.addWidget(self._btn_theme)

        layout.addWidget(bottom_box)
        self._apply_selected_style(0)

    def set_nav_visible(self, index: int, visible: bool):
        """设置导航项可见性"""
        if 0 <= index < len(self._buttons):
            self._buttons[index].parentWidget().setVisible(visible)
            self._indicators[index].setVisible(visible)

    def _update_theme_btn(self, theme):
        if theme == "dark":
            self._btn_theme.setText("  \u263E  \u5207\u6362\u6D45\u8272")  # ☾ 切换浅色
        else:
            self._btn_theme.setText("  \u2600  \u5207\u6362\u6DF1\u8272")  # ☀ 切换深色

    def _select(self, index: int):
        prev = self._current_index
        self._apply_selected_style(index)
        self._current_index = index
        if prev != index:
            self.currentChanged.emit(index)

    def _apply_colors(self):
        t = _THEMES.get(self._theme, _THEMES["light"])

        self.setStyleSheet(f"""
            QWidget#sidebar {{
                background: {t['sidebar_bg']};
                border-right: 1px solid {t['sidebar_border']};
            }}
        """)

        self._title_label.setStyleSheet(
            f"color: {t['title_color']}; background: transparent; border: none;")
        self._subtitle_label.setStyleSheet(
            f"color: {t['title2_color']}; background: transparent; border: none;")
        self._separator.setStyleSheet(
            f"background: {t['sidebar_border']}; border: none;")
        self._bottom_sep.setStyleSheet(
            f"background: {t['sidebar_border']}; border: none;")

        # 主题按钮样式
        self._btn_theme.setStyleSheet(f"""
            QPushButton {{
                background: {t['theme_btn_bg']};
                color: {t['theme_btn_text']};
                border: 1px solid {t['theme_btn_border']};
                border-radius: 8px;
                text-align: left;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {t['theme_btn_bg_hover']};
            }}
        """)
        self._update_theme_btn(self._theme)

    def _apply_selected_style(self, index: int):
        t = _THEMES.get(self._theme, _THEMES["light"])

        sel = f"""
            QPushButton {{
                background: {t['nav_selected_bg']};
                color: {t['nav_selected_text']};
                border: none;
                border-radius: 0 8px 8px 0;
                text-align: left;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {t['nav_selected_bg']}; }}
        """

        norm = f"""
            QPushButton {{
                background: transparent;
                color: {t['nav_text']};
                border: none;
                border-radius: 0 8px 8px 0;
                text-align: left;
                padding: 6px 14px;
                font-weight: normal;
            }}
            QPushButton:hover {{
                background: {t['nav_bg_hover']};
                color: {t['nav_text_hover']};
            }}
        """

        ind_on = f"background: {t['nav_selected_indicator']}; border-radius: 2px;"
        ind_off = "background: transparent; border: none;"

        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(sel if i == index else norm)
        for i, ind in enumerate(self._indicators):
            ind.setStyleSheet(ind_on if i == index else ind_off)
