# -*- coding: utf-8 -*-
"""汇率显示组件"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QThread

from src.models.database import DatabaseManager
from src.services.exchange_rate import ExchangeRateService


class ExchangeRateWorker(QThread):
    """后台获取汇率"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db

    def run(self):
        try:
            svc = ExchangeRateService(self.db)
            result = svc.fetch_and_save()
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("API返回数据无效")
        except Exception as e:
            self.error.emit(str(e))


class ExchangeWidget(QWidget):
    """汇率栏组件"""

    rate_updated = Signal(float)  # cny_to_rub rate

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._worker = None
        self._build_ui()
        self._load_cached()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_rate = QLabel("1 CNY = ?.?? RUB")
        self.lbl_rate.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_rate)

        self.lbl_updated = QLabel("")
        self.lbl_updated.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.lbl_updated)

        layout.addStretch()

        self.btn_sync = QPushButton("🔄 同步汇率")
        self.btn_sync.setFixedHeight(28)
        self.btn_sync.clicked.connect(self._on_sync)
        layout.addWidget(self.btn_sync)

    def _load_cached(self):
        svc = ExchangeRateService(self.db)
        rate = svc.get_cached_rate()
        if rate and rate.get("cny_to_rub"):
            self._display_rate(rate["cny_to_rub"], rate.get("updated_at"))

    def _display_rate(self, cny_to_rub, updated_at=None):
        self.lbl_rate.setText(f"1 CNY = {cny_to_rub:.4f} RUB")
        if updated_at:
            ts = str(updated_at)[:19] if updated_at else ""
            self.lbl_updated.setText(f"(更新: {ts})")

    def _on_sync(self):
        if self._worker and self._worker.isRunning():
            return
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("⏳ 获取中...")
        self._worker = ExchangeRateWorker(self.db)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, rate_dict):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄 同步汇率")
        self._display_rate(rate_dict["cny_to_rub"], rate_dict.get("updated_at"))
        self.rate_updated.emit(rate_dict["cny_to_rub"])

    def _on_error(self, err):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄 同步汇率")
        self.lbl_updated.setText(f"(同步失败)")
        self.lbl_updated.setStyleSheet("color: #cf1322; font-size: 11px;")
