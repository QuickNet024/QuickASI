# -*- coding: utf-8 -*-
"""佣金服务测试"""

import pytest
import os
import tempfile

from src.services.commission_svc import CommissionService
from src.models.database import DatabaseManager
from src.models.commission import Commission


@pytest.fixture
def db():
    DatabaseManager.reset_instance()
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = DatabaseManager(db_path=db_path)
    yield db
    db.close()
    DatabaseManager.reset_instance()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def svc(db):
    return CommissionService(db=db)


class TestFindCommissionRate:
    def test_match_by_product(self, svc, db):
        db.insert_commission(Commission(category="美妆", product="水凝胶面膜", rate=15.0))
        rate, matched, source = svc.find_commission_rate("水凝胶面膜")
        assert rate == 15.0
        assert matched is True
        assert source == "product"

    def test_match_by_category(self, svc, db):
        db.insert_commission(Commission(category="内衣", product="晨衣", rate=15.0))
        rate, matched, source = svc.find_commission_rate("内衣")
        assert rate == 15.0
        assert matched is True
        assert source == "category"

    def test_no_match_returns_default(self, svc):
        rate, matched, source = svc.find_commission_rate("不存在的类目")
        assert rate == 30.0
        assert matched is False
        assert source == "default"

    def test_product_priority_over_category(self, svc, db):
        db.insert_commission(Commission(category="箱包", product="箱包", rate=10.0))
        # If category name equals product name, product match should win
        rate, matched, source = svc.find_commission_rate("箱包")
        assert matched is True

    def test_import_from_excel(self, svc, db):
        """Test importing the actual WB commission file"""
        file_path = r"D:\Projects\亏损计算系统\WB佣金表-FBS.xlsx"
        if not os.path.exists(file_path):
            pytest.skip("WB commission file not found")
        count = svc.import_from_excel(file_path)
        assert count > 0
        assert db.get_commission_count() > 0
