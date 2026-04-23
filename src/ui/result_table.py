# -*- coding: utf-8 -*-
"""结果表格组件 - QTableWidget 带颜色标记"""

from typing import Optional

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.services.excel_service import ProductRow


# 颜色常量
COLOR_PROFIT = QColor(230, 247, 230)    # #e6f7e6
COLOR_LOSS = QColor(255, 230, 230)      # #ffe6e6
COLOR_UNMATCHED = QColor(255, 230, 230) # #ffe6e6 (浅红色)
COLOR_HEADER_BG = QColor(0, 21, 41)     # #001529
COLOR_HEADER_FG = QColor(255, 255, 255)

# 列定义: (key, title, width)
COLUMNS = [
    ("seller_sku", "卖家货号", 180),
    ("category", "类目", 80),
    ("current_price", "当前价格", 80),
    ("current_discount", "当前折扣", 70),
    ("discounted_price", "折后价格", 80),
    ("distribution_price", "分销价格", 90),
    ("shipping_fee", "运费", 70),
    ("inventory", "库存", 70),
    ("cost_matched", "商品成本匹配", 90),
    ("commission_source", "佣金匹配状态", 140),
    ("product_cost", "产品成本", 80),
    ("commission_rate", "佣金率", 60),
    ("breakeven", "盈亏平衡", 80),
    ("profit", "盈亏额", 80),
    ("max_discount", "建议折扣", 70),
    ("min_price", "新价格", 80),
]


class ResultTable(QTableWidget):
    """结果表格 - 颜色标记盈亏"""

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self._setup_headers()
        self._results = []

    def _setup_headers(self):
        headers = [col[1] for col in COLUMNS]
        self.setHorizontalHeaderLabels(headers)
        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for i, (_, _, w) in enumerate(COLUMNS):
            header.resizeSection(i, w)
        # header and grid styles handled by QSS (#resultTable)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(True)

    def load_results(self, results: list):
        """Load calculation results into the table.
        Each result is a dict with keys matching COLUMNS."""
        self._results = results
        self.setRowCount(len(results))
        for row_idx, row_data in enumerate(results):
            cost_matched = row_data.get("cost_matched", False)
            row_color = self._row_color(cost_matched, row_data.get("profit"))

            for col_idx, (key, _, _) in enumerate(COLUMNS):
                val = row_data.get(key, "")
                item = QTableWidgetItem(self._format_value(key, val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if row_color:
                    item.setBackground(row_color)
                # 盈亏额特殊文字颜色
                if key == "profit" and isinstance(val, (int, float)):
                    if val > 0:
                        item.setForeground(QColor(56, 158, 13))
                    elif val < 0:
                        item.setForeground(QColor(207, 19, 34))
                self.setItem(row_idx, col_idx, item)

        self.resizeColumnsToContents()
        # 恢复固定宽度
        for i, (_, _, w) in enumerate(COLUMNS):
            self.setColumnWidth(i, w)

    def _row_color(self, cost_matched: bool, profit) -> Optional[QColor]:
        if not cost_matched:
            return COLOR_UNMATCHED
        if isinstance(profit, (int, float)):
            if profit > 0:
                return COLOR_PROFIT
            elif profit < 0:
                return COLOR_LOSS
        return None

    def _format_value(self, key, val):
        if val is None:
            return "-"
        if key == "inventory":
            if val is None:
                return "-"
            try:
                return str(int(float(val)))
            except (ValueError, TypeError):
                return "-"
        # cost_matched: bool → ✅ / ❌
        if key == "cost_matched":
            return "✅" if val else "❌"
        # distribution_price: float → .2f format
        if key == "distribution_price":
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return "-"
        # commission_source: already a Chinese string
        if key == "commission_source":
            return str(val) if val else "-"
        # existing formatting for other columns
        if key in ("current_price", "discounted_price", "product_cost", "shipping_fee",
                    "breakeven", "profit", "min_price"):
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        if key in ("current_discount", "max_discount", "commission_rate"):
            try:
                v = int(float(val))
                return f"{v}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        return str(val) if val else "-"

    def get_results(self):
        return self._results

    def clear_results(self):
        self.setRowCount(0)
        self._results = []
