# -*- coding: utf-8 -*-
"""汇率服务测试"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock

from src.services.exchange_rate import ExchangeRateService
from src.models.database import DatabaseManager


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
    return ExchangeRateService(db=db)


class TestFetchAndSave:
    @patch("src.services.exchange_rate.requests.get")
    def test_success(self, mock_get, svc, db):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": "success",
            "conversion_rates": {"CNY": 7.25, "RUB": 92.5}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = svc.fetch_and_save()
        assert result is not None
        # cny_to_rub = 92.5 / 7.25 ≈ 12.7586
        assert result["cny_to_rub"] == pytest.approx(12.7586, abs=0.01)

        cached = db.get_exchange_rate()
        assert cached is not None
        assert cached["cny_to_rub"] == pytest.approx(12.7586, abs=0.01)


class TestGetCachedRate:
    def test_no_cache(self, svc):
        rate = svc.get_cached_rate()
        assert rate is None

    def test_with_cache(self, svc, db):
        db.save_exchange_rate(12.5, 0.08)
        rate = svc.get_cached_rate()
        assert rate is not None
        assert rate["cny_to_rub"] == 12.5


class TestGetCnyToRub:
    def test_default(self, svc):
        assert svc.get_cny_to_rub() == 0.0

    def test_cached(self, svc, db):
        db.save_exchange_rate(13.0, 0.077)
        assert svc.get_cny_to_rub() == 13.0
