# -*- coding: utf-8 -*-
"""SQLite数据库管理器（单例模式，线程安全）"""

import sqlite3
import os
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from datetime import datetime

from src.config import Config
from src.models.product import Product
from src.models.commission import Commission

# Register datetime adapter for Python 3.12+
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())


class DatabaseManager:
    """SQLite数据库管理器（单例模式，线程安全）"""

    _instance = None

    def __new__(cls, db_path=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._db_path = db_path or Config.DB_PATH
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path=None):
        if self._initialized:
            return
        self._db_path = db_path or Config.DB_PATH
        self._ensure_dir()
        self._init_tables()
        self._migrate_tables()
        self._initialized = True

    def _ensure_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_conn(self):
        """每次调用创建新连接——线程安全，自动提交并关闭。"""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @property
    def connection(self):
        """向后兼容属性——创建新连接。"""
        return self._get_conn()

    def close(self):
        """不再持有持久连接，无需关闭。"""
        pass

    def _init_tables(self):
        """初始化所有表"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_code TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    distribution_price REAL DEFAULT 0,
                    dimensions TEXT DEFAULT '',
                    weight REAL DEFAULT 0,
                    category TEXT DEFAULT '',
                    chinese_name TEXT DEFAULT '',
                    brand TEXT DEFAULT '',
                    inventory INTEGER DEFAULT 0,
                    synced_at TIMESTAMP,
                    UNIQUE(sku_code, sheet_name)
                );

                CREATE TABLE IF NOT EXISTS commissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT DEFAULT '',
                    product TEXT DEFAULT '',
                    rate REAL DEFAULT 0,
                    source TEXT DEFAULT 'wb_fbs',
                    platform TEXT DEFAULT 'wb',
                    shop_type TEXT DEFAULT 'local'
                );

                CREATE TABLE IF NOT EXISTS exchange_rates (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    cny_to_rub REAL DEFAULT 0,
                    rub_to_cny REAL DEFAULT 0,
                    updated_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT ''
                );
            """)

    def _migrate_tables(self):
        """为已有DB添加新列"""
        with self._get_conn() as conn:
            try:
                conn.execute("ALTER TABLE products ADD COLUMN inventory INTEGER DEFAULT 0")
            except Exception:
                pass  # 列已存在
            # Add new columns for feishu-sync-enhancement
            for col_name, col_type in [
                ("image_file_token", "TEXT"),
                ("image_local_path", "TEXT"),
                ("original_price", "REAL"),
                ("supplier", "TEXT"),
                ("remarks", "TEXT"),
                ("inventory_status", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type} DEFAULT ''")
                except Exception:
                    pass
            # Add commission multi-type columns
            for col_name, col_default in [
                ("platform", "'wb'"),
                ("shop_type", "'local'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE commissions ADD COLUMN {col_name} TEXT DEFAULT {col_default}")
                except Exception:
                    pass  # Column already exists

    # ── Product CRUD ──

    def insert_product(self, product: Product) -> int:
        """插入或更新产品"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO products
                (sku_code, sheet_name, distribution_price, dimensions, weight,
                 category, chinese_name, brand, inventory, inventory_status, synced_at,
                 image_file_token, image_local_path, original_price, supplier, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (product.sku_code, product.sheet_name, product.distribution_price,
                  product.dimensions, product.weight, product.category,
                  product.chinese_name, product.brand, product.inventory, product.inventory_status, product.synced_at,
                  product.image_file_token, product.image_local_path, product.original_price,
                  product.supplier, product.remarks))
            return cursor.lastrowid or 0

    def insert_products_batch(self, products: List[Product]) -> int:
        """批量插入产品"""
        count = 0
        with self._get_conn() as conn:
            for p in products:
                conn.execute("""
                    INSERT OR REPLACE INTO products
                    (sku_code, sheet_name, distribution_price, dimensions, weight,
                     category, chinese_name, brand, inventory, inventory_status, synced_at,
                     image_file_token, image_local_path, original_price, supplier, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p.sku_code, p.sheet_name, p.distribution_price,
                      p.dimensions, p.weight, p.category,
                      p.chinese_name, p.brand, p.inventory, p.inventory_status, p.synced_at,
                      p.image_file_token, p.image_local_path, p.original_price,
                      p.supplier, p.remarks))
                count += 1
        return count

    def get_product_by_sku(self, sku_code: str) -> Optional[Product]:
        """按SKU查找产品"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE sku_code = ?", (sku_code,)
            ).fetchone()
            if row:
                return self._row_to_product(row)
            return None

    def get_products_by_sheet_prefix(self, prefix: str) -> List[Product]:
        """按sheet名前缀查找产品。Sheet名格式为"Category-Prefix"(如"数码-3C5")"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM products WHERE sheet_name LIKE ?", (f"%-{prefix}",)
            ).fetchall()
            return [self._row_to_product(r) for r in rows]

    def get_all_products(self) -> List[Product]:
        """获取所有产品"""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM products").fetchall()
            return [self._row_to_product(r) for r in rows]

    def get_product_count(self) -> int:
        """获取产品总数"""
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    def get_last_product_sync_time(self) -> str:
        """获取产品最后同步时间"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(synced_at) FROM products"
            ).fetchone()
            if row and row[0]:
                return str(row[0])[:16]
            return ""

    def clear_products(self):
        """清空产品表"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM products")

    def _row_to_product(self, row) -> Product:
        # DB column order: id, sku_code, sheet_name, distribution_price, dimensions,
        # weight, category, chinese_name, brand, synced_at, inventory,
        # image_file_token, image_local_path, original_price, supplier, remarks, inventory_status
        return Product(
            id=row[0], sku_code=row[1], sheet_name=row[2],
            distribution_price=row[3], dimensions=row[4], weight=row[5],
            category=row[6], chinese_name=row[7], brand=row[8],
            inventory=row[10] if len(row) > 10 and row[10] is not None else 0,
            inventory_status=row[16] if len(row) > 16 and row[16] is not None else "",
            synced_at=row[9],
            image_file_token=row[11] if len(row) > 11 else "",
            image_local_path=row[12] if len(row) > 12 else "",
            original_price=float(row[13]) if len(row) > 13 and row[13] not in (None, "") else 0.0,
            supplier=row[14] if len(row) > 14 else "",
            remarks=row[15] if len(row) > 15 else "",
        )

    # ── Commission CRUD ──

    def insert_commission(self, commission: Commission) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO commissions (category, product, rate, source, platform, shop_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (commission.category, commission.product, commission.rate,
                  commission.source, commission.platform, commission.shop_type))
            return cursor.lastrowid or 0

    def insert_commissions_batch(self, commissions: List[Commission]) -> int:
        count = 0
        with self._get_conn() as conn:
            for c in commissions:
                conn.execute("""
                    INSERT INTO commissions (category, product, rate, source, platform, shop_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (c.category, c.product, c.rate, c.source, c.platform, c.shop_type))
                count += 1
        return count

    def find_commission_by_product(self, product_name: str,
                                    platform: str = None,
                                    shop_type: str = None) -> Optional[float]:
        """按商品名查找佣金率，可选按平台+店铺类型过滤"""
        with self._get_conn() as conn:
            sql = "SELECT rate FROM commissions WHERE product = ?"
            params = [product_name]
            if platform:
                sql += " AND platform = ?"
                params.append(platform)
            if shop_type:
                sql += " AND shop_type = ?"
                params.append(shop_type)
            sql += " LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else None

    def find_commission_by_category(self, category_name: str,
                                     platform: str = None,
                                     shop_type: str = None) -> Optional[float]:
        """按品类查找佣金率，可选按平台+店铺类型过滤"""
        with self._get_conn() as conn:
            sql = "SELECT rate FROM commissions WHERE category = ?"
            params = [category_name]
            if platform:
                sql += " AND platform = ?"
                params.append(platform)
            if shop_type:
                sql += " AND shop_type = ?"
                params.append(shop_type)
            sql += " LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else None

    def get_all_commissions(self) -> List[Commission]:
        """获取所有佣金数据"""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM commissions ORDER BY category, product").fetchall()
            return [self._row_to_commission(r) for r in rows]

    def _row_to_commission(self, row) -> Commission:
        return Commission(
            id=row[0], category=row[1], product=row[2],
            rate=row[3], source=row[4],
            platform=row[5] if len(row) > 5 else "wb",
            shop_type=row[6] if len(row) > 6 else "local",
        )

    def clear_commissions(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM commissions")

    def clear_commissions_by_type(self, platform: str, shop_type: str):
        """清空指定平台+店铺类型的佣金数据"""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM commissions WHERE platform = ? AND shop_type = ?",
                (platform, shop_type))

    def get_commission_count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM commissions").fetchone()[0]

    def get_commission_count_by_type(self, platform: str, shop_type: str) -> int:
        """获取指定平台+店铺类型的佣金数量"""
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM commissions WHERE platform = ? AND shop_type = ?",
                (platform, shop_type)).fetchone()[0]

    # ── Exchange Rate ──

    def save_exchange_rate(self, cny_to_rub: float, rub_to_cny: float):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO exchange_rates (id, cny_to_rub, rub_to_cny, updated_at)
                VALUES (1, ?, ?, ?)
            """, (cny_to_rub, rub_to_cny, datetime.now()))

    def get_exchange_rate(self) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM exchange_rates WHERE id = 1").fetchone()
            if row:
                return {"cny_to_rub": row[1], "rub_to_cny": row[2], "updated_at": row[3]}
            return None

    # ── App Config ──

    def save_config(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, value))

    def get_config(self, key: str, default: str = "") -> str:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def get_all_config(self) -> Dict[str, str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM app_config").fetchall()
            return {r[0]: r[1] for r in rows}

    @classmethod
    def reset_instance(cls):
        """重置单例（仅用于测试）"""
        cls._instance = None
