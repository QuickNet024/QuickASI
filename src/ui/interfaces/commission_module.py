# -*- coding: utf-8 -*-
"""佣金数据接口模块 — 统一卡片风格 + 多平台API同步"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QGroupBox, QRadioButton,
    QButtonGroup, QFrame, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal

from src.models.database import DatabaseManager
from src.services.commission_svc import CommissionService
from src.config import Config
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry
from src.ui.api_settings_dialog import ApiSettingsDialog


# ═══ Workers ═══════════════════════════════════

class CommissionImportWorker(QThread):
    """Excel 导入 Worker"""
    finished = Signal(int, str, str)
    error = Signal(str)

    def __init__(self, db, file_path, platform, shop_type):
        super().__init__()
        self._commission_db = DatabaseManager(Config.DB_COMMISSION_PATH, init_tables=["commissions", "commission_meta", "app_config"])
        self.file_path = file_path
        self.platform = platform
        self.shop_type = shop_type

    def run(self):
        try:
            svc = CommissionService(self._commission_db)
            count = svc.import_from_excel(
                self.file_path, self.platform, self.shop_type)
            if not self.isInterruptionRequested():
                self.finished.emit(count, self.platform, self.shop_type)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class CommissionSyncWorker(QThread):
    """API 同步佣金 Worker — 支持多平台"""
    finished = Signal(int, list)  # total_count, [synced_platforms]
    error = Signal(str)

    def __init__(self, db, platforms: list):
        super().__init__()
        self._commission_db = DatabaseManager(Config.DB_COMMISSION_PATH, init_tables=["commissions", "commission_meta", "app_config"])
        self.platforms = platforms

    def run(self):
        try:
            svc = CommissionService(self._commission_db)
            total = 0
            synced = []
            for platform in self.platforms:
                if self.isInterruptionRequested():
                    return
                try:
                    count = svc.sync_from_api(platform)
                    total += count
                    synced.append(platform)
                except NotImplementedError:
                    raise
                except Exception as e:
                    synced.append(f"{platform}(失败)")
            if not self.isInterruptionRequested():
                self.finished.emit(total, synced)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


# ═══ 同步平台选择对话框（多选） ══════════════

class _SyncPlatformsDialog(QDialog):
    """选择要同步的平台（可多选）"""

    PLATFORMS = [
        ("wb", "WB (Wildberries)"),
        ("ozon", "OZON"),
        ("market", "MARKET (Яндекс Маркет)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同步佣金 — 选择平台")
        self.setMinimumWidth(320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        hint = QLabel("选择要通过 API 同步佣金数据的平台：")
        layout.addWidget(hint)

        self._checkboxes = {}
        for key, label in self.PLATFORMS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._checkboxes[key] = cb
            layout.addWidget(cb)

        # 全选/取消
        sel_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(26)
        btn_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checkboxes.values()])
        sel_row.addWidget(btn_all)

        btn_none = QPushButton("取消全选")
        btn_none.setFixedHeight(26)
        btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes.values()])
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_selected_platforms(self) -> list:
        return [k for k, cb in self._checkboxes.items() if cb.isChecked()]


# ═══ 导入类型选择对话框（单选平台+店铺类型） ═══

class _ImportTypeDialog(QDialog):
    """导入佣金表 — 选择具体平台 + 本土/跨境"""

    PLATFORMS = [
        ("wb", "WB (Wildberries)"),
        ("ozon", "OZON"),
        ("market", "MARKET (Яндекс Маркет)"),
    ]

    SHOP_TYPES = [
        ("local", "本土店铺"),
        ("cross_border", "跨境店铺"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入佣金表 — 选择类型")
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        platform_group = QGroupBox("选择平台")
        platform_lay = QVBoxLayout(platform_group)
        self._platform_group = QButtonGroup(self)
        for i, (key, label) in enumerate(self.PLATFORMS):
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            self._platform_group.addButton(rb, i)
            platform_lay.addWidget(rb)
        layout.addWidget(platform_group)

        type_group = QGroupBox("选择店铺类型")
        type_lay = QVBoxLayout(type_group)
        self._type_group = QButtonGroup(self)
        for i, (key, label) in enumerate(self.SHOP_TYPES):
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            self._type_group.addButton(rb, i)
            type_lay.addWidget(rb)
        layout.addWidget(type_group)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_selection(self) -> tuple:
        platform_idx = self._platform_group.checkedId()
        type_idx = self._type_group.checkedId()
        platform = self.PLATFORMS[platform_idx][0] if platform_idx >= 0 else "wb"
        shop_type = self.SHOP_TYPES[type_idx][0] if type_idx >= 0 else "local"
        return platform, shop_type


# ═══ Module ═══════════════════════════════════

class CommissionModule(InterfaceModule):

    @property
    def module_id(self) -> str:
        return "commission"

    @property
    def name(self) -> str:
        return "佣金数据"

    @property
    def description(self) -> str:
        return ""

    @property
    def icon_text(self) -> str:
        return ""

    def create_widget(self, db, signals: ModuleSignals = None) -> QWidget:
        return _CommissionWidget(db, signals)


class _CommissionWidget(QWidget):
    """佣金数据卡片内容"""

    def __init__(self, db: DatabaseManager, signals: ModuleSignals = None):
        super().__init__()
        # db is app_db for registry; create module-specific DB
        self.db = DatabaseManager(Config.DB_COMMISSION_PATH, init_tables=["commissions", "commission_meta", "app_config"])
        self._signals = signals
        self._worker = None
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 信息展示框 ──
        info_box = QFrame()
        info_box.setObjectName("commissionInfoBox")
        info_inner = QVBoxLayout(info_box)
        info_inner.setContentsMargins(10, 8, 10, 8)
        info_inner.setSpacing(1)

        lbl_hint = QLabel("佣金数据")
        lbl_hint.setObjectName("rateHint")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(lbl_hint)

        self.lbl_count = QLabel("--")
        self.lbl_count.setObjectName("rateValue")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_count)

        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("rateHint")
        self.lbl_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_detail)

        layout.addWidget(info_box)
        layout.addSpacing(4)

        # ── 主按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_sync = QPushButton("同步佣金")
        self.btn_sync.setProperty("class", "btn-primary")
        self.btn_sync.setMinimumHeight(36)
        self.btn_sync.clicked.connect(self._on_sync_api)
        btn_row.addWidget(self.btn_sync)

        self.btn_import = QPushButton("导入佣金表")
        self.btn_import.setProperty("class", "btn-primary")
        self.btn_import.setMinimumHeight(36)
        self.btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(self.btn_import)

        layout.addLayout(btn_row)

        # ── API 设置 ──
        self.btn_settings = QPushButton("API 设置")
        self.btn_settings.setFixedHeight(30)
        self.btn_settings.clicked.connect(self._on_settings)
        layout.addWidget(self.btn_settings)

        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def _cleanup_worker(self, worker_attr: str = '_worker'):
        old = getattr(self, worker_attr, None)
        if old is not None:
            try: old.finished.disconnect()
            except Exception: pass
            try: old.error.disconnect()
            except Exception: pass
            old.requestInterruption()
            if old.isRunning():
                old.wait(10000)
                if old.isRunning():
                    # Thread still running — keep reference alive
                    # so Python GC doesn't destroy it
                    return
            old.deleteLater()
            setattr(self, worker_attr, None)

    # ── 同步佣金（API，多平台选择）──

    def _on_sync_api(self):
        """选择要同步的平台（可多选），然后通过 API 同步"""
        dlg = _SyncPlatformsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        platforms = dlg.get_selected_platforms()
        if not platforms:
            QMessageBox.information(self, "提示", "请至少选择一个平台")
            return

        if self._worker and self._worker.isRunning():
            return

        names = ", ".join(p.upper() for p in platforms)
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("同步中...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        if self._signals:
            self._signals.sync_started.emit()
        self._cleanup_worker()
        self._worker = CommissionSyncWorker(self.db, platforms)
        self._worker.finished.connect(self._on_sync_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_sync_done(self, total, synced_list):
        self._cleanup_worker()
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("同步佣金")
        self.progress.setVisible(False)
        self._refresh_status()
        if self._signals:
            self._signals.sync_finished.emit()
            self._signals.stats_changed.emit()
        names = ", ".join(s.upper() for s in synced_list)
        QMessageBox.information(self, "同步完成",
            f"已同步: {names}\n共 {total} 条佣金数据")

    # ── 导入佣金表（Excel，单选平台+店铺类型）──

    def _on_import(self):
        """选择具体平台+本土/跨境，再选 Excel 文件"""
        dlg = _ImportTypeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        platform, shop_type = dlg.get_selection()
        type_label = f"{platform.upper()} {'本土' if shop_type == 'local' else '跨境'}"

        path, _ = QFileDialog.getOpenFileName(
            self, f"选择{type_label}佣金表", "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*)")
        if not path:
            return

        if self._worker and self._worker.isRunning():
            return

        self.btn_import.setEnabled(False)
        self.btn_import.setText("导入中...")
        if self._signals:
            self._signals.sync_started.emit()
        self._cleanup_worker()
        self._worker = CommissionImportWorker(self.db, path, platform, shop_type)
        self._worker.finished.connect(self._on_import_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_import_done(self, count, platform, shop_type):
        self._cleanup_worker()
        type_label = f"{platform.upper()} {'本土' if shop_type == 'local' else '跨境'}"
        self.btn_import.setEnabled(True)
        self.btn_import.setText("导入佣金表")
        self._refresh_status()
        if self._signals:
            self._signals.sync_finished.emit()
            self._signals.stats_changed.emit()
        QMessageBox.information(self, "导入成功",
            f"成功导入 {count} 条 {type_label} 佣金数据")

    def _on_error(self, err):
        self._cleanup_worker()
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("同步佣金")
        self.btn_import.setEnabled(True)
        self.btn_import.setText("导入佣金表")
        self.progress.setVisible(False)
        QMessageBox.warning(self, "操作失败", err)

    def stop_worker(self):
        """Stop the worker thread gracefully."""
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(10000)
        self._cleanup_worker()

    # ── API 设置（3个平台独立配置）──

    def _on_settings(self):
        ApiSettingsDialog("佣金 API 设置", [
            ("wb_commission_api_key", "WB API Key", "", True),
            ("wb_commission_api_url", "WB API URL", ""),
            ("ozon_commission_api_key", "OZON API Key", "", True),
            ("ozon_commission_api_url", "OZON API URL", ""),
            ("market_commission_api_key", "MARKET API Key", "", True),
            ("market_commission_api_url", "MARKET API URL", ""),
        ], self.db, self).exec()

    def _refresh_status(self):
        # Try dynamic tables first
        tables = self.db.get_commission_tables()
        if tables:
            total = sum(t.row_count for t in tables)
            self.lbl_count.setText(f"{total:,} 条")
            lines = []
            for t in tables:
                shop_label = "本土" if t.shop_type == "local" else "跨境"
                label = f"{t.platform.upper()}{shop_label}"
                lines.append(f"{label}:{t.row_count:,}")
            self.lbl_detail.setText("  ".join(lines))
        else:
            # Fallback to old commissions table
            total = self.db.get_commission_count()
            self.lbl_count.setText(f"{total} 条")
            lines = []
            for platform in ["wb", "ozon", "market"]:
                for shop_type in ["local", "cross_border"]:
                    count = self.db.get_commission_count_by_type(platform, shop_type)
                    if count > 0:
                        label = f"{platform.upper()}{'本土' if shop_type == 'local' else '跨境'}"
                        lines.append(f"{label}:{count}")
            if lines:
                self.lbl_detail.setText("  ".join(lines))
            else:
                self.lbl_detail.setText("暂无佣金数据")


# 自动注册
InterfaceRegistry.register(CommissionModule)
