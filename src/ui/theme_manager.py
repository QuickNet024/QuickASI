# -*- coding: utf-8 -*-
"""主题管理器 - 深色/浅色主题切换（非QObject，避免单例崩溃）"""

import os
import logging

from src.config import Config
from src.models.database import DatabaseManager

try:
    import qt_material
    _HAS_QT_MATERIAL = True
except ImportError:
    _HAS_QT_MATERIAL = False

logger = logging.getLogger(__name__)

# qt-material theme name mapping
_THEME_MAP = {
    "light": "light_teal.xml",
    "dark": "dark_teal.xml",
}


class ThemeManager:
    """主题管理（简单单例，不用QObject，避免崩溃）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._current_theme = "light"
            cls._instance._db = None
            cls._instance._loaded = False
        return cls._instance

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._db = DatabaseManager(Config.DB_APP_PATH, init_tables=["app_config"])
        try:
            saved = self._db.get_config("theme", "light")
            if saved in ("light", "dark"):
                self._current_theme = saved
        except Exception:
            pass
        self._loaded = True

    @property
    def current_theme(self) -> str:
        self._ensure_loaded()
        return self._current_theme

    def apply_theme(self, app, theme_name: str = None):
        """应用指定主题"""
        self._ensure_loaded()
        if theme_name is None:
            theme_name = self._current_theme

        if _HAS_QT_MATERIAL:
            self._apply_qt_material(app, theme_name)
        else:
            self._apply_qss_fallback(app, theme_name)

    def _apply_qt_material(self, app, theme_name: str):
        """使用 qt-material 应用主题"""
        material_theme = _THEME_MAP.get(theme_name)
        if material_theme is None:
            logger.error(f"Unknown theme: {theme_name}")
            return

        # Try assets/custom.qss first (T4 will create it), fall back to project root
        css_file_path = os.path.join(
            os.path.dirname(__file__), "assets", "custom.qss"
        )
        if not os.path.isfile(css_file_path):
            css_file_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "custom_override.qss"
            )
            if not os.path.isfile(css_file_path):
                css_file_path = None

        try:
            qt_material.apply_stylesheet(
                app,
                theme=material_theme,
                css_file=css_file_path,
                invert_secondary=False,
            )
            self._current_theme = theme_name
            self._save_preference()
            logger.info(f"Theme applied (qt-material): {theme_name}")
        except Exception as e:
            logger.error(f"Failed to apply theme {theme_name}: {e}")

    def _apply_qss_fallback(self, app, theme_name: str):
        """qt-material 不可用时回退到直接加载 QSS"""
        qss_path = os.path.join(
            os.path.dirname(__file__), "assets", f"{theme_name}.qss"
        )

        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_content = f.read()
            app.setStyleSheet(qss_content)
            self._current_theme = theme_name
            self._save_preference()
            logger.info(f"Theme applied (QSS fallback): {theme_name}")
        except FileNotFoundError:
            logger.error(f"Theme file not found: {qss_path}")
        except Exception as e:
            logger.error(f"Failed to apply theme {theme_name}: {e}")

    def toggle_theme(self):
        """切换 light / dark，返回新主题名"""
        self._ensure_loaded()
        self._current_theme = "dark" if self._current_theme == "light" else "light"
        return self._current_theme

    def toggle_and_apply(self, app):
        """切换主题并立即应用"""
        new_theme = self.toggle_theme()
        self.apply_theme(app, new_theme)

    def _save_preference(self):
        try:
            if self._db:
                self._db.save_config("theme", self._current_theme)
        except Exception:
            pass

    @classmethod
    def reset_instance(cls):
        """重置单例（仅用于测试）"""
        cls._instance = None
        cls._instance._loaded = False
