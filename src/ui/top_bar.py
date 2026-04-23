# -*- coding: utf-8 -*-
"""顶栏组件 — 已移除标题（sidebar已有标题），保留为空组件用于未来扩展"""

from PySide6.QtWidgets import QWidget


class TopBar(QWidget):
    """顶栏: 当前为空组件，sidebar已有完整标题显示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(0)  # 不占空间

    def refresh_theme(self, theme: str):
        """主题切换 — 当前无需操作"""
        pass
