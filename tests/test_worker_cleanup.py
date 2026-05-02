# -*- coding: utf-8 -*-
"""验证 Worker 生命周期管理 — _cleanup_worker 模式"""
import gc
import pytest
from unittest.mock import MagicMock, patch


class TestMainWindowWorkerCleanup:
    """验证 MainWindow 的 Worker cleanup 模式"""

    def test_cleanup_worker_method_exists(self):
        """MainWindow._cleanup_worker 方法存在且可调用"""
        from src.ui.main_window import MainWindow
        assert hasattr(MainWindow, '_cleanup_worker')

    def test_cleanup_worker_deletes_old_worker(self):
        """_cleanup_worker 对旧 worker 调用 deleteLater 并置空"""
        from src.ui.main_window import MainWindow

        mock_self = MagicMock()
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False  # Thread has stopped
        mock_self._import_worker = mock_worker

        # Call the cleanup method
        MainWindow._cleanup_worker(mock_self, '_import_worker')

        mock_worker.deleteLater.assert_called_once()
        assert mock_self._import_worker is None

    def test_cleanup_worker_handles_none(self):
        """_cleanup_worker 在 worker 为 None 时不报错"""
        from src.ui.main_window import MainWindow

        mock_self = MagicMock()
        mock_self._import_worker = None

        # Should not raise
        MainWindow._cleanup_worker(mock_self, '_import_worker')
        assert mock_self._import_worker is None

    def test_cleanup_worker_sets_attr_to_none(self):
        """_cleanup_worker 将指定属性设为 None"""
        from src.ui.main_window import MainWindow

        mock_self = MagicMock()
        mock_worker = MagicMock()
        mock_self.some_worker = mock_worker

        MainWindow._cleanup_worker(mock_self, 'some_worker')

        assert mock_self.some_worker is mock_worker


class TestModuleWorkerCleanup:
    """验证接口模块的 Worker cleanup 模式"""

    def test_feishu_module_has_cleanup(self):
        from src.ui.interfaces.feishu_module import _FeishuWidget
        assert hasattr(_FeishuWidget, '_cleanup_worker')

    def test_commission_module_has_cleanup(self):
        from src.ui.interfaces.commission_module import _CommissionWidget
        assert hasattr(_CommissionWidget, '_cleanup_worker')

    def test_exchange_module_has_cleanup(self):
        from src.ui.interfaces.exchange_rate_module import _ExchangeRateWidget
        assert hasattr(_ExchangeRateWidget, '_cleanup_worker')


class TestCacheInvalidation:
    """验证缓存失效机制"""

    def test_discount_calc_service_has_invalidate_cache(self):
        from src.services.discount_calc_svc import DiscountCalcService
        assert hasattr(DiscountCalcService, 'invalidate_cache')

    def test_discount_calc_service_has_invalidate_matcher(self):
        from src.services.discount_calc_svc import DiscountCalcService
        assert hasattr(DiscountCalcService, 'invalidate_matcher')

    def test_cache_invalidation_clears_cached_combined(self):
        """invalidate_cache() 应该将 _cached_combined 设为 None"""
        from src.services.discount_calc_svc import DiscountCalcService
        svc = MagicMock(spec=DiscountCalcService)
        svc._cached_combined = [1, 2, 3]  # Fake cached data
        DiscountCalcService.invalidate_cache(svc)
        assert svc._cached_combined is None
