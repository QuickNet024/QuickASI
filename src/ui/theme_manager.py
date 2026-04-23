# -*- coding: utf-8 -*-
"""主题管理器 - 深色/浅色主题切换（非QObject，避免单例崩溃）"""

import os
import logging

from src.models.database import DatabaseManager

logger = logging.getLogger(__name__)


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
        self._db = DatabaseManager()
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
        """应用指定主题，加载QSS文件"""
        self._ensure_loaded()
        if theme_name is None:
            theme_name = self._current_theme

        qss_path = os.path.join(
            os.path.dirname(__file__), "assets", f"{theme_name}.qss"
        )

        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_content = f.read()
            app.setStyleSheet(qss_content)
            self._current_theme = theme_name
            self._save_preference()
            logger.info(f"Theme applied: {theme_name}")
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
