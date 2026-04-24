# -*- coding: utf-8 -*-
"""计算数据表格组件 — 显示详细计算明细（运费、盈亏平衡、盈亏额等）"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QAction, QActionGroup

# 列定义: (key, title, width)
COLUMNS = [
    ("row_number", "行号", 50),
    ("seller_sku", "卖家货号", 150),
    ("current_price", "当前价格", 80),
    ("discounted_price", "折后价格", 80),
    ("product_cost", "产品成本", 80),
    ("shipping_fee", "运费", 70),
    ("breakeven", "盈亏平衡点", 90),
    ("profit", "盈亏额", 80),
    ("max_discount", "保本折扣", 70),
    ("target_discount", "目标折扣", 70),
    ("min_price", "保本价格", 80),
    ("target_price", "目标价格", 80),
]


class CalcDataTable(QTableWidget):
    """计算数据表格 — 显示详细的计算明细"""

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self._setup_headers()
        self._raw_display_data = []

        # 筛选/排序状态
        self._sort_col = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._col_filters = {}

        header = self.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

    def _setup_headers(self):
        headers = [col[1] for col in COLUMNS]
        self.setHorizontalHeaderLabels(headers)
        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(True)

    def populate(self, data: list):
        """Load calc display data into the table.

        Each item is a dict with keys matching COLUMNS.
        """
        self._raw_display_data = data
        self._apply_filters_and_populate()

    def _filtered_data(self) -> list:
        data = list(self._raw_display_data)
        for col_idx, allowed_values in self._col_filters.items():
            if not allowed_values or col_idx >= len(COLUMNS):
                continue
            key = COLUMNS[col_idx][0]
            data = [d for d in data if str(d.get(key, "")).strip() in allowed_values]
        if 0 <= self._sort_col < len(COLUMNS):
            key = COLUMNS[self._sort_col][0]
            reverse = self._sort_order == Qt.SortOrder.DescendingOrder
            def sort_key(d):
                val = d.get(key, "")
                try:
                    return (0, float(val))
                except (ValueError, TypeError):
                    return (1, str(val))
            data.sort(key=sort_key, reverse=reverse)
        return data

    def _apply_filters_and_populate(self):
        data = self._filtered_data()
        self.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            for col_idx, (key, _, _) in enumerate(COLUMNS):
                val = row_data.get(key, "")
                item = QTableWidgetItem(self._format_value(key, val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Profit text color: green if positive, red if negative
                if key == "profit" and isinstance(val, (int, float)):
                    if val > 0:
                        item.setForeground(QColor(56, 158, 13))
                    elif val < 0:
                        item.setForeground(QColor(207, 19, 34))
                self.setItem(row_idx, col_idx, item)

    def _format_value(self, key, val):
        if val is None:
            return "-"
        # Percentage fields
        if key in ("max_discount", "target_discount"):
            try:
                return f"{int(float(val))}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        # Monetary / float fields
        if key in ("current_price", "discounted_price", "product_cost",
                    "shipping_fee", "breakeven", "profit", "min_price",
                    "target_price"):
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        return str(val) if val is not None and val != "" else "-"

    def _on_header_clicked(self, col_idx: int):
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
            self.horizontalHeader().setSortIndicator(self._sort_col, self._sort_order)
        self._apply_filters_and_populate()

    def _on_header_context_menu(self, pos):
        col_idx = self.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0 or col_idx >= len(COLUMNS):
            return
        global_pos = self.horizontalHeader().mapToGlobal(pos)
        self._show_column_filter_menu(col_idx, global_pos)

    def _show_column_filter_menu(self, col_idx: int, global_pos):
        key = COLUMNS[col_idx][0]
        header_name = COLUMNS[col_idx][1]
        unique_values = sorted(set(
            str(d.get(key, "")).strip()
            for d in self._raw_display_data
        ))
        if not unique_values:
            return
        menu = QMenu(self)
        menu.setWindowTitle(f"筛选: {header_name}")
        select_all_action = QAction("全选", self)
        clear_action = QAction("清除筛选", self)
        menu.addAction(select_all_action)
        menu.addAction(clear_action)
        menu.addSeparator()
        current_allowed = self._col_filters.get(col_idx)
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
        apply_action = QAction("✓ 应用筛选", self)
        menu.addAction(apply_action)
        chosen = menu.exec(global_pos)
        if chosen == apply_action:
            checked_values = set(v for a, v in val_actions.items() if a.isChecked())
            if len(checked_values) == len(unique_values) or not checked_values:
                self._col_filters.pop(col_idx, None)
            else:
                self._col_filters[col_idx] = checked_values
            self._apply_filters_and_populate()
        elif chosen in (select_all_action, clear_action):
            self._col_filters.pop(col_idx, None)
            self._apply_filters_and_populate()

    def clear_data(self):
        self.setRowCount(0)
        self._raw_display_data = []
        self._col_filters.clear()
        self._sort_col = -1
