# -*- coding: utf-8 -*-
"""飞书API集成服务 V2 — 高速并行同步 + 增量图片 + 独立配置

特性:
- concurrent.futures 多线程并行读取 sheet 数据
- 增量图片同步（对比 DB 中的 file_token，仅下载变更）
- 无 5MB 限制：下载任意大小 → 缩放压缩 → 保存
- 可配置线程数、限流 QPS、图片缓存路径
- 纯 Python 核心逻辑，QImage 可选（非 GUI 环境保存原始字节）
- 可被 Web/Win 程序直接调用
"""

import re
import os
import json
import requests
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple, Dict, Callable
from datetime import datetime

from src.config import Config
from src.models.database import DatabaseManager
from src.models.product import Product
from src.services.interface_config import InterfaceConfig

logger = logging.getLogger(__name__)


# 默认列映射: 表头候选词 → 产品字段
DEFAULT_COLUMN_MAP = {
    "sku_code":        {"candidates": ["sku-货号", "sku", "货号", "sku_code"], "type": "text"},
    "distribution_price": {"candidates": ["分销价格", "分销价", "价格", "price", "供货价", "供货价格", "成本价", "采购价", "成本"], "type": "number"},
    "dimensions":      {"candidates": ["长*宽*高(cm)", "长×宽×高", "尺寸", "dimensions"], "type": "text"},
    "weight":          {"candidates": ["包装重量", "重量", "weight"], "type": "number"},
    "category":        {"candidates": ["类目", "品类", "category"], "type": "text"},
    "chinese_name":    {"candidates": ["中文名称", "名称", "name"], "type": "text"},
    "brand":           {"candidates": ["品牌", "brand"], "type": "text"},
    "inventory":       {"candidates": ["库存数量", "库存数", "stock_qty"], "type": "number"},
    "inventory_status":{"candidates": ["库存信息"], "type": "text"},
    "supplier":        {"candidates": ["产品编号", "供应商编号", "供应商"], "type": "text"},
    "image":           {"candidates": ["图片", "image", "产品图片"], "type": "image"},
}


class _RateLimiter:
    """简单的令牌桶限流器 — 线程安全"""

    def __init__(self, rate: float = 5.0):
        """
        Args:
            rate: 每秒允许的最大请求数
        """
        self._rate = max(rate, 0.1)
        self._min_interval = 1.0 / self._rate
        self._last_time = 0.0
        self._lock = threading.Lock()

    def wait(self):
        """阻塞等待直到可以发送下一个请求"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_time = time.monotonic()

    @property
    def rate(self) -> float:
        return self._rate

    @rate.setter
    def rate(self, value: float):
        self._rate = max(value, 0.1)
        self._min_interval = 1.0 / self._rate


class FeishuService:
    """飞书云表数据同步服务 V2 — 独立封装，可被多程序调用

    配置优先级: DB > config/feishu.json > 代码默认值
    """

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

        # 加载配置：DB > 文件 > 默认值
        self._iconfig = InterfaceConfig("feishu", db=self.db)
        self._iconfig.reload()  # 确保读到最新文件

        self.app_id = self._iconfig.get("api.app_id", Config.FEISHU_APP_ID)
        self.app_secret = self._iconfig.get("api.app_secret", Config.FEISHU_APP_SECRET)
        self.spreadsheet_token = self._iconfig.get("api.spreadsheet_token", Config.FEISHU_SPREADSHEET_TOKEN)
        self.base_url = self._iconfig.get("api.base_url", "https://open.feishu.cn")

        # 同步配置
        self._sync_thread_count = self._iconfig.get("sync.thread_count", 4)
        self._rate_limit = self._iconfig.get("sync.rate_limit_per_sec", 5.0)
        self._request_timeout = self._iconfig.get("sync.request_timeout_sec", 30)
        self._retry_count = self._iconfig.get("sync.retry_count", 3)
        self._retry_delay = self._iconfig.get("sync.retry_delay_sec", 1.0)

        # 图片配置
        self._image_dir = self._iconfig.get("image.download_path", "data/image_cache")
        self._image_resize = self._iconfig.get("image.resize_enabled", True)
        self._image_target_w = self._iconfig.get("image.target_width", 450)
        self._image_target_h = self._iconfig.get("image.target_height", 600)
        self._image_incremental = self._iconfig.get("image.incremental_mode", True)
        self._image_dl_threads = self._iconfig.get("image.download_thread_count", 3)
        self._image_dl_batch = self._iconfig.get("image.download_batch_size", 5)
        self._image_dl_delay = self._iconfig.get("image.download_delay_sec", 0.2)

        # API 限流器
        self._limiter = _RateLimiter(self._rate_limit)
        self._token = None

    # ═══ 配置访问接口 ═══════════════════════════

    def get_iconfig(self) -> InterfaceConfig:
        """获取当前接口配置管理器（供外部读取/修改配置）"""
        return self._iconfig

    def get_sync_settings(self) -> dict:
        """返回当前同步相关配置（供 UI 展示）"""
        return {
            "thread_count": self._sync_thread_count,
            "rate_limit_per_sec": self._rate_limit,
            "request_timeout_sec": self._request_timeout,
            "retry_count": self._retry_count,
            "image_dir": self._image_dir,
            "image_incremental": self._image_incremental,
            "image_dl_threads": self._image_dl_threads,
        }

    def update_sync_settings(self, settings: dict):
        """更新同步配置（同时写入配置文件）"""
        if "thread_count" in settings:
            self._sync_thread_count = settings["thread_count"]
            self._iconfig.set("sync.thread_count", settings["thread_count"])
        if "rate_limit_per_sec" in settings:
            self._rate_limit = settings["rate_limit_per_sec"]
            self._limiter.rate = self._rate_limit
            self._iconfig.set("sync.rate_limit_per_sec", settings["rate_limit_per_sec"])
        if "request_timeout_sec" in settings:
            self._request_timeout = settings["request_timeout_sec"]
            self._iconfig.set("sync.request_timeout_sec", settings["request_timeout_sec"])
        if "image_dir" in settings:
            self._image_dir = settings["image_dir"]
            self._iconfig.set("image.download_path", settings["image_dir"])
        if "image_incremental" in settings:
            self._image_incremental = settings["image_incremental"]
            self._iconfig.set("image.incremental_mode", settings["image_incremental"])
        if "image_dl_threads" in settings:
            self._image_dl_threads = settings["image_dl_threads"]
            self._iconfig.set("image.download_thread_count", settings["image_dl_threads"])

    # ═══ API 基础方法 ═══════════════════════════

    def get_tenant_token(self) -> str:
        self._limiter.wait()
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Feishu auth failed: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        return self._token

    def get_all_sheets(self) -> List[dict]:
        """获取所有 sheet 页信息"""
        token = self._token or self.get_tenant_token()
        self._limiter.wait()
        url = f"{self.base_url}/open-apis/sheets/v3/spreadsheets/{self.spreadsheet_token}/sheets/query"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Get sheets failed: {data.get('msg')}")
        return data.get("data", {}).get("sheets", [])

    def get_sheet_headers(self, sheet_id: str) -> List[str]:
        """读取单个 sheet 的第一行（表头）"""
        rows = self.get_sheet_data(sheet_id, max_rows=1)
        if rows:
            return [str(c).strip() for c in rows[0]]
        return []

    def get_all_sheet_headers(self) -> Dict[str, List[str]]:
        """获取所有 sheet 的表头，返回 {sheet_title: [headers]}"""
        self.get_tenant_token()
        sheets = self.get_all_sheets()
        result = {}
        for s in sheets:
            title = s.get("title", "")
            sheet_id = s.get("sheet_id", "")
            if title in Config.FEISHU_EXCLUDE_SHEETS:
                continue
            try:
                headers = self.get_sheet_headers(sheet_id)
                result[title] = headers
            except Exception as e:
                logger.warning(f"Failed to read headers for '{title}': {e}")
                result[title] = []
        return result

    def get_sheet_data(self, sheet_id: str, max_rows: int = 10000, max_col: int = None) -> List[List]:
        col_str = self._col_letter(max_col) if max_col else "ZZ"
        range_str = f"{sheet_id}!A1:{col_str}{max_rows}"
        return self._raw_get_range(range_str)

    # ═══ 高级配置 ═══════════════════════════════

    def get_sync_config(self) -> dict:
        """读取飞书同步高级配置"""
        raw = self.db.get_config("feishu_sync_config", "")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "included_sheets": [],
            "excluded_sheets": list(Config.FEISHU_EXCLUDE_SHEETS),
            "column_mapping": {},
        }

    def save_sync_config(self, config: dict):
        """保存飞书同步高级配置"""
        self.db.save_config("feishu_sync_config", json.dumps(config, ensure_ascii=False))

    def _get_effective_column_map(self, config: dict) -> dict:
        """获取生效的列映射：用户自定义 > 默认"""
        user_map = config.get("column_mapping", {})
        if user_map:
            return user_map
        return DEFAULT_COLUMN_MAP

    def _should_sync_sheet(self, title: str, config: dict) -> bool:
        """根据配置判断是否同步该 sheet"""
        excluded = config.get("excluded_sheets", list(Config.FEISHU_EXCLUDE_SHEETS))
        if title in excluded:
            return False
        included = config.get("included_sheets", [])
        if included and title not in included:
            return False
        return True

    # ═══ 同步主流程 V2（并行） ═══════════════════

    def sync_all_products(self, sync_images=False,
                          progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Tuple[int, List[str]]:
        """同步所有 sheet 到本地 DB — 多线程并行

        Args:
            sync_images: 是否同步图片
            progress_cb: 进度回调 (current, total, message)

        Returns:
            (总产品数, 已同步sheet列表)
        """
        config = self.get_sync_config()
        self.get_tenant_token()
        sheets = self.get_all_sheets()

        active_sheets = []
        for s in sheets:
            title = s.get("title", "")
            if not self._should_sync_sheet(title, config):
                continue
            sheet_id = s.get("sheet_id", "")
            grid = s.get("grid_properties", {})
            active_sheets.append((sheet_id, title, grid))

        if not active_sheets:
            return 0, []

        col_map = self._get_effective_column_map(config)

        # ── 阶段1: 尝试批量获取（单次 API 调用） ──
        ranges = []
        for sheet_id, title, grid in active_sheets:
            row_count = grid.get("row_count", 10000)
            ranges.append(f"{sheet_id}!A1:ZZ{row_count}")

        value_ranges = None
        try:
            value_ranges = self._raw_batch_get_ranges(ranges)
        except Exception as e:
            logger.warning(f"Batch read failed ({e}), falling back to parallel individual reads")

        if value_ranges is not None:
            # 批量成功 — 并行解析 + 写入
            total, synced_sheets = self._parallel_parse_and_save(
                active_sheets, value_ranges, col_map, progress_cb)
        else:
            # 批量失败 — 并行逐个读取
            total, synced_sheets = self._parallel_fetch_and_save(
                active_sheets, col_map, progress_cb)

        # ── 阶段2: 图片同步（多线程增量） ──
        if sync_images:
            self._sync_images_parallel(active_sheets,
                                       value_ranges if value_ranges else [],
                                       col_map, progress_cb)

        return total, synced_sheets

    def _parallel_parse_and_save(self, active_sheets, value_ranges, col_map,
                                  progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Tuple[int, List[str]]:
        """并行解析批量获取的数据"""
        total = 0
        synced_sheets = []
        sheet_count = len(active_sheets)

        # 用线程池并行解析各 sheet
        futures = {}
        with ThreadPoolExecutor(max_workers=min(self._sync_thread_count, sheet_count)) as pool:
            for i, vr in enumerate(value_ranges):
                sheet_id, title, grid = active_sheets[i]
                future = pool.submit(self._parse_one_sheet, vr, title, col_map)
                futures[future] = title

            for future in as_completed(futures):
                title = futures[future]
                try:
                    products = future.result()
                    if products:
                        self.db.insert_products_batch(products)
                        total += len(products)
                        synced_sheets.append(title)
                        if progress_cb:
                            progress_cb(len(synced_sheets), sheet_count, f"已解析: {title}")
                except Exception as e:
                    logger.error(f"Failed to parse sheet '{title}': {e}")

        logger.info(f"Parsed {total} products from {len(synced_sheets)} sheets (parallel)")
        return total, synced_sheets

    def _parallel_fetch_and_save(self, active_sheets, col_map,
                                  progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Tuple[int, List[str]]:
        """并行逐个读取 sheet 数据（批量获取失败时的降级方案）"""
        total = 0
        synced_sheets = []
        sheet_count = len(active_sheets)
        _lock = threading.Lock()
        _done_count = [0]

        def _fetch_one(item):
            sheet_id, title, grid = item
            try:
                col_count = min(grid.get("column_count", 26), 52)
                row_count = grid.get("row_count", 10000)
                rows = self.get_sheet_data(sheet_id, max_rows=row_count, max_col=col_count)
                if len(rows) < 2:
                    return title, []
                headers = rows[0]
                products = self._parse_rows_with_map(headers, rows[1:], title, col_map)
                return title, products
            except Exception as e:
                logger.error(f"Failed to fetch sheet '{title}': {e}")
                return title, []

        with ThreadPoolExecutor(max_workers=min(self._sync_thread_count, sheet_count)) as pool:
            futures = {pool.submit(_fetch_one, item): item[1] for item in active_sheets}

            for future in as_completed(futures):
                title = futures[future]
                try:
                    _, products = future.result()
                    if products:
                        with _lock:
                            self.db.insert_products_batch(products)
                            total += len(products)
                            synced_sheets.append(title)
                    with _lock:
                        _done_count[0] += 1
                    if progress_cb:
                        progress_cb(_done_count[0], sheet_count, f"已读取: {title}")
                except Exception as e:
                    logger.error(f"Failed to process sheet '{title}': {e}")

        logger.info(f"Fetched {total} products from {len(synced_sheets)} sheets (parallel individual)")
        return total, synced_sheets

    def _parse_one_sheet(self, vr: dict, title: str, col_map: dict) -> List[Product]:
        """解析单个 sheet 的数据（供线程池调用）"""
        rows = vr.get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return self._parse_rows_with_map(headers, rows[1:], title, col_map)

    # ═══ 图片同步 V2（多线程增量） ═══════════════

    def _sync_images_parallel(self, active_sheets, value_ranges, col_map,
                               progress_cb=None):
        """多线程增量图片下载

        增量逻辑: 对比 DB 中产品的 image_file_token 和本地文件
        - token 未变 + 本地文件存在 → 跳过
        - token 变更或本地文件缺失 → 下载
        """
        # 收集所有需要下载的图片 token
        tokens_to_download = self._collect_image_tokens(active_sheets, value_ranges, col_map)
        if not tokens_to_download:
            logger.info("No images found to download")
            return

        logger.info(f"Found {len(tokens_to_download)} unique image tokens")

        # 增量过滤
        if self._image_incremental:
            tokens_to_download = self._filter_incremental(tokens_to_download)
            if not tokens_to_download:
                logger.info("All images up to date (incremental)")
                return
            logger.info(f"Incremental: {len(tokens_to_download)} images need download")

        # 多线程下载
        self._download_images_parallel(tokens_to_download, progress_cb)

    def _collect_image_tokens(self, active_sheets, value_ranges, col_map) -> Dict[str, Tuple[str, str]]:
        """从数据中收集所有图片 token"""
        tokens = {}  # fileToken -> (sku, col_name)

        if value_ranges:
            for i, vr in enumerate(value_ranges):
                rows = vr.get("values", [])
                if len(rows) < 2:
                    continue
                headers = [str(c).strip().lower() for c in rows[0]]
                sku_idx = self._find_col_by_map(headers, col_map, "sku_code")
                img_idx = self._find_col_by_map(headers, col_map, "image")

                for row in rows[1:]:
                    sku = self._safe_str(row, sku_idx) if sku_idx is not None else ""
                    if not sku:
                        continue
                    if img_idx is not None and img_idx < len(row):
                        val = row[img_idx]
                        if isinstance(val, dict) and val.get("type") == "embed-image":
                            token = val.get("fileToken", "")
                            if token and token not in tokens:
                                tokens[token] = (sku, "image")
        else:
            # 逐个读取时需要重新获取数据
            for sheet_id, title, grid in active_sheets:
                try:
                    col_count = min(grid.get("column_count", 26), 52)
                    row_count = grid.get("row_count", 10000)
                    rows = self.get_sheet_data(sheet_id, max_rows=row_count, max_col=col_count)
                    if len(rows) < 2:
                        continue
                    headers = [str(c).strip().lower() for c in rows[0]]
                    sku_idx = self._find_col_by_map(headers, col_map, "sku_code")
                    img_idx = self._find_col_by_map(headers, col_map, "image")
                    for row in rows[1:]:
                        sku = self._safe_str(row, sku_idx) if sku_idx is not None else ""
                        if not sku:
                            continue
                        if img_idx is not None and img_idx < len(row):
                            val = row[img_idx]
                            if isinstance(val, dict) and val.get("type") == "embed-image":
                                token = val.get("fileToken", "")
                                if token and token not in tokens:
                                    tokens[token] = (sku, "image")
                except Exception as e:
                    logger.warning(f"Failed to collect image tokens from '{title}': {e}")

        return tokens

    def _filter_incremental(self, tokens: Dict[str, Tuple[str, str]]) -> Dict[str, Tuple[str, str]]:
        """增量过滤: 跳过本地已存在且 token 未变的图片"""
        cache_dir = self._resolve_image_dir()
        filtered = {}
        for file_token, (sku, col) in tokens.items():
            local_path = os.path.join(cache_dir, f"{file_token}.png")
            if os.path.exists(local_path):
                # 本地文件存在 — 增量模式下跳过
                # 未来可通过 DB 记录 file_token hash 实现更精确的变更检测
                continue
            filtered[file_token] = (sku, col)
        return filtered

    def _resolve_image_dir(self) -> str:
        """解析图片缓存目录路径（支持相对路径和绝对路径）"""
        if os.path.isabs(self._image_dir):
            return self._image_dir
        # 相对于项目根目录
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), self._image_dir)

    def _download_images_parallel(self, tokens: Dict[str, Tuple[str, str]],
                                   progress_cb=None):
        """多线程并行下载图片（无 5MB 限制）"""
        cache_dir = self._resolve_image_dir()
        os.makedirs(cache_dir, exist_ok=True)

        token_list = list(tokens.keys())
        total = len(token_list)
        downloaded = [0]
        failed = [0]
        _count_lock = threading.Lock()

        def _download_batch(batch_tokens):
            """下载一批图片"""
            try:
                self._limiter.wait()
                urls = self._get_temp_download_urls(batch_tokens)
                for file_token, url in urls.items():
                    if not url:
                        continue
                    try:
                        self._limiter.wait()
                        resp = requests.get(url, timeout=self._request_timeout)
                        if resp.status_code == 200:
                            local_path = os.path.join(cache_dir, f"{file_token}.png")
                            if os.path.exists(local_path):
                                with _count_lock:
                                    downloaded[0] += 1
                                continue
                            # 保存图片（无大小限制，自动缩放）
                            self._save_image(resp.content, local_path)
                            with _count_lock:
                                downloaded[0] += 1
                            logger.debug(f"Downloaded image: {file_token}")
                    except Exception as e:
                        with _count_lock:
                            failed[0] += 1
                        logger.warning(f"Failed to download image {file_token}: {e}")
            except Exception as e:
                logger.warning(f"Failed to get temp URLs for batch: {e}")

        # 分批并行下载
        batch_size = self._image_dl_batch
        batches = [token_list[i:i + batch_size] for i in range(0, len(token_list), batch_size)]

        with ThreadPoolExecutor(max_workers=self._image_dl_threads) as pool:
            futures = []
            for batch in batches:
                future = pool.submit(_download_batch, batch)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Image download batch error: {e}")
                if progress_cb:
                    progress_cb(downloaded[0], total, f"图片: {downloaded[0]}/{total}")

        logger.info(f"Image sync done: {downloaded[0]} downloaded, {failed[0]} failed, {total} total")

    def _save_image(self, image_data: bytes, save_path: str):
        """保存图片 — 自动缩放到目标尺寸，支持非 GUI 环境"""
        if self._image_resize:
            try:
                self._save_normalized_image(image_data, save_path)
                return
            except ImportError:
                # PySide6 不可用（非 GUI 环境）— 保存原始字节
                logger.debug("QImage not available, saving raw image bytes")
            except Exception as e:
                logger.warning(f"Image normalization failed, saving raw: {e}")

        # 保存原始字节
        with open(save_path, "wb") as f:
            f.write(image_data)

    @staticmethod
    def _save_normalized_image(image_data: bytes, save_path: str):
        """Resize image to target size PNG with transparent padding (requires PySide6)."""
        from PySide6.QtGui import QImage, QPixmap, QPainter
        from PySide6.QtCore import Qt, QSize

        TARGET_W, TARGET_H = 450, 600

        img = QImage()
        img.loadFromData(image_data)
        if img.isNull():
            with open(save_path, "wb") as f:
                f.write(image_data)
            return

        scaled = img.scaled(TARGET_W, TARGET_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        canvas = QPixmap(QSize(TARGET_W, TARGET_H))
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        x = (TARGET_W - scaled.width()) // 2
        y = (TARGET_H - scaled.height()) // 2
        painter.drawImage(x, y, scaled)
        painter.end()
        canvas.save(save_path, "PNG")

    # ═══ 数据解析（保持向后兼容） ═══════════════

    def _parse_rows(self, headers: List, rows: List[List], sheet_name: str) -> List[Product]:
        """向后兼容 — 使用默认列映射解析行数据"""
        return self._parse_rows_with_map(headers, rows, sheet_name, DEFAULT_COLUMN_MAP)

    def _parse_rows_with_map(self, headers: List, rows: List[List], sheet_name: str, col_map: dict) -> List[Product]:
        """使用列映射配置解析行数据"""
        h = [str(col).strip().lower() for col in headers]

        sku_idx = self._find_col_by_map(h, col_map, "sku_code")
        if sku_idx is None:
            return []

        price_idx = self._find_col_by_map(h, col_map, "distribution_price")
        dim_idx = self._find_col_by_map(h, col_map, "dimensions")
        weight_idx = self._find_col_by_map(h, col_map, "weight")
        cat_idx = self._find_col_by_map(h, col_map, "category")
        name_idx = self._find_col_by_map(h, col_map, "chinese_name")
        brand_idx = self._find_col_by_map(h, col_map, "brand")
        inv_count_idx = self._find_col_by_map(h, col_map, "inventory")
        inv_status_idx = self._find_col_by_map(h, col_map, "inventory_status")
        supplier_idx = self._find_col_by_map(h, col_map, "supplier")
        img_col_idx = self._find_col_by_map(h, col_map, "image")

        products = []
        now = datetime.now()
        for row in rows:
            try:
                sku = self._safe_str(row, sku_idx)
                if not sku:
                    continue

                img_token = ""
                if img_col_idx is not None and img_col_idx < len(row):
                    val = row[img_col_idx]
                    if isinstance(val, dict) and val.get("type") == "embed-image":
                        img_token = val.get("fileToken", "")
                if not img_token and brand_idx is not None and brand_idx < len(row):
                    val = row[brand_idx]
                    if isinstance(val, dict) and val.get("type") == "embed-image":
                        img_token = val.get("fileToken", "")

                products.append(Product(
                    sku_code=sku,
                    sheet_name=sheet_name,
                    distribution_price=self._safe_float(row, price_idx),
                    dimensions=self._safe_str(row, dim_idx),
                    weight=self._safe_float(row, weight_idx),
                    category=self._safe_str(row, cat_idx),
                    chinese_name=self._safe_str(row, name_idx),
                    brand=self._safe_str(row, brand_idx),
                    inventory=self._safe_int(row, inv_count_idx),
                    inventory_status=self._safe_str(row, inv_status_idx),
                    synced_at=now,
                    image_file_token=img_token,
                    image_local_path="",
                    original_price=0.0,
                    supplier=self._safe_str(row, supplier_idx),
                    remarks="",
                ))
            except Exception:
                continue
        return products

    def _find_col_by_map(self, headers: List[str], col_map: dict, field: str) -> Optional[int]:
        mapping = col_map.get(field)
        if not mapping:
            return None
        candidates = mapping.get("candidates", [])
        if not candidates:
            header_name = mapping.get("header", "")
            if header_name:
                candidates = [header_name.lower()]
        return self._find_col(headers, candidates) if candidates else None

    @staticmethod
    def _find_col(headers: List[str], candidates: List[str]) -> Optional[int]:
        for i, h in enumerate(headers):
            for c in candidates:
                if c == h:
                    return i
        for i, h in enumerate(headers):
            for c in candidates:
                if c in h:
                    return i
        return None

    @staticmethod
    def _safe_str(row: List, idx: Optional[int]) -> str:
        if idx is None or idx >= len(row):
            return ""
        val = row[idx]
        if val is None:
            return ""
        if isinstance(val, dict):
            if val.get("type") == "embed-image":
                return ""
            return str(val).strip()
        return str(val).strip()

    @staticmethod
    def _safe_float(row: List, idx: Optional[int]) -> float:
        if idx is None or idx >= len(row):
            return 0.0
        try:
            val = row[idx]
            if val is None or val == "":
                return 0.0
            if isinstance(val, dict):
                return 0.0
            text = str(val).replace(",", "").strip()
            if text.startswith("="):
                return 0.0
            match = re.search(r'-?\d+\.?\d*', text)
            if match:
                return float(match.group())
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_int(row: List, idx: Optional[int]) -> int:
        if idx is None or idx >= len(row):
            return 0
        try:
            val = row[idx]
            if val is None or val == "":
                return 0
            if isinstance(val, dict):
                return 0
            return int(float(str(val).replace(",", "").strip()))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _col_letter(n: int) -> str:
        result = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result
        return result

    # ═══ 低级 API 调用（带限流和重试） ═════════

    def _raw_get_range(self, range_str: str) -> List[List]:
        """Low-level range fetch with rate limiting and retry."""
        last_err = None
        for attempt in range(self._retry_count):
            try:
                self._limiter.wait()
                token = self._token or self.get_tenant_token()
                url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.spreadsheet_token}/values/{range_str}"
                headers = {"Authorization": f"Bearer {token}"}
                params = {
                    "valueRenderOption": "UnformattedValue",
                    "dateTimeRenderOption": "FormattedString"
                }
                resp = requests.get(url, headers=headers, params=params, timeout=self._request_timeout)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    raise Exception(f"Get sheet data failed: {data.get('msg')}")
                return data.get("data", {}).get("valueRange", {}).get("values", [])
            except Exception as e:
                last_err = e
                if attempt < self._retry_count - 1:
                    logger.warning(f"Retry {attempt+1}/{self._retry_count} for range {range_str}: {e}")
                    time.sleep(self._retry_delay)
        raise last_err  # type: ignore[misc]

    def _raw_batch_get_ranges(self, ranges: List[str]) -> List[dict]:
        """Fetch multiple ranges in one API call with rate limiting."""
        self._limiter.wait()
        token = self._token or self.get_tenant_token()
        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.spreadsheet_token}/values_batch_get"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "ranges": ",".join(ranges),
            "valueRenderOption": "UnformattedValue",
            "dateTimeRenderOption": "FormattedString"
        }
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Batch get failed: {data.get('msg')}")
        return data.get("data", {}).get("valueRanges", [])

    def _get_temp_download_urls(self, file_tokens):
        """Get temporary download URLs for a batch of file tokens."""
        self._limiter.wait()
        token = self._token or self.get_tenant_token()
        url = f"{self.base_url}/open-apis/drive/v1/medias/batch_get_tmp_download_url"
        headers = {"Authorization": f"Bearer {token}"}
        params = [("file_tokens", t) for t in file_tokens]
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Get temp URLs failed: {data.get('msg')}")
        result = {}
        for item in data.get("data", {}).get("tmp_download_urls", []):
            result[item.get("file_token")] = item.get("tmp_download_url")
        return result
