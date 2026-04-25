# -*- coding: utf-8 -*-
"""原始数据表格组件 — RawDataModel + RawTable。"""

from src.ui.table_base import BaseTableModel, BaseTableView


# ---------------------------------------------------------------------------
# RawDataModel
# ---------------------------------------------------------------------------

class RawDataModel(BaseTableModel):
    """原始数据表格模型，存储 list[dict]，通过 set_data_from_rows 接收 list[list]。"""

    COLUMNS = [
        ("row_number", "行号", 50),
        ("brand", "品牌", 80),
        ("category", "类目", 80),
        ("wb_article", "WB货号", 80),
        ("seller_sku", "卖家货号", 150),
        ("barcode", "条码", 80),
        ("wb_stock", "WB库存", 70),
        ("seller_stock", "卖家库存", 70),
        ("turnover", "周转率", 70),
        ("current_price", "当前价格", 80),
        ("current_discount", "当前折扣", 70),
        ("discounted_price", "折后价格", 80),
        ("new_price", "新价格", 80),
        ("new_discount", "新折扣", 70),
    ]

    def __init__(self, parent=None):
        super().__init__(self.COLUMNS, parent)

    def set_data_from_rows(self, rows: list[list]):
        """将 list[list] 转换为 list[dict] 并设置数据。"""
        keys = [c[0] for c in self.COLUMNS]
        dict_data = []
        for row in rows:
            d = {}
            for i, k in enumerate(keys):
                d[k] = row[i] if i < len(row) else None
            dict_data.append(d)
        self.set_data(dict_data)

    def _format_value(self, row: int, col: int) -> str:
        key = self._col_key(col)
        val = self._col_value(self._data[row], col)

        if key in ("current_discount", "new_discount"):
            if val is not None:
                try:
                    return f"{int(float(val))}%"
                except (ValueError, TypeError):
                    return "-"
            return "-"

        if key in ("current_price", "discounted_price", "new_price"):
            if val is not None:
                try:
                    return f"{float(val):.2f}"
                except (ValueError, TypeError):
                    return "-"
            return "-"

        if key == "turnover":
            if val:
                try:
                    return f"{float(val):.1f}"
                except (ValueError, TypeError):
                    return "-"
            return "-"

        if key in ("wb_stock", "seller_stock"):
            return str(val) if val is not None else "-"

        return str(val) if val is not None else "-"


# ---------------------------------------------------------------------------
# RawTable
# ---------------------------------------------------------------------------

class RawTable(BaseTableView):
    """原始数据表格视图，接受 list[list] 数据。"""

    def __init__(self, parent=None):
        model = RawDataModel()
        super().__init__(model, parent)
        self.setObjectName("rawTable")
        self._set_column_widths()

    def populate(self, data: list[list]):
        """接受 list[list] 数据（非 list[dict]）。"""
        self._model.set_data_from_rows(data)
        self._set_column_widths()
