# -*- coding: utf-8 -*-
"""
WB亏损计算系统 - 应用入口
"""
import sys
import os

# Ensure the project root is in Python path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager


def main():
    # PySide6 / Qt6 handles HiDPI automatically — no AA_ attributes needed
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Set application font
    font = app.font()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(9)
    app.setFont(font)

    # Apply saved theme
    tm = ThemeManager()
    tm.apply_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
