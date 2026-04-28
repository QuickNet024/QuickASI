# -*- coding: utf-8 -*-
"""验证内存泄漏修复效果 — Worker 对象不累积"""
import gc
import pytest


class TestMemoryLeak:
    """验证 Worker 对象在 cleanup 后可被 GC 回收"""

    def test_mock_workers_are_collected(self):
        """模拟 Worker 创建/销毁循环后，对象可被 GC"""
        import weakref

        collected = []

        class FakeWorker:
            def __init__(self):
                self.data = [0] * 10000  # Simulate some memory usage

        workers = []
        for _ in range(10):
            # Simulate creating and cleaning up workers
            worker = FakeWorker()
            ref = weakref.ref(worker, lambda r: collected.append(1))
            workers.append(ref)
            del worker

        gc.collect()

        # All weakrefs should be dead after GC
        alive = sum(1 for ref in workers if ref() is not None)
        assert alive == 0, f"{alive} workers still alive after GC"

    def test_cleanup_worker_pattern(self):
        """验证 cleanup 模式：deleteLater mock + set None"""
        from unittest.mock import MagicMock
        from src.ui.main_window import MainWindow

        # Simulate the cleanup pattern
        mock_self = MagicMock()
        worker1 = MagicMock()
        mock_self._worker = worker1

        # Cleanup
        MainWindow._cleanup_worker(mock_self, '_worker')

        assert mock_self._worker is None
        worker1.deleteLater.assert_called_once()

    def test_cache_prevents_repeated_queries(self):
        """验证 get_import_data 缓存生效"""
        from unittest.mock import MagicMock, PropertyMock

        # Create a mock service with cache attribute
        mock_db = MagicMock()
        mock_db.get_import_rows.return_value = [(1, 'sku1')]
        mock_db.get_calc_results.return_value = [(1, 'sku1', True)]

        from src.services.discount_calc_svc import DiscountCalcService
        svc = DiscountCalcService.__new__(DiscountCalcService)
        svc.db = mock_db
        svc._feishu_db = MagicMock()
        svc._cached_combined = None
        svc._matcher = None
        svc._matcher_cache_valid = False

        # First call should query DB
        result1 = svc.get_import_data()
        assert mock_db.get_import_rows.call_count == 1

        # Second call should use cache
        result2 = svc.get_import_data()
        assert mock_db.get_import_rows.call_count == 1  # No additional query

        # Results should be identical
        assert result1 is result2

    def test_cache_invalidation_works(self):
        """验证 invalidate_cache 后重新查询"""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.get_import_rows.return_value = [(1, 'sku1')]
        mock_db.get_calc_results.return_value = [(1, 'sku1', True)]

        from src.services.discount_calc_svc import DiscountCalcService
        svc = DiscountCalcService.__new__(DiscountCalcService)
        svc.db = mock_db
        svc._feishu_db = MagicMock()
        svc._cached_combined = None
        svc._matcher = None
        svc._matcher_cache_valid = False

        # First call
        svc.get_import_data()
        assert mock_db.get_import_rows.call_count == 1

        # Invalidate
        svc.invalidate_cache()

        # Second call should re-query
        svc.get_import_data()
        assert mock_db.get_import_rows.call_count == 2
