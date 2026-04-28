# -*- coding: utf-8 -*-
"""飞书API集成服务 - 单元测试（全量Mock，无真实API调用）"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.services.feishu_service import FeishuService
from src.models.database import DatabaseManager
from src.models.product import Product


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = DatabaseManager(db_path)
    yield db
    db.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def svc(db):
    return FeishuService(db=db)


def _mock_token_response():
    return {"code": 0, "tenant_access_token": "test_token"}


def _mock_sheets_response():
    return {"code": 0, "data": {"sheets": [
        {"title": "数码-3C5", "sheet_id": "sheet_3c5"},
        {"title": "货盘公告", "sheet_id": "sheet_skip"},
        {"title": "服装-XB1", "sheet_id": "sheet_xb1"},
    ]}}


def _mock_sheet_data(headers, rows):
    return {"code": 0, "data": {"valueRange": {"values": [headers] + rows}}}


def _mock_batch_response(value_ranges):
    """Build a batch get response with multiple valueRanges."""
    return {"code": 0, "data": {"valueRanges": value_ranges}}


class TestGetTenantToken:
    @patch("requests.Session.post")
    def test_success(self, mock_post, svc):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_token_response()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        token = svc.get_tenant_token()
        assert token == "test_token"

    @patch("requests.Session.post")
    def test_auth_failure(self, mock_post, svc):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 99999, "msg": "invalid app_id"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        with pytest.raises(Exception, match="Feishu auth failed"):
            svc.get_tenant_token()


class TestGetAllSheets:
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_returns_sheets(self, mock_post, mock_get, svc):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _mock_token_response()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = _mock_sheets_response()
        mock_get_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_resp

        # Pre-set token to skip auth
        svc._token = "test_token"
        sheets = svc.get_all_sheets()
        assert len(sheets) == 3
        assert sheets[0]["title"] == "数码-3C5"


class TestGetSheetData:
    @patch("requests.Session.get")
    def test_returns_values(self, mock_get, svc):
        svc._token = "test_token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_sheet_data(
            ["SKU-货号", "分销价格"], [["SKU-001", 100]]
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        values = svc.get_sheet_data("sheet_1")
        assert len(values) == 2
        assert values[0] == ["SKU-货号", "分销价格"]


class TestSyncAllProducts:
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_sync_excludes_sheets(self, mock_post, mock_get, svc, db):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _mock_token_response()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_resp

        batch_resp = _mock_batch_response([
            {"values": [["SKU-货号", "分销价格", "长*宽*高(cm)", "类目"],
                        ["3C5-YX-JC-530-白", 500, "30*20*10", "音响"]]},
            {"values": [["标题"], ["公告"]]},
        ])

        mock_get_resp = MagicMock()
        mock_get_resp.raise_for_status = MagicMock()
        mock_get_resp.json.side_effect = [_mock_sheets_response(), batch_resp]
        mock_get.return_value = mock_get_resp

        count, sheets = svc.sync_all_products()
        assert count == 1
        assert "货盘公告" not in sheets

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_sync_stores_products(self, mock_post, mock_get, svc, db):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _mock_token_response()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_resp

        batch_resp = _mock_batch_response([
            {"values": [["SKU-货号", "分销价格", "长*宽*高(cm)", "类目"],
                        ["SKU-001", 100, "10*10*10", "电子"]]},
        ])

        mock_get_resp = MagicMock()
        mock_get_resp.raise_for_status = MagicMock()
        mock_get_resp.json.side_effect = [
            {"code": 0, "data": {"sheets": [{"title": "测试", "sheet_id": "s1"}]}},
            batch_resp
        ]
        mock_get.return_value = mock_get_resp

        count, _ = svc.sync_all_products()
        assert count == 1
        p = db.get_product_by_sku("SKU-001")
        assert p is not None
        assert p.distribution_price == 100.0

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_sync_empty_sheet_skipped(self, mock_post, mock_get, svc, db):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _mock_token_response()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_resp

        # Only header, no data rows
        data = _mock_sheet_data(["SKU-货号", "分销价格"], [])

        mock_get_resp = MagicMock()
        mock_get_resp.raise_for_status = MagicMock()
        mock_get_resp.json.side_effect = [
            {"code": 0, "data": {"sheets": [{"title": "空表", "sheet_id": "s1"}]}},
            data
        ]
        mock_get.return_value = mock_get_resp

        count, sheets = svc.sync_all_products()
        assert count == 0
        assert sheets == []

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_sync_multiple_sheets(self, mock_post, mock_get, svc, db):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _mock_token_response()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_resp

        batch_resp = _mock_batch_response([
            {"values": [["SKU-货号", "分销价格"], ["SKU-A1", 50], ["SKU-A2", 60]]},
            {"values": [["SKU-货号", "分销价格"], ["SKU-B1", 70]]},
        ])

        sheets_resp = {"code": 0, "data": {"sheets": [
            {"title": "Sheet-A", "sheet_id": "sA"},
            {"title": "Sheet-B", "sheet_id": "sB"},
        ]}}

        mock_get_resp = MagicMock()
        mock_get_resp.raise_for_status = MagicMock()
        mock_get_resp.json.side_effect = [sheets_resp, batch_resp]
        mock_get.return_value = mock_get_resp

        count, sheets = svc.sync_all_products()
        assert count == 3
        assert "Sheet-A" in sheets
        assert "Sheet-B" in sheets


class TestParseRows:
    def test_standard_headers(self, svc):
        headers = ["SKU-货号", "分销价格", "长*宽*高(cm)", "包装重量", "类目", "中文名称", "品牌"]
        rows = [["TEST-001", "500", "30*20*10", "1.5", "电子", "测试产品", "测试品牌"]]
        products = svc._parse_rows(headers, rows, "测试Sheet")
        assert len(products) == 1
        assert products[0].sku_code == "TEST-001"
        assert products[0].distribution_price == 500.0
        assert products[0].dimensions == "30*20*10"
        assert products[0].weight == 1.5
        assert products[0].category == "电子"
        assert products[0].chinese_name == "测试产品"
        assert products[0].brand == "测试品牌"
        assert products[0].sheet_name == "测试Sheet"
        assert products[0].image_file_token == ""
        assert products[0].image_local_path == ""
        assert products[0].original_price == 0.0
        assert products[0].supplier == ""
        assert products[0].remarks == ""

    def test_no_sku_column(self, svc):
        headers = ["名称", "价格"]
        rows = [["产品", 100]]
        products = svc._parse_rows(headers, rows, "测试")
        assert products == []

    def test_empty_sku_skipped(self, svc):
        headers = ["SKU-货号", "分销价格"]
        rows = [["", 100], [None, 200]]
        products = svc._parse_rows(headers, rows, "测试")
        assert products == []

    def test_alternative_header_names(self, svc):
        headers = ["货号", "价格", "尺寸", "重量", "品类", "名称", "品牌"]
        rows = [["ALT-001", 200, "15*10*5", "2.0", "家居", "替换名", "替换牌"]]
        products = svc._parse_rows(headers, rows, "替换Sheet")
        assert len(products) == 1
        assert products[0].sku_code == "ALT-001"
        assert products[0].distribution_price == 200.0

    def test_comma_in_price(self, svc):
        headers = ["SKU-货号", "分销价格"]
        rows = [["SKU-COMMA", "1,500.50"]]
        products = svc._parse_rows(headers, rows, "测试")
        assert len(products) == 1
        assert products[0].distribution_price == 1500.50

    def test_missing_columns_use_defaults(self, svc):
        headers = ["SKU-货号"]
        rows = [["SKU-MIN"]]
        products = svc._parse_rows(headers, rows, "测试")
        assert len(products) == 1
        assert products[0].distribution_price == 0.0
        assert products[0].dimensions == ""
        assert products[0].weight == 0.0

    def test_multiple_rows(self, svc):
        headers = ["SKU-货号", "分销价格"]
        rows = [["SKU-1", 100], ["SKU-2", 200], ["SKU-3", 300]]
        products = svc._parse_rows(headers, rows, "测试")
        assert len(products) == 3


class TestHelperMethods:
    def test_find_col_exact_match(self):
        assert FeishuService._find_col(["sku-货号"], ["sku-货号"]) == 0

    def test_find_col_partial_match(self):
        assert FeishuService._find_col(["sku-货号(标准)"], ["sku-货号"]) == 0

    def test_find_col_no_match(self):
        assert FeishuService._find_col(["其他列"], ["sku-货号"]) is None

    def test_safe_str_none(self):
        assert FeishuService._safe_str([], 0) == ""

    def test_safe_str_out_of_range(self):
        assert FeishuService._safe_str(["a"], 5) == ""

    def test_safe_float_invalid(self):
        assert FeishuService._safe_float(["abc"], 0) == 0.0

    def test_safe_float_none_idx(self):
        assert FeishuService._safe_float(["100"], None) == 0.0

    def test_safe_float_empty_string(self):
        assert FeishuService._safe_float([""], 0) == 0.0

    def test_safe_float_none_value(self):
        assert FeishuService._safe_float([None], 0) == 0.0

    def test_safe_float_currency_prefix(self):
        assert FeishuService._safe_float(["¥500.00"], 0) == 500.0

    def test_safe_float_currency_suffix(self):
        assert FeishuService._safe_float(["500.00 ₽"], 0) == 500.0

    def test_safe_float_rub_prefix(self):
        assert FeishuService._safe_float(["RUB 500"], 0) == 500.0

    def test_safe_float_formula_string(self):
        assert FeishuService._safe_float(["=A2*B2"], 0) == 0.0

    def test_safe_float_dict_image(self):
        assert FeishuService._safe_float([{"type": "embed-image"}], 0) == 0.0

    def test_safe_float_comma_thousands(self):
        assert FeishuService._safe_float(["1,500.50"], 0) == 1500.5

    def test_safe_str_dict_image(self):
        assert FeishuService._safe_str([{"type": "embed-image", "fileToken": "abc"}], 0) == ""
