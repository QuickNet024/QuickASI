# -*- coding: utf-8 -*-
"""Comprehensive unit tests for all 4 table models + proxy model.

Covers: BaseTableModel, MatchDataModel, CalcDataModel, ResultModel,
        RawDataModel, ColumnFilterProxyModel.
"""

import sys
import gc
import time

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.ui.table_base import BaseTableModel, ColumnFilterProxyModel
from src.ui.match_data_table import MatchDataModel
from src.ui.calc_data_table import CalcDataModel
from src.ui.result_table import ResultModel
from src.ui.raw_table import RawDataModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for all model tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Helpers — column key lookup
# ---------------------------------------------------------------------------

def _col_index(model, key: str) -> int:
    for i, (k, _, _) in enumerate(model.COLUMNS):
        if k == key:
            return i
    raise KeyError(f"Column key '{key}' not found")


# ═══════════════════════════════════════════════════════════════════════════
#  1. BaseTableModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBaseTableModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.columns = [("name", "名称", 80), ("value", "值", 80), ("extra", "额外", 80)]
        self.model = BaseTableModel(self.columns)
        # Provide a minimal _format_value so we can instantiate
        self.model._format_value = lambda row, col: str(
            self.model._col_value(self.model._data[row], col) or "-"
        )

    def test_set_data_updates_row_count(self):
        data = [{"name": "A", "value": 1}, {"name": "B", "value": 2}]
        self.model.set_data(data)
        assert self.model.rowCount() == 2

    def test_set_data_returns_correct_display(self):
        self.model.set_data([{"name": "A", "value": 10}])
        idx = self.model.index(0, 0)
        assert self.model.data(idx, Qt.ItemDataRole.DisplayRole) == "A"
        idx2 = self.model.index(0, 1)
        assert self.model.data(idx2, Qt.ItemDataRole.DisplayRole) == "10"

    def test_update_columns_preserves_other_keys(self):
        self.model.set_data([{"name": "A", "value": 10, "extra": "keep"}])
        self.model.update_columns({"value"}, [{"value": 99}])
        idx = self.model.index(0, 1)
        assert self.model.data(idx, Qt.ItemDataRole.DisplayRole) == "99"
        # "name" and "extra" should still be there
        assert self.model._data[0]["name"] == "A"
        assert self.model._data[0]["extra"] == "keep"

    def test_clear_columns_sets_none(self):
        self.model.set_data([{"name": "A", "value": 10}])
        self.model.clear_columns({"value"})
        assert self.model._data[0]["value"] is None

    def test_clear_data_empties_model(self):
        self.model.set_data([{"name": "A"}, {"name": "B"}])
        self.model.clear_data()
        assert self.model.rowCount() == 0

    def test_header_data_returns_titles(self):
        assert self.model.headerData(0, Qt.Orientation.Horizontal) == "名称"
        assert self.model.headerData(1, Qt.Orientation.Horizontal) == "值"

    def test_header_data_vertical_returns_row_number(self):
        assert self.model.headerData(0, Qt.Orientation.Vertical) == 1
        assert self.model.headerData(3, Qt.Orientation.Vertical) == 4

    def test_text_alignment_center(self):
        self.model.set_data([{"name": "A"}])
        idx = self.model.index(0, 0)
        assert self.model.data(idx, Qt.ItemDataRole.TextAlignmentRole) == Qt.AlignmentFlag.AlignCenter

    def test_header_alignment_center(self):
        assert self.model.headerData(0, Qt.Orientation.Horizontal,
                                      Qt.ItemDataRole.TextAlignmentRole) == Qt.AlignmentFlag.AlignCenter

    def test_column_count(self):
        assert self.model.columnCount() == 3


# ═══════════════════════════════════════════════════════════════════════════
#  2. MatchDataModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchDataModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = MatchDataModel()

    def _display(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.DisplayRole)

    def _bg(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.BackgroundRole)

    def _fg(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.ForegroundRole)

    def test_bool_formatting_true(self):
        self.model.set_data([{"seller_sku": "SKU1", "sku_matched": True, "category_matched": True}])
        assert self._display(0, "sku_matched") == "✅"
        assert self._display(0, "category_matched") == "✅"

    def test_bool_formatting_false(self):
        self.model.set_data([{"seller_sku": "SKU1", "sku_matched": False, "category_matched": False}])
        assert self._display(0, "sku_matched") == "❌"
        assert self._display(0, "category_matched") == "❌"

    def test_percent_formatting(self):
        self.model.set_data([{"commission_rate": 10}])
        assert self._display(0, "commission_rate") == "10%"

    def test_float_formatting_cost(self):
        self.model.set_data([{"product_cost": 50.5}])
        assert self._display(0, "product_cost") == "50.50"

    def test_volume_formatting(self):
        self.model.set_data([{"volume": 1.234}])
        assert self._display(0, "volume") == "1.234"

    def test_volume_formatting_none(self):
        self.model.set_data([{"volume": None}])
        assert self._display(0, "volume") == "-"

    def test_density_formatting(self):
        self.model.set_data([{"density": 0.567}])
        assert self._display(0, "density") == "0.567"

    def test_density_formatting_zero(self):
        self.model.set_data([{"density": 0}])
        assert self._display(0, "density") == "-"

    def test_weight_formatting(self):
        self.model.set_data([{"weight": 0.89}])
        assert self._display(0, "weight") == "0.890"

    def test_weight_formatting_zero(self):
        self.model.set_data([{"weight": 0}])
        assert self._display(0, "weight") == "-"

    def test_none_value_shows_dash(self):
        self.model.set_data([{"product_cost": None}])
        assert self._display(0, "product_cost") == "-"

    def test_row_color_sku_miss(self):
        self.model.set_data([{"seller_sku": "X", "sku_matched": False}])
        bg = self._bg(0, "seller_sku")
        assert bg is not None
        assert bg == QColor("#ffe6e6")

    def test_row_color_category_miss(self):
        self.model.set_data([{"seller_sku": "X", "sku_matched": True, "category_matched": False}])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#fff3e0")

    def test_inventory_status_color(self):
        self.model.set_data([{"seller_sku": "X", "sku_matched": True, "inventory_status": "货源充足"}])
        bg = self._bg(0, "inventory_status")
        fg = self._fg(0, "inventory_status")
        assert bg == QColor("#e6f7e6")
        assert fg == QColor("#1a7a1a")

    def test_inventory_status_display(self):
        self.model.set_data([{"inventory_status": "停止上架"}])
        assert self._display(0, "inventory_status") == "停止上架"

    def test_inventory_status_empty_shows_dash(self):
        self.model.set_data([{"inventory_status": ""}])
        assert self._display(0, "inventory_status") == "-"


# ═══════════════════════════════════════════════════════════════════════════
#  3. CalcDataModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCalcDataModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = CalcDataModel()

    def _display(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.DisplayRole)

    def _fg(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.ForegroundRole)

    def test_profit_positive_green(self):
        self.model.set_data([{"seller_sku": "A", "profit": 10.5}])
        fg = self._fg(0, "profit")
        assert fg is not None
        assert fg == QColor(56, 158, 13)

    def test_profit_negative_red(self):
        self.model.set_data([{"seller_sku": "A", "profit": -3.2}])
        fg = self._fg(0, "profit")
        assert fg is not None
        assert fg == QColor(207, 19, 34)

    def test_profit_zero_no_color(self):
        self.model.set_data([{"seller_sku": "A", "profit": 0}])
        fg = self._fg(0, "profit")
        assert fg is None

    def test_percent_discount(self):
        self.model.set_data([{"max_discount": 30}])
        assert self._display(0, "max_discount") == "30%"

    def test_view_column_returns_none(self):
        self.model.set_data([{"seller_sku": "A", "_view": "btn"}])
        col = _col_index(self.model, "_view")
        idx = self.model.index(0, col)
        # data() returns None for _view column (DisplayRole)
        assert self.model.data(idx, Qt.ItemDataRole.DisplayRole) is None

    def test_money_formatting(self):
        self.model.set_data([{"current_price": 100}])
        assert self._display(0, "current_price") == "100.00"

    def test_breakeven_formatting(self):
        self.model.set_data([{"breakeven": 55.123}])
        assert self._display(0, "breakeven") == "55.12"


# ═══════════════════════════════════════════════════════════════════════════
#  4. ResultModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestResultModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = ResultModel()

    def _bg(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.BackgroundRole)

    def _fg(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.ForegroundRole)

    def _display(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.DisplayRole)

    def test_color_priority_sku_over_category(self):
        """SKU miss + category miss → SKU color takes priority."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": False,
            "category_matched": False, "profit": 10,
        }])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#ffe6e6")

    def test_color_priority_sku_over_profit(self):
        """SKU miss + profit>0 → SKU color takes priority."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": False,
            "category_matched": True, "profit": 100,
        }])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#ffe6e6")

    def test_category_miss_color(self):
        """category_matched False (no SKU miss) → category color."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": True,
            "category_matched": False,
        }])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#fff3e0")

    def test_profit_positive_row_green(self):
        """All matched + profit>0 → green row."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": True,
            "category_matched": True, "profit": 50,
        }])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#e6f7e6")

    def test_profit_negative_row_red(self):
        """All matched + profit<0 → red row."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": True,
            "category_matched": True, "profit": -20,
        }])
        bg = self._bg(0, "seller_sku")
        assert bg == QColor("#ffe6e6")

    def test_inventory_override(self):
        """inventory_status cell overrides row-level color."""
        self.model.set_data([{
            "seller_sku": "X", "cost_matched": True,
            "category_matched": True, "profit": 50,
            "inventory_status": "停止上架",
        }])
        bg = self._bg(0, "inventory_status")
        assert bg == QColor("#ffe6e6")

    def test_profit_foreground_positive(self):
        self.model.set_data([{"seller_sku": "X", "profit": 25}])
        fg = self._fg(0, "profit")
        assert fg == QColor(56, 158, 13)

    def test_profit_foreground_negative(self):
        self.model.set_data([{"seller_sku": "X", "profit": -5}])
        fg = self._fg(0, "profit")
        assert fg == QColor(207, 19, 34)

    def test_inventory_foreground(self):
        self.model.set_data([{"seller_sku": "X", "inventory_status": "货源紧缺"}])
        fg = self._fg(0, "inventory_status")
        assert fg == QColor("#856404")

    def test_cost_matched_display(self):
        self.model.set_data([{"seller_sku": "X", "cost_matched": True}])
        assert self._display(0, "cost_matched") == "✅"
        self.model.set_data([{"seller_sku": "X", "cost_matched": False}])
        assert self._display(0, "cost_matched") == "❌"

    def test_none_value_shows_dash(self):
        self.model.set_data([{"seller_sku": "X", "profit": None}])
        assert self._display(0, "profit") == "-"


# ═══════════════════════════════════════════════════════════════════════════
#  5. ColumnFilterProxyModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestColumnFilterProxyModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = MatchDataModel()
        self.model.set_data([
            {"seller_sku": "SKU1", "sku_matched": True},
            {"seller_sku": "SKU2", "sku_matched": False},
            {"seller_sku": "SKU3", "sku_matched": True},
        ])
        self.proxy = ColumnFilterProxyModel()
        self.proxy.setSourceModel(self.model)

    def test_no_filter_shows_all(self):
        assert self.proxy.rowCount() == 3

    def test_column_filter_reduces_rows(self):
        # Filter sku_matched column (col index for "sku_matched")
        col = _col_index(self.model, "sku_matched")
        self.proxy.set_column_filter(col, {"✅"})
        assert self.proxy.rowCount() == 2

    def test_clear_filter_restores_all(self):
        col = _col_index(self.model, "sku_matched")
        self.proxy.set_column_filter(col, {"✅"})
        assert self.proxy.rowCount() == 2
        self.proxy.clear_column_filter(col)
        assert self.proxy.rowCount() == 3

    def test_clear_all_filters(self):
        col = _col_index(self.model, "sku_matched")
        self.proxy.set_column_filter(col, {"✅"})
        self.proxy.clear_all_filters()
        assert self.proxy.rowCount() == 3

    def test_filter_column_unique_values(self):
        col = _col_index(self.model, "sku_matched")
        vals = self.proxy.filter_column_unique_values(col)
        assert "✅" in vals
        assert "❌" in vals


# ═══════════════════════════════════════════════════════════════════════════
#  6. RawDataModel tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRawDataModel:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = RawDataModel()

    def _display(self, row, col_key):
        col = _col_index(self.model, col_key)
        return self.model.data(self.model.index(row, col), Qt.ItemDataRole.DisplayRole)

    def test_list_list_conversion(self):
        rows = [
            [1, "BrandA", "Cat1", "WB001", "SKU1", "BC001", 10, 5, 1.2, 100, 15, 85, 90, 10],
        ]
        self.model.set_data_from_rows(rows)
        assert self.model.rowCount() == 1
        assert self.model._data[0]["brand"] == "BrandA"
        assert self.model._data[0]["seller_sku"] == "SKU1"

    def test_list_list_short_row(self):
        """Row shorter than columns — missing values should be None."""
        rows = [[1, "BrandA"]]  # only 2 values out of 14 columns
        self.model.set_data_from_rows(rows)
        assert self.model._data[0]["brand"] == "BrandA"
        assert self.model._data[0]["seller_sku"] is None

    def test_discount_formatting(self):
        self.model.set_data_from_rows([[1, "B", "C", "W", "S", "BC", 0, 0, 0, 0, 15, 0, 0, 0]])
        assert self._display(0, "current_discount") == "15%"

    def test_price_formatting(self):
        self.model.set_data_from_rows([[1, "B", "C", "W", "S", "BC", 0, 0, 0, 100, 0, 0, 0, 0]])
        assert self._display(0, "current_price") == "100.00"

    def test_turnover_formatting(self):
        self.model.set_data_from_rows([[1, "B", "C", "W", "S", "BC", 0, 0, 2.5, 0, 0, 0, 0, 0]])
        assert self._display(0, "turnover") == "2.5"

    def test_none_value_dash(self):
        self.model.set_data([{"brand": None}])
        assert self._display(0, "brand") == "-"

    def test_stock_display(self):
        self.model.set_data([{"wb_stock": 42}])
        assert self._display(0, "wb_stock") == "42"

    def test_stock_none_dash(self):
        self.model.set_data([{"wb_stock": None}])
        assert self._display(0, "wb_stock") == "-"


# ═══════════════════════════════════════════════════════════════════════════
#  7. Performance tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPerformance:

    @pytest.fixture(autouse=True)
    def _setup(self, qapp):
        self.model = MatchDataModel()

    def test_populate_5000_rows_fast(self):
        data = [
            {"seller_sku": f"SKU{i}", "sku_matched": i % 2 == 0,
             "commission_rate": 10, "product_cost": 50.0 + i,
             "volume": 1.234, "density": 0.567, "weight": 0.89}
            for i in range(5000)
        ]
        t0 = time.perf_counter()
        self.model.set_data(data)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert self.model.rowCount() == 5000
        assert elapsed_ms < 500, f"set_data took {elapsed_ms:.1f}ms (limit 500ms)"

    def test_no_qtablewidgetitem_created(self):
        """Model uses QAbstractTableModel, not QTableWidgetItem."""
        data = [{"seller_sku": "A", "sku_matched": True}]
        self.model.set_data(data)
        gc.collect()
        widgets = [o for o in gc.get_objects()
                   if type(o).__name__ == "QTableWidgetItem"]
        assert len(widgets) == 0
