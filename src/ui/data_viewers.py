# -*- coding: utf-8 -*-
"""数据查看器 — 产品表格（动态列+图片+Excel筛选+列显隐+排序） + 佣金表格"""

import os
import json
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QStyledItemDelegate, QStyle, QMenu, QApplication,
    QPushButton, QSizePolicy, QToolTip
)
from PySide6.QtCore import Qt, QSize, QRect, Signal, QPoint, QTimer
from PySide6.QtGui import (QPixmap, QColor, QPen, QPainter, QPixmapCache,
                            QKeySequence, QActionGroup, QAction)

from src.models.database import DatabaseManager

logger = logging.getLogger(__name__)

# 图片缓存目录
_IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "image_cache")


# ── 缩略图 Delegate ────────────────────────────────


class ThumbnailDelegate(QStyledItemDelegate):
    """产品图片缩略图 — 48x48, 缓存, 无图占位"""

    THUMB_SIZE = 48

    def __init__(self, image_dir="", parent=None):
        super().__init__(parent)
        self._image_dir = image_dir

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        path = str(index.data(Qt.DisplayRole) or "").strip()
        thumb = self._load_thumbnail(path)
        if thumb and not thumb.isNull():
            x = option.rect.x() + (option.rect.width() - self.THUMB_SIZE) // 2
            y = option.rect.y() + (option.rect.height() - self.THUMB_SIZE) // 2
            painter.drawPixmap(x, y, thumb)
        else:
            r = QRect(option.rect.x() + 4, option.rect.y() + 4,
                       self.THUMB_SIZE, self.THUMB_SIZE)
            painter.setPen(QPen(QColor("#d9d9d9"), 1))
            painter.setBrush(QColor("#f5f5f5"))
            painter.drawRoundedRect(r, 4, 4)
            painter.setPen(QColor("#bfbfbf"))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "无图")
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.THUMB_SIZE + 8, self.THUMB_SIZE + 8)

    def _load_thumbnail(self, path):
        if not path:
            return QPixmap()
        if not os.path.isabs(path):
            path = os.path.join(self._image_dir, path)
        key = f"thumb:{path}"
        cached = QPixmapCache.find(key)
        if cached is not None:
            return cached
        if not os.path.isfile(path):
            return QPixmap()
        pm = QPixmap(path)
        if pm.isNull():
            return QPixmap()
        scaled = pm.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        QPixmapCache.insert(key, scaled)
        return scaled


# ── 产品表格 ──────────────────────────────────────


class ProductViewer(QWidget):
    """产品数据浏览面板

    功能:
    - 动态列（来自飞书 raw_sync_data）
    - 过滤"不同步"列（读取 column_mapping 中 _skip 标记）
    - 本地行号 ID 列（#）
    - Excel 风格表头筛选（右键表头 → 勾选值）
    - 列显示/隐藏设置（持久化到 feishu.db）
    - 搜索、Sheet 筛选、排序
    """

    # 列显隐设置持久化 key
    _COL_VIS_KEY = "product_viewer_hidden_cols"
    _COL_WIDTH_KEY = "product_viewer_col_widths"

    # 默认列宽映射
    _DEFAULT_WIDTHS = {
        "sku_code": 120, "sheet_name": 100, "distribution_price": 80,
        "category": 80, "chinese_name": 140, "brand": 70, "weight": 60,
        "dimensions": 80, "inventory": 70, "inventory_status": 80,
        "supplier": 90, "image": 58,
    }

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._loaded = False
        self._raw_data = []       # from get_products_raw()
        self._columns = []        # [(header_name, col_key), ...] — 不含 _skip 列
        self._allowed_headers = None  # 白名单 set，None 表示全部允许
        self._skipped_headers = set()  # 标记为 _skip 的表头名
        self._img_col_idx = -1    # 图片列索引
        self._sort_col = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._col_filters = {}    # col_idx → set(allowed_values)
        self._hidden_cols = set() # 隐藏的列名
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("搜索:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("全表搜索...")
        self._search_box.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_all_filters)
        self._search_box.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self._search_box, stretch=1)

        self._sheet_filter = QComboBox()
        self._sheet_filter.setMinimumWidth(130)
        self._sheet_filter.addItem("全部Sheet")
        self._sheet_filter.currentIndexChanged.connect(self._apply_all_filters)
        toolbar.addWidget(QLabel("Sheet:"))
        toolbar.addWidget(self._sheet_filter)

        self._btn_clear_filter = QPushButton("清除筛选")
        self._btn_clear_filter.setFixedHeight(28)
        self._btn_clear_filter.clicked.connect(self._clear_all_filters)
        toolbar.addWidget(self._btn_clear_filter)

        # 列设置按钮
        self._btn_columns = QPushButton("列设置")
        self._btn_columns.setFixedHeight(28)
        self._btn_columns.clicked.connect(self._show_column_settings)
        toolbar.addWidget(self._btn_columns)

        toolbar.addStretch()
        self._lbl_count = QLabel("共 0 条")
        self._lbl_count.setProperty("class", "stat-label")
        toolbar.addWidget(self._lbl_count)

        layout.addLayout(toolbar)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditKeyPressed)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_cell_context_menu)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setSortingEnabled(False)  # 自己控制排序
        self._table.cellChanged.connect(self._on_cell_changed)

        # 双击复制单元格内容
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # 表头：点击排序 + 右键筛选
        header = self._table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        # 图片列 delegate
        self._thumb_delegate = ThumbnailDelegate(_IMAGE_DIR)

        layout.addWidget(self._table)

    # ═══ 数据加载 ═══════════════════════════════

    def load_data(self):
        """从 DB 加载产品数据"""
        self._raw_data = self.db.get_products_raw()

        # 读取列映射配置，找出 _skip 的列
        self._load_skip_columns()

        # 确定列
        self._columns = self._detect_columns()

        # 加载列显隐设置
        self._load_column_visibility()

        self._img_col_idx = self._find_image_column()

        # 填充 Sheet 筛选
        self._populate_sheet_filter()

        # 填充表格
        self._populate_table()

        self._loaded = True

    def _load_skip_columns(self):
        """确定应显示的列集合：只有 column_mapping 中配置过且未标记 _skip 的列才显示。

        逻辑：
        - 如果 column_mapping 为空（从未配置过），显示所有列
        - 如果 column_mapping 有配置，只显示其中 type != "_skip" 的列的 header 名称
        - 不在 column_mapping 中的列（如 ID、实拍等）一律不显示
        """
        self._allowed_headers = None  # None 表示全部允许
        self._skipped_headers.clear()

        try:
            from src.services.feishu_service import FeishuService
            svc = FeishuService(self.db)
            config = svc.get_sync_config()
            col_mapping = config.get("column_mapping", {})

            if not col_mapping:
                # 从未配置过列映射 → 显示全部
                return

            # 只允许 column_mapping 中配置过的、且 type 不是 _skip 的列
            allowed = set()
            for field, info in col_mapping.items():
                col_type = info.get("type", "")
                header_name = info.get("header", "")
                if col_type == "_skip" or field == "_skip":
                    if header_name:
                        self._skipped_headers.add(header_name)
                    continue
                if header_name:
                    allowed.add(header_name)

            self._allowed_headers = allowed  # 非空 set 表示白名单

        except Exception as e:
            logger.debug(f"读取列映射配置失败（忽略）: {e}")

    def _detect_columns(self) -> list:
        """从 raw_sync_data 中提取列名列表。

        过滤规则：
        1. 如果有 _allowed_headers 白名单，只显示白名单中的列
        2. 否则显示所有列（但排除 _skipped_headers）
        3. 第一列始终是本地行号 '#'
        """
        # 从第一条有数据的记录提取列
        data_columns = []
        for item in self._raw_data:
            raw = item.get("raw", {})
            if raw:
                for header in raw.keys():
                    if not header or header == "None":
                        continue  # 跳过空列名
                    if self._allowed_headers is not None:
                        # 白名单模式：只显示配置过的列
                        if header in self._allowed_headers:
                            data_columns.append((header, header))
                    else:
                        # 全量模式：只跳过 _skip 列
                        if header not in self._skipped_headers:
                            data_columns.append((header, header))
                break

        if not data_columns:
            # 回退：使用固定列
            data_columns = [
                ("货号", "sku_code"), ("中文名称", "chinese_name"),
                ("来源Sheet", "sheet_name"), ("类目", "category"),
                ("分销价格", "distribution_price"), ("库存数量", "inventory"),
                ("重量", "weight"), ("尺寸", "dimensions"), ("品牌", "brand"),
            ]

        # 最前面加本地行号列
        return [("#", "#")] + data_columns

    def _find_image_column(self) -> int:
        """查找图片列索引（名称含'图片'或'image'）"""
        for i, (header, key) in enumerate(self._columns):
            h_lower = header.lower()
            if "图片" in h_lower or "image" in h_lower:
                return i
        return -1

    def _populate_sheet_filter(self):
        sheets = sorted(set(
            item.get("sheet_name", "") for item in self._raw_data if item.get("sheet_name")
        ))
        current = self._sheet_filter.currentText()
        self._sheet_filter.blockSignals(True)
        self._sheet_filter.clear()
        self._sheet_filter.addItem("全部Sheet")
        self._sheet_filter.addItems(sheets)
        idx = self._sheet_filter.findText(current)
        if idx >= 0:
            self._sheet_filter.setCurrentIndex(idx)
        self._sheet_filter.blockSignals(False)

    def _populate_table(self):
        """填充表格数据"""
        cols = self._columns
        data = self._filtered_data()

        # 阻塞信号：防止 setItem 触发 cellChanged → _on_cell_changed 卡死
        self._table.blockSignals(True)

        self._table.setRowCount(len(data))
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels([c[0] for c in cols])

        for i, item in enumerate(data):
            for j, (header, key) in enumerate(cols):
                if header == "#":
                    # 本地行号（不可编辑）
                    cell = QTableWidgetItem(str(i + 1))
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    cell.setData(Qt.ItemDataRole.UserRole, {"id": item.get("id")})
                    self._table.setItem(i, j, cell)
                elif j == self._img_col_idx:
                    raw = item.get("raw", {})
                    token = raw.get(header, "") or item.get("image_file_token", "")
                    local_path = item.get("image_local_path", "")
                    if token and not local_path:
                        local_path = os.path.join(_IMAGE_DIR, f"{token}.png")
                    cell = QTableWidgetItem(local_path)
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    cell.setData(Qt.ItemDataRole.UserRole, {"id": item.get("id")})
                    self._table.setItem(i, j, cell)
                else:
                    raw = item.get("raw", {})
                    val = raw.get(header, "")
                    cell = QTableWidgetItem(self._format_val(val))
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell.setData(Qt.ItemDataRole.UserRole, {"id": item.get("id")})
                    # 数据列可双击编辑

                    # 库存状态 / 库存信息列 → 高亮色
                    self._apply_stock_highlight(cell, header, val)
                    self._table.setItem(i, j, cell)

        # 列宽自适应内容
        self._table.resizeColumnsToContents()
        # 确保最小宽度
        for j in range(len(cols)):
            if self._table.columnWidth(j) < 50:
                self._table.setColumnWidth(j, 50)
        self._table.horizontalHeader().setStretchLastSection(True)

        # 行高
        row_h = 56 if self._img_col_idx >= 0 else 36
        for i in range(self._table.rowCount()):
            self._table.setRowHeight(i, row_h)

        # 图片 delegate
        if self._img_col_idx >= 0:
            self._table.setItemDelegateForColumn(self._img_col_idx, self._thumb_delegate)

        # 应用列显隐
        self._apply_column_visibility()

        # # 列不可隐藏
        self._table.setColumnHidden(0, False)

        # 恢复信号
        self._table.blockSignals(False)

        self._lbl_count.setText(f"共 {len(data)} 条")

    # ═══ 库存状态高亮 ═══════════════════════════

    # 库存状态关键词 → (背景色, 文字色)  深浅色主题通用
    _STOCK_COLORS = {
        "货源充足":   ("#166534", "#4ADE80"),  # 深绿底 亮绿字
        "停止上架":   ("#7F1D1D", "#FCA5A5"),  # 深红底 亮红字
        "货源紧缺":   ("#713F12", "#FDE047"),  # 深黄底 亮黄字
        "等待补货":   ("#7C2D12", "#FB923C"),  # 深橘底 亮橘字
    }
    _STOCK_COLOR_CACHE: dict = {}  # val_str → (QColor_bg, QColor_fg)
    # 库存状态相关的列名关键词
    _STOCK_COL_KEYWORDS = {"库存信息", "库存状态", "inventory_status", "stock_status"}

    def _is_stock_column(self, header: str) -> bool:
        """判断列名是否属于库存状态列"""
        h_lower = header.lower()
        return any(kw in h_lower for kw in self._STOCK_COL_KEYWORDS)

    def _apply_stock_highlight(self, cell: QTableWidgetItem, header: str, value):
        """根据库存状态值设置单元格背景色"""
        if not self._is_stock_column(header):
            return
        val_str = str(value).strip()
        hex_colors = self._STOCK_COLORS.get(val_str)
        if hex_colors:
            if val_str not in ProductViewer._STOCK_COLOR_CACHE:
                ProductViewer._STOCK_COLOR_CACHE[val_str] = (QColor(hex_colors[0]), QColor(hex_colors[1]))
            bg, fg = ProductViewer._STOCK_COLOR_CACHE[val_str]
            cell.setBackground(bg)
            cell.setForeground(fg)

    # ═══ 列显隐设置 ═══════════════════════════

    def _load_column_visibility(self):
        """从 DB 加载隐藏列设置"""
        self._hidden_cols.clear()
        try:
            raw = self.db.get_config(self._COL_VIS_KEY, "")
            if raw:
                self._hidden_cols = set(json.loads(raw))
        except Exception:
            pass

    def _save_column_visibility(self):
        """保存隐藏列设置到 DB"""
        try:
            self.db.save_config(self._COL_VIS_KEY,
                                json.dumps(list(self._hidden_cols), ensure_ascii=False))
        except Exception as e:
            logger.warning(f"保存列设置失败: {e}")

    def _apply_column_visibility(self):
        """应用列显隐"""
        for j, (header, key) in enumerate(self._columns):
            if header == "#":
                self._table.setColumnHidden(j, False)
            else:
                self._table.setColumnHidden(j, header in self._hidden_cols)

    def _show_column_settings(self):
        """弹出列设置菜单 — 勾选显示/隐藏"""
        menu = QMenu(self)
        menu.setWindowTitle("列设置")

        for j, (header, key) in enumerate(self._columns):
            if header == "#":
                continue  # # 列始终显示
            action = QAction(header, self)
            action.setCheckable(True)
            action.setChecked(header not in self._hidden_cols)
            action.triggered.connect(lambda checked, h=header: self._toggle_column(h, checked))
            menu.addAction(action)

        menu.exec(self._btn_columns.mapToGlobal(
            self._btn_columns.rect().bottomLeft()))

    def _toggle_column(self, header: str, visible: bool):
        """切换列显示/隐藏"""
        if visible:
            self._hidden_cols.discard(header)
        else:
            self._hidden_cols.add(header)
        self._apply_column_visibility()
        self._save_column_visibility()

    # ═══ 筛选 ═══════════════════════════════════

    def _filtered_data(self) -> list:
        """根据当前筛选条件过滤数据"""
        data = list(self._raw_data)

        # Sheet 筛选
        sheet = self._sheet_filter.currentText()
        if sheet and sheet != "全部Sheet":
            data = [d for d in data if d.get("sheet_name") == sheet]

        # 搜索框筛选
        search = self._search_box.text().strip().lower()
        if search:
            filtered = []
            for d in data:
                raw = d.get("raw", {})
                all_text = " ".join(str(v).lower() for v in raw.values())
                all_text += " " + d.get("sku_code", "").lower()
                all_text += " " + d.get("sheet_name", "").lower()
                if search in all_text:
                    filtered.append(d)
            data = filtered

        # Excel 风格列筛选（多值勾选）
        for col_idx, allowed_values in self._col_filters.items():
            if not allowed_values or col_idx >= len(self._columns):
                continue
            header = self._columns[col_idx][0]
            if header == "#":
                continue
            data = [d for d in data
                    if str(d.get("raw", {}).get(header, "")).strip() in allowed_values]

        # 排序
        if 0 <= self._sort_col < len(self._columns):
            header = self._columns[self._sort_col][0]
            reverse = self._sort_order == Qt.SortOrder.DescendingOrder
            if header == "#":
                # 行号不参与排序（它是序号）
                pass
            else:
                def sort_key(d):
                    val = d.get("raw", {}).get(header, "")
                    try:
                        return (0, float(val))
                    except (ValueError, TypeError):
                        return (1, str(val))
                data.sort(key=sort_key, reverse=reverse)

        return data

    # ═══ 排序 ═══════════════════════════════════

    def _on_header_clicked(self, col_idx: int):
        """点击表头切换排序"""
        # # 列不排序
        if col_idx == 0:
            return

        if self._sort_col == col_idx:
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                self._sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.SortOrder.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.SortOrder.AscendingOrder

        if self._sort_col >= 0:
            header = self._table.horizontalHeader()
            header.setSortIndicator(self._sort_col, self._sort_order)

        self._populate_table()

    # ═══ 表头右键筛选 ═══════════════════════════

    def _on_header_context_menu(self, pos: QPoint):
        """右键表头 — 弹出列筛选菜单"""
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0 or col_idx >= len(self._columns):
            return
        header_name = self._columns[col_idx][0]
        if header_name == "#":
            return
        global_pos = self._table.horizontalHeader().mapToGlobal(pos)
        self._show_column_filter_menu(col_idx, global_pos)

    def _show_column_filter_menu(self, col_idx: int, global_pos: QPoint):
        """弹出指定列的筛选菜单"""
        if col_idx < 0 or col_idx >= len(self._columns):
            return

        header_name = self._columns[col_idx][0]
        if header_name == "#":
            return  # 行号列不筛选

        # 收集该列的唯一值
        unique_values = sorted(set(
            str(item.get("raw", {}).get(header_name, "")).strip()
            for item in self._raw_data
        ))

        if not unique_values:
            return

        menu = QMenu(self)
        menu.setWindowTitle(f"筛选: {header_name}")

        # 全选
        select_all_action = QAction("全选", self)
        menu.addAction(select_all_action)

        # 清除筛选
        clear_action = QAction("清除筛选", self)
        menu.addAction(clear_action)

        menu.addSeparator()

        # 当前已选的值
        current_allowed = self._col_filters.get(col_idx)

        # 值列表（多选）
        group = QActionGroup(self)
        group.setExclusive(False)

        val_actions = {}
        for val in unique_values:
            display = val if val else "(空)"
            action = QAction(display, self)
            action.setCheckable(True)
            if current_allowed is None:
                action.setChecked(True)
            else:
                action.setChecked(val in current_allowed)
            menu.addAction(action)
            group.addAction(action)
            val_actions[action] = val

        menu.addSeparator()

        # "应用" 按钮
        apply_action = QAction("✓ 应用筛选", self)
        menu.addAction(apply_action)

        # 执行菜单
        chosen = menu.exec(global_pos)

        if chosen == apply_action:
            # 收集勾选的值
            checked_values = set()
            for action, val in val_actions.items():
                if action.isChecked():
                    checked_values.add(val)

            if len(checked_values) == len(unique_values) or not checked_values:
                # 全选 = 不筛选
                self._col_filters.pop(col_idx, None)
            else:
                self._col_filters[col_idx] = checked_values

            self._populate_table()

        elif chosen == select_all_action:
            self._col_filters.pop(col_idx, None)
            self._populate_table()

        elif chosen == clear_action:
            self._col_filters.pop(col_idx, None)
            self._populate_table()

    def _on_search_text_changed(self, text):
        """搜索防抖：空字符串立即触发，否则延迟300ms"""
        if not text:
            self._search_timer.stop()
            self._apply_all_filters()
        else:
            self._search_timer.start()

    def _apply_all_filters(self):
        """搜索框或Sheet下拉变化时重新填充表格"""
        self._populate_table()

    def _clear_all_filters(self):
        """清除所有筛选"""
        self._col_filters.clear()
        self._sort_col = -1
        # 安全清除排序指示器
        header = self._table.horizontalHeader()
        if header.isSortIndicatorShown():
            header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        # blockSignals 防止 clear/setCurrentIndex 触发 _apply_all_filters
        self._search_box.blockSignals(True)
        self._search_box.clear()
        self._search_box.blockSignals(False)
        self._sheet_filter.blockSignals(True)
        self._sheet_filter.setCurrentIndex(0)
        self._sheet_filter.blockSignals(False)
        self._populate_table()

    # ═══ 单元格编辑保存 ═════════════════════════

    def _on_cell_changed(self, row: int, col: int):
        """单元格编辑后自动保存到数据库"""
        item = self._table.item(row, col)
        if not item:
            return
        if col < 0 or col >= len(self._columns):
            return

        header = self._columns[col][0]
        if header == "#":
            return  # 行号不可编辑

        # 获取产品 ID（UserRole 仅存 {"id": ...}）
        row_meta = item.data(Qt.ItemDataRole.UserRole)
        if not row_meta:
            return
        product_id = row_meta.get("id")
        if not product_id:
            return

        # 从过滤后的数据中找到对应行，更新内存
        data = self._filtered_data()
        if row < 0 or row >= len(data):
            return
        row_data = data[row]

        new_value = item.text()
        try:
            self.db.update_product_raw_field(product_id, header, new_value)
            # 同步更新内存中的 raw 数据
            raw = row_data.get("raw", {})
            raw[header] = new_value
            row_data["raw"] = raw
            logger.debug(f"已保存: 产品#{product_id} {header} = {new_value}")
        except Exception as e:
            logger.warning(f"保存失败: {e}")

    # ═══ 单元格右键菜单 ═════════════════════════

    def _on_cell_context_menu(self, pos):
        item = self._table.itemAt(pos)
        if not item:
            return

        col = self._table.columnAt(pos.x())
        menu = QMenu(self)

        copy_action = menu.addAction("复制")
        action = menu.exec(self._table.mapToGlobal(pos))
        if action == copy_action:
            QApplication.clipboard().setText(item.text())

    # ═══ 其他 ═══════════════════════════════════

    def refresh(self):
        self._loaded = False
        self.load_data()

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击单元格时复制其内容到剪贴板。"""
        item = self._table.item(row, col)
        if item and item.text():
            QApplication.clipboard().setText(item.text())
            rect = self._table.visualItemRect(item)
            QToolTip.showText(
                self._table.viewport().mapToGlobal(rect.center()),
                f"已复制: {item.text()[:50]}",
                self._table,
                rect,
                1500
            )

    @property
    def table(self):
        return self._table

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            item = self._table.currentItem()
            if item:
                QApplication.clipboard().setText(item.text())
        else:
            super().keyPressEvent(event)

    @staticmethod
    def _format_val(val) -> str:
        if val is None:
            return "-"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)


# ── 佣金表格 ──────────────────────────────────────


class CommissionViewer(QWidget):
    """佣金数据浏览面板 — 动态多表、右键筛选、排序、搜索"""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._loaded = False
        self._raw_data = []        # list of tuples from get_commission_table_data()
        self._columns = []         # [(display_header, db_col_name), ...]
        self._current_table = ""   # currently selected table name
        self._sort_col = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._col_filters = {}     # col_idx → set(allowed_values)
        self._build_ui()

    # ═══ UI 构建 ═══════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("搜索:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("全表搜索...")
        self._search_box.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_all_filters)
        self._search_box.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self._search_box, stretch=1)

        self._table_filter = QComboBox()
        self._table_filter.setMinimumWidth(180)
        self._table_filter.currentIndexChanged.connect(self._on_table_changed)
        toolbar.addWidget(QLabel("表格:"))
        toolbar.addWidget(self._table_filter)

        self._btn_clear_filter = QPushButton("清除筛选")
        self._btn_clear_filter.setFixedHeight(28)
        self._btn_clear_filter.clicked.connect(self._clear_all_filters)
        toolbar.addWidget(self._btn_clear_filter)

        toolbar.addStretch()
        self._lbl_count = QLabel("共 0 条")
        self._lbl_count.setProperty("class", "stat-label")
        toolbar.addWidget(self._lbl_count)

        layout.addLayout(toolbar)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setSortingEnabled(False)  # 自己控制排序

        header = self._table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        layout.addWidget(self._table)

    # ═══ 数据加载 ═══════════════════════════════

    def load_data(self):
        """从 DB 加载佣金表元数据，填充下拉框"""
        tables = self.db.get_commission_tables()

        prev_table = self._current_table

        self._table_filter.blockSignals(True)
        self._table_filter.clear()
        for t in tables:
            shop_label = "本土" if t.shop_type == "local" else "跨境"
            label = f"{t.platform.upper()}{shop_label} ({t.row_count:,}条)"
            self._table_filter.addItem(label, t.table_name)
        self._table_filter.blockSignals(False)

        # 尝试恢复之前选中的表
        restored = False
        if prev_table:
            for i in range(self._table_filter.count()):
                if self._table_filter.itemData(i) == prev_table:
                    self._table_filter.setCurrentIndex(i)
                    restored = True
                    break

        # 加载第一个可用表（或恢复的表）
        if self._table_filter.count() > 0:
            self._load_table_data(self._table_filter.currentData())

        self._loaded = True

    def _load_table_data(self, table_name: str):
        """加载指定佣金表的数据和列定义"""
        if not table_name:
            return
        self._current_table = table_name

        # 获取该表的元数据
        tables = self.db.get_commission_tables()
        meta = next((t for t in tables if t.table_name == table_name), None)
        if not meta:
            return

        # 从元数据构建列定义
        headers = json.loads(meta.column_headers)   # ["品类", "商品", "WB仓库，%", ...]
        rate_cols = json.loads(meta.rate_columns)     # ["rate_col_0", "rate_col_1", ...]

        self._columns = []
        self._columns.append(("品类", "category"))
        self._columns.append(("商品", "product"))
        for i, rate_col in enumerate(rate_cols):
            display_name = headers[i + 2] if i + 2 < len(headers) else rate_col
            self._columns.append((display_name, rate_col))

        # 加载数据
        self._raw_data = self.db.get_commission_table_data(table_name)

        # 重置筛选状态并填充表格
        self._col_filters.clear()
        self._sort_col = -1
        self._populate_table()

    # ═══ 表格填充 ═══════════════════════════════

    def _populate_table(self):
        """根据当前筛选条件填充表格"""
        data = self._filtered_data()

        self._table.blockSignals(True)

        self._table.setRowCount(len(data))
        self._table.setColumnCount(len(self._columns))
        self._table.setHorizontalHeaderLabels([c[0] for c in self._columns])

        for i, row in enumerate(data):
            for j, (_header, col_key) in enumerate(self._columns):
                val = self._get_cell_value(row, col_key)
                raw_val = self._get_raw_value(row, col_key)

                cell = QTableWidgetItem()
                if isinstance(raw_val, float):
                    cell.setText(f"{raw_val:.1f}" if raw_val != 0 else "0")
                else:
                    cell.setText(str(val))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(i, j, cell)

        # 列宽自适应内容
        self._table.resizeColumnsToContents()
        for j in range(len(self._columns)):
            if self._table.columnWidth(j) < 50:
                self._table.setColumnWidth(j, 50)
        self._table.horizontalHeader().setStretchLastSection(True)

        self._table.blockSignals(False)

        self._lbl_count.setText(f"共 {len(data)} 条")

    # ═══ 辅助方法 ═══════════════════════════════

    def _get_raw_value(self, row, col_key):
        """提取行元组中的原始值（保留类型信息）"""
        if col_key == "category":
            return row[1] if len(row) > 1 else ""
        elif col_key == "product":
            return row[2] if len(row) > 2 else ""
        else:
            rate_idx = int(col_key.split("_")[-1])
            return row[3 + rate_idx] if len(row) > 3 + rate_idx else 0.0

    def _get_cell_value(self, row, col_key) -> str:
        """提取行元组中的显示字符串值"""
        raw = self._get_raw_value(row, col_key)
        return str(raw) if raw is not None else ""

    # ═══ 筛选与排序 ═══════════════════════════════

    def _filtered_data(self) -> list:
        """根据搜索、列筛选、排序过滤数据"""
        data = list(self._raw_data)

        # 搜索框筛选
        search = self._search_box.text().strip().lower()
        if search:
            filtered = []
            for row in data:
                row_text = " ".join(str(v).lower() for v in row)
                if search in row_text:
                    filtered.append(row)
            data = filtered

        # Excel 风格列筛选（多值勾选）
        for col_idx, allowed_values in self._col_filters.items():
            if not allowed_values or col_idx >= len(self._columns):
                continue
            col_key = self._columns[col_idx][1]
            data = [row for row in data
                    if self._get_cell_value(row, col_key) in allowed_values]

        # 排序
        if 0 <= self._sort_col < len(self._columns):
            col_key = self._columns[self._sort_col][1]
            reverse = self._sort_order == Qt.SortOrder.DescendingOrder

            def sort_key(row):
                raw = self._get_raw_value(row, col_key)
                try:
                    return (0, float(raw))
                except (ValueError, TypeError):
                    return (1, str(raw))
            data.sort(key=sort_key, reverse=reverse)

        return data

    # ═══ 排序 ═════════════════════════════════

    def _on_header_clicked(self, col_idx: int):
        """点击表头切换排序"""
        if self._sort_col == col_idx:
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                self._sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._sort_col = -1
                self._sort_order = Qt.SortOrder.AscendingOrder
        else:
            self._sort_col = col_idx
            self._sort_order = Qt.SortOrder.AscendingOrder

        if self._sort_col >= 0:
            header = self._table.horizontalHeader()
            header.setSortIndicator(self._sort_col, self._sort_order)

        self._populate_table()

    # ═══ 表头右键筛选 ═══════════════════════════

    def _on_header_context_menu(self, pos: QPoint):
        """右键表头 — 弹出列筛选菜单"""
        col_idx = self._table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0 or col_idx >= len(self._columns):
            return
        global_pos = self._table.horizontalHeader().mapToGlobal(pos)
        self._show_column_filter_menu(col_idx, global_pos)

    def _show_column_filter_menu(self, col_idx: int, global_pos: QPoint):
        """弹出指定列的筛选菜单"""
        if col_idx < 0 or col_idx >= len(self._columns):
            return

        header_name = self._columns[col_idx][0]
        col_key = self._columns[col_idx][1]

        # 收集该列的唯一值
        unique_values = sorted(set(
            self._get_cell_value(row, col_key)
            for row in self._raw_data
        ))

        if not unique_values:
            return

        menu = QMenu(self)
        menu.setWindowTitle(f"筛选: {header_name}")

        # 全选
        select_all_action = QAction("全选", self)
        menu.addAction(select_all_action)

        # 清除筛选
        clear_action = QAction("清除筛选", self)
        menu.addAction(clear_action)

        menu.addSeparator()

        # 当前已选的值
        current_allowed = self._col_filters.get(col_idx)

        # 值列表（多选）
        group = QActionGroup(self)
        group.setExclusive(False)

        val_actions = {}
        for val in unique_values:
            display = val if val else "(空)"
            action = QAction(display, self)
            action.setCheckable(True)
            if current_allowed is None:
                action.setChecked(True)
            else:
                action.setChecked(val in current_allowed)
            menu.addAction(action)
            group.addAction(action)
            val_actions[action] = val

        menu.addSeparator()

        # "应用" 按钮
        apply_action = QAction("✓ 应用筛选", self)
        menu.addAction(apply_action)

        # 执行菜单
        chosen = menu.exec(global_pos)

        if chosen == apply_action:
            checked_values = set()
            for action, val in val_actions.items():
                if action.isChecked():
                    checked_values.add(val)

            if len(checked_values) == len(unique_values) or not checked_values:
                self._col_filters.pop(col_idx, None)
            else:
                self._col_filters[col_idx] = checked_values

            self._populate_table()

        elif chosen == select_all_action:
            self._col_filters.pop(col_idx, None)
            self._populate_table()

        elif chosen == clear_action:
            self._col_filters.pop(col_idx, None)
            self._populate_table()

    # ═══ 工具栏操作 ═══════════════════════════════

    def _on_table_changed(self, index):
        """切换佣金表"""
        table_name = self._table_filter.currentData()
        if table_name:
            self._load_table_data(table_name)

    def _on_search_text_changed(self, text):
        """搜索防抖：空字符串立即触发，否则延迟300ms"""
        if not text:
            self._search_timer.stop()
            self._apply_all_filters()
        else:
            self._search_timer.start()

    def _apply_all_filters(self):
        """搜索框变化时重新填充表格"""
        self._populate_table()

    def _clear_all_filters(self):
        """清除所有筛选"""
        self._col_filters.clear()
        self._sort_col = -1
        header = self._table.horizontalHeader()
        if header.isSortIndicatorShown():
            header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._search_box.blockSignals(True)
        self._search_box.clear()
        self._search_box.blockSignals(False)
        self._populate_table()

    def refresh(self):
        self._loaded = False
        self.load_data()

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击单元格时复制其内容到剪贴板。"""
        item = self._table.item(row, col)
        if item and item.text():
            QApplication.clipboard().setText(item.text())
            rect = self._table.visualItemRect(item)
            QToolTip.showText(
                self._table.viewport().mapToGlobal(rect.center()),
                f"已复制: {item.text()[:50]}",
                self._table,
                rect,
                1500
            )

