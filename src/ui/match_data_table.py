# -*- coding: utf-8 -*-
"""匹配数据表格组件 — 显示中间匹配结果（SKU匹配、佣金匹配、库存状态等）"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QMenu
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QAction, QActionGroup

# 行背景颜色
COLOR_ROW_NO_SKU = QColor("#ffe6e6")      # 浅红色 — 未匹配SKU
COLOR_ROW_NO_CATEGORY = QColor("#fff3e0")  # 浅橘黄色 — 未匹配类目

# 库存状态颜色 (matching ProductViewer / result_table)
_STOCK_STATUS_COLORS = {
    "货源充足": ("#e6f7e6", "#1a7a1a"),
    "停止上架": ("#ffe6e6", "#c91a2a"),
    "货源紧缺": ("#fff3cd", "#856404"),
    "等待补货": ("#ffe8cc", "#b35900"),
}

# 列定义: (key, title, width)
COLUMNS = [
    ("row_number", "行号", 50),
    ("seller_sku", "卖家货号", 150),
    ("category", "类目", 80),
    ("sku_matched", "SKU匹配", 70),
    ("matched_product_id", "匹配产品ID", 100),
    ("product_category", "产品类目", 100),
    ("dimensions", "尺寸", 100),
    ("wb_stock", "WB库存", 70),
    ("seller_stock", "卖家库存", 70),
    ("inventory_status", "库存状态", 90),
    ("commission_rate", "佣金率", 70),
    ("category_matched", "类目匹配", 70),
    ("product_cost", "产品成本", 80),
    ("density", "密度(kg/L)", 90),
    ("weight", "包装重量(kg)", 100),
]


class MatchDataTable(QTableWidget):
    """匹配数据表格 — 显示SKU匹配、佣金匹配、库存等中间结果"""

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
        """Load match display data into the table.

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
            # Determine row background color based on match status
            sku_ok = row_data.get("sku_matched", True)
            cat_ok = row_data.get("category_matched", True)
            if not sku_ok:
                row_bg = COLOR_ROW_NO_SKU
            elif not cat_ok:
                row_bg = COLOR_ROW_NO_CATEGORY
            else:
                row_bg = None

            for col_idx, (key, _, _) in enumerate(COLUMNS):
                val = row_data.get(key, "")
                item = QTableWidgetItem(self._format_value(key, val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Apply row background first
                if row_bg:
                    item.setBackground(row_bg)
                # Inventory status cell color overrides row color
                if key == "inventory_status" and val:
                    colors = _STOCK_STATUS_COLORS.get(str(val))
                    if colors:
                        item.setBackground(QColor(colors[0]))
                        item.setForeground(QColor(colors[1]))
                self.setItem(row_idx, col_idx, item)

    def _format_value(self, key, val):
        if val is None:
            return "-"
        # Boolean fields
        if key in ("sku_matched", "category_matched"):
            if val is True:
                return "✅"
            if val is False:
                return "❌"
            return str(val)
        # Inventory status
        if key == "inventory_status":
            return str(val) if val else "-"
        # Commission rate
        if key == "commission_rate":
            try:
                return f"{int(float(val))}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        # Product cost
        if key == "product_cost":
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        # Density field
        if key == "density":
            try:
                val_f = float(val)
                return f"{val_f:.3f}" if val_f > 0 else "-"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        # Weight field
        if key == "weight":
            try:
                val_f = float(val)
                return f"{val_f:.3f}" if val_f > 0 else "-"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        # Stock fields (from import data)
        if key in ("wb_stock", "seller_stock"):
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
