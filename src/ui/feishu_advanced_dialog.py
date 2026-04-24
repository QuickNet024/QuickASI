# -*- coding: utf-8 -*-
"""飞书高级同步设置弹窗 V3 — Sheet选择 + 列映射 + 同步参数 + 图片设置
新增: 线程数、限流QPS、图片缓存路径、增量模式配置"""

import json
import os
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QComboBox,
    QMessageBox,
    QGroupBox, QScrollArea, QFrame, QWidget, QProgressBar,
    QGridLayout, QFormLayout, QSizePolicy,
    QSpinBox, QDoubleSpinBox, QLineEdit, QFileDialog,
    QTabWidget, QWidget as QTabWidgetPage
)
from PySide6.QtCore import Qt, QThread, Signal

from src.models.database import DatabaseManager
from src.services.feishu_service import FeishuService, DEFAULT_COLUMN_MAP
from src.ui.assets.icons import get_util_icon

logger = logging.getLogger(__name__)


class FetchMetaWorker(QThread):
    """后台读取飞书 sheet 元数据"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db

    def run(self):
        try:
            svc = FeishuService(self.db)
            result = svc.get_all_sheet_headers()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


COL_TYPES = [
    ("text",      "文本"),
    ("number",    "数字"),
    ("image",     "图片"),
    ("price_rub", "价格(RUB)"),
    ("price_usd", "价格(USD)"),
    ("price_cny", "价格(CNY)"),
]

# 用于自动检测列类型的关键词
_TYPE_KEYWORDS = {
    "price_rub": ["руб", "rub", "цена", "price_rub"],
    "price_usd": ["usd", "$", "price_usd"],
    "price_cny": ["cny", "yuan", "元", "rmb", "price_cny"],
    "image":     ["图片", "image", "photo", "照片", "img", "图"],
    "number":    ["数量", "库存", "inventory", "stock", "qty", "count"],
}

TARGET_FIELDS = [
    ("sku_code", "货号 (SKU)"),
    ("distribution_price", "分销价格"),
    ("dimensions", "尺寸"),
    ("weight", "重量"),
    ("category", "类目"),
    ("chinese_name", "中文名称"),
    ("brand", "品牌"),
    ("inventory", "库存数量"),
    ("inventory_status", "库存状态"),
    ("supplier", "供应商编码"),
    ("image", "图片"),
    ("_skip", "不同步"),
]

SHEET_COLUMNS = 3

MAX_COL_HEADERS = 30  # 只读前30列表头


class FeishuAdvancedDialog(QDialog):
    """飞书高级同步设置 V3 — Tab式布局: 数据同步 + 列映射 + 高级参数"""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("飞书同步 — 高级设置")
        self.setMinimumSize(800, 700)
        self.setMaximumSize(900, 800)
        self.resize(900, 750)
        self._sheet_headers = {}
        self._sheet_checks = {}
        self._col_rows = []
        self._worker = None
        self._build_ui()
        self._load_current_settings()
        self._auto_load_saved_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 顶部：读取按钮 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.btn_fetch = QPushButton(" 刷新结构")
        self.btn_fetch.setProperty("class", "btn-primary")
        self.btn_fetch.setMinimumHeight(36)
        self.btn_fetch.setIcon(get_util_icon("refresh", 16))
        self.btn_fetch.clicked.connect(self._on_fetch)
        top_row.addWidget(self.btn_fetch)

        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("class", "stat-label")
        top_row.addWidget(self.lbl_status)
        top_row.addStretch()
        layout.addLayout(top_row)

        # ── Tab 页 ──
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, stretch=1)

        # Tab 1: Sheet 选择
        self._build_sheet_tab()

        # Tab 2: 列映射
        self._build_column_tab()

        # Tab 3: 同步参数（新增）
        self._build_sync_settings_tab()

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("保存设置")
        btn_save.setProperty("class", "btn-primary")
        btn_save.setFixedHeight(36)
        btn_save.setFixedWidth(120)
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    # ═══ Tab 1: Sheet 选择 ═══════════════════════

    def _build_sheet_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)

        sheet_group = QGroupBox("选择要同步的 Sheet 页")
        sheet_group_lay = QVBoxLayout(sheet_group)
        sheet_group_lay.setContentsMargins(10, 16, 10, 10)
        sheet_group_lay.setSpacing(6)

        # 全选 / 取消全选
        sel_row = QHBoxLayout()
        sel_row.setSpacing(4)

        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.setFixedSize(52, 22)
        self._btn_select_all.setProperty("class", "mini-btn")
        self._btn_select_all.clicked.connect(self._on_select_all)
        sel_row.addWidget(self._btn_select_all)

        self._btn_deselect_all = QPushButton("取消全选")
        self._btn_deselect_all.setFixedSize(64, 22)
        self._btn_deselect_all.setProperty("class", "mini-btn")
        self._btn_deselect_all.clicked.connect(self._on_deselect_all)
        sel_row.addWidget(self._btn_deselect_all)

        sel_row.addSpacing(8)

        self._lbl_sheet_count = QLabel("")
        self._lbl_sheet_count.setProperty("class", "stat-label")
        sel_row.addWidget(self._lbl_sheet_count)
        sel_row.addStretch()
        sheet_group_lay.addLayout(sel_row)

        # Sheet 网格放在滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(400)

        self._sheet_grid_widget = QWidget()
        self._sheet_grid = QGridLayout(self._sheet_grid_widget)
        self._sheet_grid.setContentsMargins(4, 4, 4, 4)
        self._sheet_grid.setSpacing(6)
        self._sheet_grid.setColumnStretch(0, 1)
        self._sheet_grid.setColumnStretch(1, 1)
        self._sheet_grid.setColumnStretch(2, 1)
        scroll.setWidget(self._sheet_grid_widget)
        sheet_group_lay.addWidget(scroll)

        lay.addWidget(sheet_group)
        self._tabs.addTab(page, "Sheet 选择")

    # ═══ Tab 2: 列映射（简洁表单）════════════════

    def _build_column_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)

        hint = QLabel(
            "勾选要同步的列，映射名默认与飞书表头一致，双击可修改。最多显示前30列。")
        hint.setProperty("class", "stat-label")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(4)

        # 批量操作行
        batch_row = QHBoxLayout()
        batch_row.setSpacing(4)

        btn_check_all = QPushButton("全选同步")
        btn_check_all.setFixedSize(64, 22)
        btn_check_all.setProperty("class", "mini-btn")
        btn_check_all.clicked.connect(lambda: self._batch_col_check(True))
        batch_row.addWidget(btn_check_all)

        btn_uncheck_all = QPushButton("取消全选")
        btn_uncheck_all.setFixedSize(64, 22)
        btn_uncheck_all.setProperty("class", "mini-btn")
        btn_uncheck_all.clicked.connect(lambda: self._batch_col_check(False))
        batch_row.addWidget(btn_uncheck_all)

        batch_row.addSpacing(8)

        self._lbl_col_count = QLabel("")
        self._lbl_col_count.setProperty("class", "stat-label")
        batch_row.addWidget(self._lbl_col_count)
        batch_row.addStretch()
        lay.addLayout(batch_row)

        # 表头行与批量操作行之间留出间距
        lay.addSpacing(8)

        # 表头行
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        lbl_sync_h = QLabel("同步")
        lbl_sync_h.setFixedWidth(44)
        lbl_sync_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sync_h.setProperty("class", "col-header")
        header_row.addWidget(lbl_sync_h)

        lbl_col_h = QLabel("飞书表头")
        lbl_col_h.setFixedWidth(160)
        lbl_col_h.setProperty("class", "col-header")
        header_row.addWidget(lbl_col_h)

        lbl_map_h = QLabel("映射名")
        lbl_map_h.setMinimumWidth(80)
        lbl_map_h.setProperty("class", "col-header")
        header_row.addWidget(lbl_map_h, stretch=1)

        lbl_type_h = QLabel("类型")
        lbl_type_h.setFixedWidth(100)
        lbl_type_h.setProperty("class", "col-header")
        header_row.addWidget(lbl_type_h)
        lay.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("colSep")
        lay.addWidget(sep)

        # 滚动区域
        self._col_scroll = QScrollArea()
        self._col_scroll.setWidgetResizable(True)
        self._col_scroll.setFrameShape(QFrame.NoFrame)
        self._col_container = QWidget()
        self._col_layout = QVBoxLayout(self._col_container)
        self._col_layout.setContentsMargins(0, 0, 0, 0)
        self._col_layout.setSpacing(1)
        self._col_layout.addStretch()
        self._col_scroll.setWidget(self._col_container)
        lay.addWidget(self._col_scroll, stretch=1)

        self._col_rows = []
        self._tabs.addTab(page, "列映射")

    # ═══ Tab 3: 同步参数（新增） ══════════════════

    def _build_sync_settings_tab(self):
        page = QWidget()
        # 用 QScrollArea 包裹，防止高 DPI 缩放时内容重叠
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setSpacing(16)
        lay.setContentsMargins(4, 4, 4, 4)

        # ── 并行与限流 ──
        parallel_group = QGroupBox("并行与限流")
        p_form = QFormLayout(parallel_group)
        p_form.setContentsMargins(20, 24, 20, 16)
        p_form.setSpacing(14)
        p_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        p_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._spin_threads = QSpinBox()
        self._spin_threads.setRange(1, 16)
        self._spin_threads.setValue(4)
        self._spin_threads.setFixedWidth(100)
        self._spin_threads.setToolTip("并行读取 Sheet 数据的线程数量")
        p_form.addRow("数据同步线程数:", self._spin_threads)

        self._spin_rate_limit = QDoubleSpinBox()
        self._spin_rate_limit.setRange(0.5, 50.0)
        self._spin_rate_limit.setValue(5.0)
        self._spin_rate_limit.setSingleStep(0.5)
        self._spin_rate_limit.setDecimals(1)
        self._spin_rate_limit.setFixedWidth(100)
        self._spin_rate_limit.setToolTip("飞书 API 默认限流: 5 QPS")
        rate_row = QHBoxLayout()
        rate_row.setSpacing(8)
        rate_row.addWidget(self._spin_rate_limit)
        rate_row.addWidget(QLabel("(飞书默认: 5)"))
        rate_row.addStretch()
        p_form.addRow("API 限流 (请求/秒):", rate_row)

        self._spin_timeout = QSpinBox()
        self._spin_timeout.setRange(5, 120)
        self._spin_timeout.setValue(30)
        self._spin_timeout.setFixedWidth(100)
        p_form.addRow("请求超时 (秒):", self._spin_timeout)

        self._spin_retry = QSpinBox()
        self._spin_retry.setRange(0, 10)
        self._spin_retry.setValue(3)
        self._spin_retry.setFixedWidth(100)
        p_form.addRow("失败重试次数:", self._spin_retry)

        lay.addWidget(parallel_group)

        # ── 图片同步 ──
        image_group = QGroupBox("图片同步")
        i_form = QFormLayout(image_group)
        i_form.setContentsMargins(20, 24, 20, 16)
        i_form.setSpacing(14)
        i_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        i_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._edit_image_dir = QLineEdit("data/image_cache")
        self._edit_image_dir.setMinimumWidth(200)
        self._edit_image_dir.setToolTip("图片保存的本地目录（支持相对路径和绝对路径）")
        path_row.addWidget(self._edit_image_dir, stretch=1)
        btn_browse = QPushButton("浏览...")
        btn_browse.setMinimumWidth(70)
        btn_browse.clicked.connect(self._on_browse_image_dir)
        path_row.addWidget(btn_browse)
        i_form.addRow("图片缓存目录:", path_row)

        self._spin_img_threads = QSpinBox()
        self._spin_img_threads.setRange(1, 8)
        self._spin_img_threads.setValue(3)
        self._spin_img_threads.setFixedWidth(100)
        self._spin_img_threads.setToolTip("并行下载图片的线程数量")
        i_form.addRow("图片下载线程数:", self._spin_img_threads)

        self._check_incremental = QCheckBox("启用增量图片同步（仅下载新增/变更图片）")
        self._check_incremental.setChecked(True)
        self._check_incremental.setToolTip("对比本地文件和远程 token，跳过未变更的图片")
        i_form.addRow("", self._check_incremental)

        hint_img = QLabel("图片同步无大小限制，所有图片都会自动缩放保存")
        hint_img.setProperty("class", "stat-label")
        hint_img.setWordWrap(True)
        i_form.addRow("", hint_img)

        lay.addWidget(image_group)

        # ── 调试日志 ──
        debug_group = QGroupBox("调试日志")
        d_lay = QVBoxLayout(debug_group)
        d_lay.setContentsMargins(20, 24, 20, 16)
        d_lay.setSpacing(12)

        self._check_debug_window = QCheckBox("启用调试日志窗口（独立窗口显示同步日志）")
        self._check_debug_window.setToolTip("打开后，同步时会在独立窗口实时显示详细日志")
        d_lay.addWidget(self._check_debug_window)

        self._check_file_log = QCheckBox("记录日志到文件（data/logs/ 目录）")
        self._check_file_log.setToolTip("日志文件按天分割，如 feishu_sync_2026-04-24.log")
        d_lay.addWidget(self._check_file_log)

        btn_show_debug = QPushButton("打开调试窗口")
        btn_show_debug.setMinimumHeight(34)
        btn_show_debug.setMinimumWidth(120)
        btn_show_debug.clicked.connect(self._on_show_debug_window)
        d_lay.addWidget(btn_show_debug)

        hint_dbg = QLabel("调试模式用于开发诊断，可查看完整的 API 请求/响应和数据解析过程")
        hint_dbg.setProperty("class", "stat-label")
        hint_dbg.setWordWrap(True)
        d_lay.addWidget(hint_dbg)

        lay.addWidget(debug_group)

        lay.addStretch()

        scroll.setWidget(container)
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

        self._tabs.addTab(page, "同步参数")

    # ═══ 加载当前设置 ═══════════════════════════

    def _on_show_debug_window(self):
        """打开调试日志窗口"""
        from src.ui.debug_log_window import DebugLogManager
        mgr = DebugLogManager()
        # 自动启用调试输出
        self._check_debug_window.setChecked(True)
        mgr.enable_debug_window(True)
        mgr.show_window()

    def _load_current_settings(self):
        """从配置文件加载当前同步参数"""
        svc = FeishuService(self.db)
        settings = svc.get_sync_settings()

        self._spin_threads.setValue(settings.get("thread_count", 4))
        self._spin_rate_limit.setValue(settings.get("rate_limit_per_sec", 5.0))
        self._spin_timeout.setValue(settings.get("request_timeout_sec", 30))
        self._spin_retry.setValue(settings.get("retry_count", 3))
        self._edit_image_dir.setText(settings.get("image_dir", "data/image_cache"))
        self._check_incremental.setChecked(settings.get("image_incremental", True))
        self._spin_img_threads.setValue(settings.get("image_dl_threads", 3))

        # 加载调试设置 — 从 DB 持久化读取
        self._check_debug_window.setChecked(
            self.db.get_config("debug_window_enabled", "0") == "1")
        self._check_file_log.setChecked(
            self.db.get_config("debug_file_enabled", "0") == "1")

    # ═══ 自动载入上次保存的配置 ═══════════════════

    def _auto_load_saved_config(self):
        """打开对话框时，自动从数据库载入上次保存的 sheet 选择和列映射。
        这样用户可以直接看到/修改上次配置，无需先点'刷新结构'。
        点'刷新结构'才会从飞书 API 重新拉取最新表头。
        """
        svc = FeishuService(self.db)
        config = svc.get_sync_config()

        included = config.get("included_sheets", [])
        excluded = config.get("excluded_sheets", [])
        col_mapping = config.get("column_mapping", {})

        has_saved = bool(included or excluded or col_mapping)

        # ── Tab 1: 从保存的 sheet 列表恢复复选框 ──
        if included or excluded:
            all_saved = included + excluded
            row, col = 0, 0
            for title in all_saved:
                cb = QCheckBox(title)
                cb.setChecked(title not in excluded)
                cb.stateChanged.connect(self._update_sheet_count)
                self._sheet_grid.addWidget(cb, row, col)
                self._sheet_checks[title] = cb
                col += 1
                if col >= SHEET_COLUMNS:
                    col = 0
                    row += 1
            self._update_sheet_count()

        # ── Tab 2: 从保存的 column_mapping 恢复列映射行 ──
        if col_mapping:
            headers = []
            mapping_ordered = {}
            for field, info in col_mapping.items():
                h = info.get("header", field)
                headers.append(h)
                mapping_ordered[h] = info
            self._populate_col_table(headers, col_mapping)

        if has_saved:
            self.lbl_status.setText("已载入上次保存的配置")

    # ═══ 浏览图片目录 ═══════════════════════════

    def _on_browse_image_dir(self):
        current = self._edit_image_dir.text()
        path = QFileDialog.getExistingDirectory(self, "选择图片缓存目录", current)
        if path:
            self._edit_image_dir.setText(path)

    # ═══ 全选/取消 ═══════════════════════════════

    def _on_select_all(self):
        for cb in self._sheet_checks.values():
            cb.setChecked(True)
        self._update_sheet_count()

    def _on_deselect_all(self):
        for cb in self._sheet_checks.values():
            cb.setChecked(False)
        self._update_sheet_count()

    def _update_sheet_count(self):
        total = len(self._sheet_checks)
        checked = sum(1 for cb in self._sheet_checks.values() if cb.isChecked())
        self._lbl_sheet_count.setText(f"已选 {checked}/{total} 个")

    # ═══ 读取飞书结构 ═══════════════════════════

    def _on_fetch(self):
        if self._worker and self._worker.isRunning():
            return
        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("刷新中...")
        self._worker = FetchMetaWorker(self.db)
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.start()

    def _on_fetch_done(self, sheet_headers: dict):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText(" 刷新结构")
        self._sheet_headers = sheet_headers
        self.lbl_status.setText(f"已刷新 {len(sheet_headers)} 个 Sheet 页")

        # 清除旧内容
        for title, cb in self._sheet_checks.items():
            self._sheet_grid.removeWidget(cb)
            cb.deleteLater()
        self._sheet_checks.clear()

        # 加载已有配置
        svc = FeishuService(self.db)
        config = svc.get_sync_config()
        excluded = config.get("excluded_sheets", [])
        col_mapping = config.get("column_mapping", {})

        # 用网格布局填充 sheet
        row, col = 0, 0
        for title, headers in sheet_headers.items():
            cb = QCheckBox(f"{title} ({len(headers)}列)")
            cb.setChecked(title not in excluded)
            cb.stateChanged.connect(self._update_sheet_count)
            self._sheet_grid.addWidget(cb, row, col)
            self._sheet_checks[title] = cb
            col += 1
            if col >= SHEET_COLUMNS:
                col = 0
                row += 1

        self._update_sheet_count()

        # 填充列映射表（用第一个 sheet 的表头 — 所有 sheet 表头一致）
        first_sheet = next(iter(sheet_headers), None)
        if first_sheet:
            self._populate_col_table(sheet_headers[first_sheet], col_mapping)

    def _on_fetch_error(self, err):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText(" 刷新结构")
        self.lbl_status.setText("刷新失败")
        QMessageBox.warning(self, "刷新失败",
            f"无法读取飞书表格结构，请先检查 API 设置是否正确：\n{err}")

    # ═══ 列映射表 ═══════════════════════════════

    def _populate_col_table(self, headers: list, col_mapping: dict):
        # 清除旧行
        for row_data in self._col_rows:
            w = row_data.get("widget")
            if w:
                self._col_layout.removeWidget(w)
                w.deleteLater()
        self._col_rows.clear()

        # 只取前30列
        headers = headers[:MAX_COL_HEADERS]

        # 构建匹配查找表（用于自动检测是否匹配到已知字段）
        header_to_field = {}
        for field, info in DEFAULT_COLUMN_MAP.items():
            for candidate in info.get("candidates", []):
                header_to_field[candidate.lower()] = (field, info.get("type", "text"))
        if col_mapping:
            for field, info in col_mapping.items():
                header_name = info.get("header", "").lower()
                candidates = info.get("candidates", [])
                for c in candidates:
                    header_to_field[c.lower()] = (field, info.get("type", "text"))
                if header_name:
                    header_to_field[header_name] = (field, info.get("type", "text"))

        # 构建 col_mapping 中 header → mapped_name 和 type 的查找
        saved_map_names = {}
        saved_types = {}
        if col_mapping:
            for field, info in col_mapping.items():
                h = info.get("header", "")
                if h:
                    saved_map_names[h.lower()] = info.get("mapped_name", h)
                    saved_types[h.lower()] = info.get("type", "text")

        insert_idx = self._col_layout.count() - 1  # before stretch

        for i, header in enumerate(headers):
            header_lower = header.strip().lower()
            matched = header_to_field.get(header_lower)

            # 行容器
            row_widget = QWidget()
            row_widget.setMinimumHeight(44)
            row_widget.setMaximumHeight(48)
            row_h = QHBoxLayout(row_widget)
            row_h.setContentsMargins(4, 4, 4, 4)
            row_h.setSpacing(8)

            # 复选框：同步/不同步
            cb_sync = QCheckBox()
            cb_sync.setChecked(True)  # 默认同步
            cb_sync.setFixedWidth(44)
            cb_sync.stateChanged.connect(self._update_col_count)
            row_h.addWidget(cb_sync)

            # 飞书表头名（只读标签）
            lbl = QLabel(f"{i + 1}. {header}")
            lbl.setFixedWidth(160)
            lbl.setToolTip(header)
            row_h.addWidget(lbl)

            # 映射名（可编辑文本框，默认=飞书表头名）
            edit_name = QLineEdit()
            # 优先用保存的 mapped_name，否则默认=表头名
            default_name = saved_map_names.get(header_lower, header)
            edit_name.setText(default_name)
            edit_name.setPlaceholderText(header)
            row_h.addWidget(edit_name, stretch=1)

            # 类型下拉选择
            combo_type = QComboBox()
            for type_key, type_label in COL_TYPES:
                combo_type.addItem(type_label, type_key)
            combo_type.setFixedWidth(100)
            combo_type.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            # 确定默认类型：优先保存的 > 自动检测 > text
            default_type = saved_types.get(header_lower)
            if not default_type:
                default_type = self._detect_col_type(header_lower, matched)
            type_idx = combo_type.findData(default_type)
            if type_idx >= 0:
                combo_type.setCurrentIndex(type_idx)
            row_h.addWidget(combo_type)

            self._col_layout.insertWidget(insert_idx, row_widget)
            insert_idx += 1

            self._col_rows.append({
                "header": header,
                "checkbox": cb_sync,
                "edit_name": edit_name,
                "type_combo": combo_type,
                "matched_field": matched[0] if matched else None,
                "widget": row_widget,
            })

        self._update_col_count()

    # ═══ 列类型自动检测 ═══════════════════════════

    @staticmethod
    def _detect_col_type(header_lower: str, matched=None) -> str:
        """根据表头名称自动检测列类型"""
        # 先看 DEFAULT_COLUMN_MAP 匹配结果
        if matched:
            mt = matched[1]
            if mt in ("number", "image"):
                return mt
        # 关键词匹配
        for type_key, keywords in _TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in header_lower:
                    return type_key
        return "text"

    # ═══ 列映射批量操作 ═══════════════════════════

    def _batch_col_check(self, checked: bool):
        for row_data in self._col_rows:
            row_data["checkbox"].setChecked(checked)
        self._update_col_count()

    def _update_col_count(self):
        total = len(self._col_rows)
        checked = sum(1 for r in self._col_rows if r["checkbox"].isChecked())
        self._lbl_col_count.setText(f"同步 {checked}/{total} 列")

    # ═══ 保存 ═══════════════════════════════════

    def _on_save(self):
        # 1. Sheet 选择配置
        included_sheets = []
        excluded_sheets = []
        for title, cb in self._sheet_checks.items():
            if cb.isChecked():
                included_sheets.append(title)
            else:
                excluded_sheets.append(title)

        # 2. 列映射
        col_mapping = {}
        for row_data in self._col_rows:
            if not row_data["checkbox"].isChecked():
                continue  # 跳过未勾选的列
            header_name = row_data["header"]
            mapped_name = row_data["edit_name"].text().strip() or header_name
            col_type = row_data["type_combo"].currentData()
            # 自动匹配内部字段名
            field = row_data["matched_field"] or header_name
            col_mapping[field] = {
                "header": header_name,
                "mapped_name": mapped_name,
                "candidates": [header_name.lower()],
                "type": col_type,
            }

        sync_config = {
            "included_sheets": included_sheets,
            "excluded_sheets": excluded_sheets,
            "column_mapping": col_mapping,
        }

        # 3. 同步参数
        sync_settings = {
            "thread_count": self._spin_threads.value(),
            "rate_limit_per_sec": self._spin_rate_limit.value(),
            "request_timeout_sec": self._spin_timeout.value(),
            "retry_count": self._spin_retry.value(),
            "image_dir": self._edit_image_dir.text().strip(),
            "image_incremental": self._check_incremental.isChecked(),
            "image_dl_threads": self._spin_img_threads.value(),
        }

        # 保存到 DB（sync_config）
        svc = FeishuService(self.db)
        svc.save_sync_config(sync_config)

        # 保存同步参数到配置文件
        svc.update_sync_settings(sync_settings)

        # 4. 调试日志设置 — 持久化到 DB
        debug_window = self._check_debug_window.isChecked()
        debug_file = self._check_file_log.isChecked()
        self.db.save_config("debug_window_enabled", "1" if debug_window else "0")
        self.db.save_config("debug_file_enabled", "1" if debug_file else "0")

        from src.ui.debug_log_window import DebugLogManager
        mgr = DebugLogManager()
        mgr.enable_debug_window(debug_window)
        mgr.enable_file_logging(debug_file)

        # 构建结果摘要
        summary_lines = [
            f"同步 Sheet: {len(included_sheets)} 个",
            f"排除 Sheet: {len(excluded_sheets)} 个",
            f"字段映射: {len(col_mapping)} 个",
            f"线程数: {sync_settings['thread_count']}",
            f"限流: {sync_settings['rate_limit_per_sec']} QPS",
            f"图片目录: {sync_settings['image_dir']}",
            f"增量同步: {'是' if sync_settings['image_incremental'] else '否'}",
        ]

        QMessageBox.information(self, "保存成功", "高级设置已保存\n\n" + "\n".join(summary_lines))
        self.accept()
