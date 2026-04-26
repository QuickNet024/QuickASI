# -*- coding: utf-8 -*-
"""产品匹配器测试"""

import pytest
import os
import tempfile

from src.services.matcher import ProductMatcher
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
def matcher(db):
    return ProductMatcher(db=db)


@pytest.fixture
def populated_db(db):
    """DB with sample products"""
    products = [
        Product(sku_code="3C5-YX-JC-530-白", sheet_name="数码-3C5", distribution_price=500, dimensions="30*20*10", category="音响"),
        Product(sku_code="3C5-YX-TO-T300-橙", sheet_name="数码-3C5", distribution_price=300, dimensions="25*15*8", category="音响"),
        Product(sku_code="XB1-13019#-黑色", sheet_name="服装-XB1", distribution_price=800, dimensions="40*30*20", category="箱包"),
        Product(sku_code="3C5-中性HS05", sheet_name="数码-3C5", distribution_price=200, dimensions="10*5*5", category="美妆"),
        Product(sku_code="3C5-JFB-中性HS05卷发棒(皮盒)-珊瑚铜", sheet_name="数码-3C5", distribution_price=150, dimensions="15*8*5", category="美妆"),
        Product(sku_code="3C5-JFB-中性HS08卷发棒(皮盒)-樱花粉", sheet_name="数码-3C5", distribution_price=160, dimensions="15*8*5", category="美妆"),
    ]
    db.insert_products_batch(products)
    return db


class TestParseSku:
    def test_standard(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-YX-JC-530-白-F4")
        assert prefix == "3C5"
        assert sku == "3C5-YX-JC-530-白"

    def test_no_f_suffix(self):
        prefix, sku = ProductMatcher.parse_seller_sku("XB1-13019#-黑色")
        assert prefix == "XB1"
        assert sku == "XB1-13019#-黑色"

    def test_f1_suffix(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-ABC-DEF-F1")
        assert prefix == "3C5"
        assert sku == "3C5-ABC-DEF"

    def test_empty(self):
        prefix, sku = ProductMatcher.parse_seller_sku("")
        assert prefix == ""
        assert sku == ""


class TestMatchProduct:
    def test_exact_match(self, matcher, populated_db):
        result = matcher.match_product("3C5-YX-JC-530-白-F4")
        assert result is not None
        assert result.sku_code == "3C5-YX-JC-530-白"

    def test_no_f_suffix_match(self, matcher, populated_db):
        result = matcher.match_product("XB1-13019#-黑色")
        assert result is not None
        assert result.sku_code == "XB1-13019#-黑色"

    def test_no_match(self, matcher, populated_db):
        result = matcher.match_product("ZZZ-NOTHING-HERE")
        assert result is None

    def test_match_batch(self, matcher, populated_db):
        results = matcher.match_batch(["3C5-YX-JC-530-白-F4", "ZZZ-NOPE"])
        assert results["3C5-YX-JC-530-白-F4"] is not None
        assert results["ZZZ-NOPE"] is None


class TestModifiedSuffix:
    """Tests for -修改{N} suffix stripping and substring containment fallback."""

    def test_parse_strips_xiugai_suffix(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-中性HS05-修改14")
        assert prefix == "3C5"
        assert sku == "3C5-中性HS05"

    def test_parse_strips_f_then_xiugai_suffix(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-中性HS05-F2-修改3")
        assert prefix == "3C5"
        assert sku == "3C5-中性HS05"

    def test_parse_xiugai_only(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-ABC-修改1")
        assert prefix == "3C5"
        assert sku == "3C5-ABC"

    def test_parse_strips_multiple_xiugai(self):
        prefix, sku = ProductMatcher.parse_seller_sku("3C5-DEF-修改1-修改2")
        assert prefix == "3C5"
        assert sku == "3C5-DEF"

    def test_exact_match_with_xiugai_suffix(self, matcher, populated_db):
        result = matcher.match_product("3C5-中性HS05-修改14")
        assert result is not None
        assert result.sku_code == "3C5-中性HS05"

    def test_substring_containment_match(self, matcher, populated_db):
        """Seller SKU core name is contained within feishu product SKU."""
        result = matcher.match_product("3C5-中性HS05卷发棒(皮盒)-修改14")
        assert result is not None
        assert result.sku_code == "3C5-JFB-中性HS05卷发棒(皮盒)-珊瑚铜"

    def test_substring_containment_without_suffix(self, matcher, populated_db):
        """Seller SKU core name matches even without -修改 suffix."""
        result = matcher.match_product("3C5-中性HS08卷发棒(皮盒)")
        assert result is not None
        assert result.sku_code == "3C5-JFB-中性HS08卷发棒(皮盒)-樱花粉"
