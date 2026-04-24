# -*- coding: utf-8 -*-
"""数据库CRUD测试"""

import pytest
import os
import tempfile

from src.models.database import DatabaseManager
from src.models.product import Product
from src.models.commission import Commission


@pytest.fixture
def db():
    """每个测试使用独立的临时数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = DatabaseManager(db_path)
    yield db
    # Cleanup
    db.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestDatabaseInit:
    def test_tables_created(self, db):
        """验证所有表都已创建"""
        with db.connection as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert "products" in table_names
            assert "commissions" in table_names
            assert "exchange_rates" in table_names
            assert "app_config" in table_names


class TestProductCRUD:
    def test_insert_product(self, db):
        p = Product(sku_code="3C5-YX-JC-530-白", sheet_name="数码-3C5",
                    distribution_price=500.0, dimensions="30*20*10")
        pid = db.insert_product(p)
        assert pid > 0

    def test_get_product_by_sku(self, db):
        p = Product(sku_code="TEST-SKU-001", sheet_name="数码-3C5",
                    distribution_price=500.0)
        db.insert_product(p)
        found = db.get_product_by_sku("TEST-SKU-001")
        assert found is not None
        assert found.sku_code == "TEST-SKU-001"
        assert found.distribution_price == 500.0

    def test_get_product_not_found(self, db):
        found = db.get_product_by_sku("NONEXISTENT")
        assert found is None

    def test_batch_insert(self, db):
        products = [
            Product(sku_code=f"SKU-{i}", sheet_name=f"CAT-{i % 3}", distribution_price=i * 10.0)
            for i in range(100)
        ]
        count = db.insert_products_batch(products)
        assert count == 100
        assert db.get_product_count() == 100

    def test_upsert_product(self, db):
        """INSERT OR REPLACE should update existing"""
        p1 = Product(sku_code="UPSERT-TEST", sheet_name="S1", distribution_price=100.0)
        db.insert_product(p1)
        p2 = Product(sku_code="UPSERT-TEST", sheet_name="S1", distribution_price=200.0)
        db.insert_product(p2)
        found = db.get_product_by_sku("UPSERT-TEST")
        assert found.distribution_price == 200.0
        assert db.get_product_count() == 1

    def test_get_by_sheet_prefix(self, db):
        products = [
            Product(sku_code="A1", sheet_name="数码-3C5", distribution_price=100),
            Product(sku_code="A2", sheet_name="数码-3C5", distribution_price=200),
            Product(sku_code="B1", sheet_name="服装-XB1", distribution_price=300),
        ]
        db.insert_products_batch(products)
        result = db.get_products_by_sheet_prefix("3C5")
        assert len(result) == 2

    def test_clear_products(self, db):
        db.insert_product(Product(sku_code="X", sheet_name="S", distribution_price=1))
        db.clear_products()
        assert db.get_product_count() == 0


class TestCommissionCRUD:
    def test_insert_commission(self, db):
        c = Commission(category="美妆", product="水凝胶面膜", rate=15.0)
        cid = db.insert_commission(c)
        assert cid > 0

    def test_find_by_product(self, db):
        db.insert_commission(Commission(category="美妆", product="水凝胶面膜", rate=15.0))
        rate = db.find_commission_by_product("水凝胶面膜")
        assert rate == 15.0

    def test_find_by_category(self, db):
        db.insert_commission(Commission(category="内衣", product="晨衣", rate=15.0))
        rate = db.find_commission_by_category("内衣")
        assert rate == 15.0

    def test_not_found(self, db):
        assert db.find_commission_by_product("不存在") is None
        assert db.find_commission_by_category("不存在") is None

    def test_batch_insert(self, db):
        commissions = [
            Commission(category=f"CAT{i}", product=f"PROD{i}", rate=float(i))
            for i in range(50)
        ]
        count = db.insert_commissions_batch(commissions)
        assert count == 50
        assert db.get_commission_count() == 50


class TestExchangeRate:
    def test_save_and_get(self, db):
        db.save_exchange_rate(12.34, 0.0810)
        rate = db.get_exchange_rate()
        assert rate is not None
        assert rate["cny_to_rub"] == 12.34
        assert rate["rub_to_cny"] == pytest.approx(0.0810, abs=0.001)

    def test_update_rate(self, db):
        db.save_exchange_rate(12.0, 0.0833)
        db.save_exchange_rate(13.0, 0.0769)
        rate = db.get_exchange_rate()
        assert rate["cny_to_rub"] == 13.0

    def test_no_rate(self, db):
        rate = db.get_exchange_rate()
        assert rate is None


class TestAppConfig:
    def test_save_and_get(self, db):
        db.save_config("calc_mode", "cross_border")
        assert db.get_config("calc_mode") == "cross_border"

    def test_default_value(self, db):
        assert db.get_config("nonexistent", "default") == "default"

    def test_get_all_config(self, db):
        db.save_config("key1", "val1")
        db.save_config("key2", "val2")
        config = db.get_all_config()
        assert config["key1"] == "val1"
        assert config["key2"] == "val2"
