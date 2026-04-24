# -*- coding: utf-8 -*-
"""SQLite数据库管理器（普通类，支持按模块初始化表，线程安全）"""

import sqlite3
import os
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from datetime import datetime

from src.models.product import Product
from src.models.commission import Commission, CommissionTableInfo

# Register datetime adapter for Python 3.12+
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())


class DatabaseManager:
    """SQLite数据库管理器 — 可指定路径和要初始化的表，线程安全。

    用法:
        # 全部表（向后兼容 / 测试）
        db = DatabaseManager("data/test.db")

        # 仅特定表（按模块）
        db = DatabaseManager("data/feishu.db", init_tables=["products", "app_config"])

        # 不自动建表（仅打开已有DB）
        db = DatabaseManager("data/existing.db", init_tables=[])
    """

    def __init__(self, db_path: str = "data/loss_calc.db", init_tables: list = None):
        """
        Args:
            db_path: 数据库文件路径
            init_tables: 要初始化的表列表，如 ['products', 'app_config']。
                         None 表示初始化全部表，[] 表示不初始化任何表。
        """
        self._db_path = db_path
        self._ensure_dir()

        if init_tables is None:
            # 向后兼容：初始化所有表
            self._init_all_tables()
            self._migrate_all_tables()
        elif len(init_tables) > 0:
            self._init_selected_tables(init_tables)
            self._migrate_selected_tables(init_tables)

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
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
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

    # ── 表初始化（分表方法） ──────────────────────────

    def _init_all_tables(self):
        """初始化全部表"""
        with self._get_conn() as conn:
            self._create_products_table(conn)
            self._create_commissions_table(conn)
            self._create_commission_meta_table(conn)
            self._create_import_rows_table(conn)
            self._create_calc_results_table(conn)
            self._create_exchange_rates_table(conn)
            self._create_app_config_table(conn)

    def _init_selected_tables(self, tables: list):
        """仅初始化指定表"""
        with self._get_conn() as conn:
            if "products" in tables:
                self._create_products_table(conn)
            if "commissions" in tables:
                self._create_commissions_table(conn)
            if "commission_meta" in tables:
                self._create_commission_meta_table(conn)
            if "import_rows" in tables:
                self._create_import_rows_table(conn)
            if "calc_results" in tables:
                self._create_calc_results_table(conn)
            if "exchange_rates" in tables:
                self._create_exchange_rates_table(conn)
            if "app_config" in tables:
                self._create_app_config_table(conn)

    @staticmethod
    def _create_products_table(conn):
        conn.execute("""
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
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sheet ON products(sheet_name)")

    @staticmethod
    def _create_commissions_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT DEFAULT '',
                product TEXT DEFAULT '',
                rate REAL DEFAULT 0,
                source TEXT DEFAULT 'wb_fbs',
                platform TEXT DEFAULT 'wb',
                shop_type TEXT DEFAULT 'local'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commissions_cat ON commissions(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commissions_prod ON commissions(product)")

    @staticmethod
    def _create_exchange_rates_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id INTEGER PRIMARY KEY DEFAULT 1,
                cny_to_rub REAL DEFAULT 0,
                rub_to_cny REAL DEFAULT 0,
                updated_at TIMESTAMP
            )
        """)

    @staticmethod
    def _create_app_config_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)

    @staticmethod
    def _create_commission_meta_table(conn):
        """创建佣金表元数据表"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commission_table_info (
                table_name TEXT PRIMARY KEY,
                platform TEXT,
                shop_type TEXT,
                source_file TEXT DEFAULT '',
                column_headers TEXT DEFAULT '[]',
                rate_columns TEXT DEFAULT '[]',
                row_count INTEGER DEFAULT 0,
                imported_at TIMESTAMP
            )
        """)

    @staticmethod
    def _create_import_rows_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS import_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_number INTEGER DEFAULT 0,
                brand TEXT DEFAULT '',
                category TEXT DEFAULT '',
                wb_article TEXT DEFAULT '',
                seller_sku TEXT DEFAULT '',
                barcode TEXT DEFAULT '',
                wb_stock TEXT DEFAULT '',
                seller_stock TEXT DEFAULT '',
                turnover TEXT DEFAULT '',
                current_price TEXT DEFAULT '',
                new_price REAL,
                current_discount INTEGER,
                new_discount INTEGER,
                import_batch TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_import_sku ON import_rows(seller_sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_import_batch ON import_rows(import_batch)")

    @staticmethod
    def _create_calc_results_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calc_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_row_id INTEGER DEFAULT 0,
                sku_matched INTEGER DEFAULT 0,
                category_matched INTEGER DEFAULT 0,
                matched_product_id INTEGER,
                product_cost REAL,
                product_category TEXT DEFAULT '',
                dimensions TEXT DEFAULT '',
                weight REAL,
                inventory INTEGER,
                inventory_status TEXT DEFAULT '',
                seller_stock TEXT DEFAULT '',
                wb_stock TEXT DEFAULT '',
                commission_rate REAL,
                commission_source TEXT DEFAULT '',
                discounted_price REAL,
                shipping_fee REAL,
                breakeven REAL,
                profit REAL,
                max_discount INTEGER,
                min_price REAL,
                target_discount INTEGER,
                target_price REAL,
                calc_batch TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calc_import_id ON calc_results(import_row_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calc_batch ON calc_results(calc_batch)")

    # ── 迁移（分表方法） ──────────────────────────

    def _migrate_all_tables(self):
        """迁移全部表"""
        with self._get_conn() as conn:
            self._migrate_products(conn)
            self._migrate_commissions(conn)
            self._migrate_calc_results(conn)

    def _migrate_selected_tables(self, tables: list):
        """仅迁移指定表"""
        with self._get_conn() as conn:
            if "products" in tables:
                self._migrate_products(conn)
            if "commissions" in tables:
                self._migrate_commissions(conn)
            if "calc_results" in tables:
                self._migrate_calc_results(conn)

    @staticmethod
    def _migrate_products(conn):
        """为已有DB添加产品表新列"""
        # Add inventory column
        try:
            conn.execute("ALTER TABLE products ADD COLUMN inventory INTEGER DEFAULT 0")
        except Exception:
            pass
        # Add feishu-sync-enhancement columns
        for col_name, col_type in [
            ("image_file_token", "TEXT"),
            ("image_local_path", "TEXT"),
            ("original_price", "REAL"),
            ("supplier", "TEXT"),
            ("remarks", "TEXT"),
            ("inventory_status", "TEXT"),
            ("raw_sync_data", "TEXT"),   # V2: 完整原始行数据 JSON
        ]:
            try:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type} DEFAULT ''")
            except Exception:
                pass

    @staticmethod
    def _migrate_commissions(conn):
        """为已有DB添加佣金表新列"""
        for col_name, col_default in [
            ("platform", "'wb'"),
            ("shop_type", "'local'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE commissions ADD COLUMN {col_name} TEXT DEFAULT {col_default}")
            except Exception:
                pass

    @staticmethod
    def _migrate_calc_results(conn):
        """为calc_results表添加新列"""
        for col_name, col_type, col_default in [
            ("inventory_status", "TEXT", "''"),
            ("seller_stock", "TEXT", "''"),
            ("wb_stock", "TEXT", "''"),
            ("target_discount", "INTEGER", "NULL"),
            ("target_price", "REAL", "NULL"),
            ("weight", "REAL", "NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE calc_results ADD COLUMN {col_name} {col_type} DEFAULT {col_default}")
            except Exception:
                pass

    # ── Product CRUD ──

    def insert_product(self, product: Product) -> int:
        """插入或更新产品"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO products
                (sku_code, sheet_name, distribution_price, dimensions, weight,
                 category, chinese_name, brand, inventory, inventory_status, synced_at,
                 image_file_token, image_local_path, original_price, supplier, remarks,
                 raw_sync_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (product.sku_code, product.sheet_name, product.distribution_price,
                  product.dimensions, product.weight, product.category,
                  product.chinese_name, product.brand, product.inventory, product.inventory_status, product.synced_at,
                  product.image_file_token, product.image_local_path, product.original_price,
                  product.supplier, product.remarks, product.raw_sync_data))
            return cursor.lastrowid or 0

    def insert_products_batch(self, products: List[Product]) -> int:
        """批量插入产品 — 使用 executemany 提升性能"""
        if not products:
            return 0
        rows = []
        for p in products:
            rows.append((
                p.sku_code, p.sheet_name, p.distribution_price,
                p.dimensions, p.weight, p.category,
                p.chinese_name, p.brand, p.inventory, p.inventory_status, p.synced_at,
                p.image_file_token, p.image_local_path, p.original_price,
                p.supplier, p.remarks, p.raw_sync_data
            ))
        with self._get_conn() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO products
                (sku_code, sheet_name, distribution_price, dimensions, weight,
                 category, chinese_name, brand, inventory, inventory_status, synced_at,
                 image_file_token, image_local_path, original_price, supplier, remarks,
                 raw_sync_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
        return len(products)

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

    def update_product_raw_field(self, product_id: int, field_name: str, value):
        """更新产品 raw_sync_data 中的某个字段值"""
        import json as _json
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT raw_sync_data FROM products WHERE id = ?",
                (product_id,)
            ).fetchone()
            if not row:
                return
            raw = {}
            if row[0]:
                try:
                    raw = _json.loads(row[0])
                except (ValueError, TypeError):
                    pass
            raw[field_name] = value
            conn.execute(
                "UPDATE products SET raw_sync_data = ? WHERE id = ?",
                (_json.dumps(raw, ensure_ascii=False), product_id)
            )

    def _row_to_product(self, row) -> Product:
        # DB column order: id, sku_code, sheet_name, distribution_price, dimensions,
        # weight, category, chinese_name, brand, synced_at, inventory,
        # image_file_token, image_local_path, original_price, supplier, remarks, inventory_status
        # raw_sync_data (V2)
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
            raw_sync_data=row[17] if len(row) > 17 and row[17] else "",
        )

    def get_products_raw(self) -> List[dict]:
        """获取所有产品的原始数据（raw_sync_data JSON 解析后 + 元数据）。
        用于 ProductViewer 动态列展示。

        Returns:
            [{"id": int, "sku_code": str, "sheet_name": str, "synced_at": str,
              "image_file_token": str, "image_local_path": str,
              "raw": {col_name: value, ...}}, ...]
        """
        import json as _json
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, sku_code, sheet_name, synced_at, "
                "image_file_token, image_local_path, raw_sync_data FROM products"
            ).fetchall()
        result = []
        for r in rows:
            raw = {}
            if r[6]:
                try:
                    raw = _json.loads(r[6])
                except (_json.JSONDecodeError, TypeError):
                    pass
            result.append({
                "id": r[0],
                "sku_code": r[1],
                "sheet_name": r[2],
                "synced_at": str(r[3])[:16] if r[3] else "",
                "image_file_token": r[4] or "",
                "image_local_path": r[5] or "",
                "raw": raw,
            })
        return result

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
        """批量插入佣金 — 使用 executemany 提升性能"""
        if not commissions:
            return 0
        rows = [
            (c.category, c.product, c.rate, c.source, c.platform, c.shop_type)
            for c in commissions
        ]
        with self._get_conn() as conn:
            conn.executemany("""
                INSERT INTO commissions (category, product, rate, source, platform, shop_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, rows)
        return len(rows)

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

    # ── Dynamic Commission Table Methods ──

    def create_commission_data_table(self, table_name: str, columns: list):
        """动态创建佣金数据表。

        Args:
            table_name: 表名，必须以 "commission_" 开头
            columns: [(db_col_name, col_type), ...] 例如 [("rate_col_0", "REAL"), ...]
        """
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        # Validate column names
        for col_name, _ in columns:
            if not col_name.replace("_", "").isalnum():
                raise ValueError(f"Invalid column name: {col_name}")

        col_defs = ", ".join(f"{col} {typ}" for col, typ in columns)
        with self._get_conn() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.execute(
                f"CREATE TABLE {table_name} ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "category TEXT, "
                "product TEXT, "
                f"{col_defs}"
                ")"
            )
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_cat ON {table_name}(category)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_prod ON {table_name}(product)")

    def import_commission_rows_batch(self, table_name: str, rows: list):
        """批量插入佣金数据到指定动态表。

        Args:
            table_name: 必须以 "commission_" 开头
            rows: list of tuples matching the table schema (category, product, rate_col_0, ...)
        """
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        if not rows:
            return

        placeholders = ", ".join("?" * len(rows[0]))
        col_count = len(rows[0])
        # Build column list: category, product, rate_col_0, ...
        col_names = ["category", "product"] + [f"rate_col_{i}" for i in range(col_count - 2)]
        cols = ", ".join(col_names)

        with self._get_conn() as conn:
            conn.executemany(
                f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})",
                rows
            )

    def save_commission_table_info(self, info: CommissionTableInfo):
        """保存佣金表元数据（INSERT OR REPLACE）"""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO commission_table_info
                (table_name, platform, shop_type, source_file,
                 column_headers, rate_columns, row_count, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (info.table_name, info.platform, info.shop_type, info.source_file,
                  info.column_headers, info.rate_columns, info.row_count, info.imported_at))

    def get_commission_tables(self) -> List[CommissionTableInfo]:
        """获取所有已注册的佣金动态表元数据"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT table_name, platform, shop_type, source_file, "
                "column_headers, rate_columns, row_count, imported_at "
                "FROM commission_table_info"
            ).fetchall()
            return [
                CommissionTableInfo(
                    table_name=r[0], platform=r[1], shop_type=r[2],
                    source_file=r[3] or "", column_headers=r[4] or "[]",
                    rate_columns=r[5] or "[]", row_count=r[6] or 0,
                    imported_at=r[7] or ""
                ) for r in rows
            ]

    def get_commission_table_data(self, table_name: str) -> List[tuple]:
        """获取指定佣金动态表的所有数据"""
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        with self._get_conn() as conn:
            return conn.execute(f"SELECT * FROM {table_name} ORDER BY category, product").fetchall()

    def get_commission_count_by_table(self, table_name: str) -> int:
        """获取指定动态表的行数"""
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        with self._get_conn() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    def find_rate_in_table(self, table_name: str, name: str,
                           rate_col: str = "rate_col_0") -> Optional[float]:
        """在指定动态表中按商品名/品类查找佣金率。

        先匹配 product 列，未找到则匹配 category 列。
        table_name 必须以 "commission_" 开头以防SQL注入。
        """
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        if not rate_col.replace("_", "").isalnum():
            raise ValueError(f"Invalid rate column: {rate_col}")

        with self._get_conn() as conn:
            row = conn.execute(
                f"SELECT {rate_col} FROM {table_name} WHERE product = ? LIMIT 1",
                (name,)
            ).fetchone()
            if row is not None and row[0] is not None:
                return row[0]
            row = conn.execute(
                f"SELECT {rate_col} FROM {table_name} WHERE category = ? LIMIT 1",
                (name,)
            ).fetchone()
            if row is not None and row[0] is not None:
                return row[0]
        return None

    def get_commission_table_columns(self, table_name: str) -> List[str]:
        """获取指定动态表的列名列表（通过 PRAGMA table_info）"""
        if not table_name.startswith("commission_"):
            raise ValueError(f"Invalid table name: {table_name}")
        with self._get_conn() as conn:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            return [r[1] for r in rows]

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

    # ── Import Rows CRUD (折扣推算) ──

    def insert_import_rows_batch(self, rows: list) -> int:
        """批量插入导入行。rows是ImportRow对象列表。返回插入数量。"""
        if not rows:
            return 0
        data = [(r.row_number, r.brand, r.category, r.wb_article, r.seller_sku,
                 r.barcode, r.wb_stock, r.seller_stock, r.turnover, r.current_price,
                 r.new_price, r.current_discount, r.new_discount, r.import_batch)
                for r in rows]
        with self._get_conn() as conn:
            conn.executemany("""
                INSERT INTO import_rows (row_number, brand, category, wb_article, seller_sku,
                    barcode, wb_stock, seller_stock, turnover, current_price,
                    new_price, current_discount, new_discount, import_batch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
        return len(data)

    def get_import_rows(self, batch: str = None) -> list:
        """获取导入行。如果指定batch则只返回该批次的。"""
        with self._get_conn() as conn:
            if batch:
                rows = conn.execute("SELECT * FROM import_rows WHERE import_batch = ? ORDER BY row_number", (batch,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM import_rows ORDER BY id DESC").fetchall()
            return rows

    def get_import_row_count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM import_rows").fetchone()[0]

    def get_latest_import_batch(self) -> str:
        with self._get_conn() as conn:
            row = conn.execute("SELECT import_batch FROM import_rows ORDER BY id DESC LIMIT 1").fetchone()
            return row[0] if row else ""

    def clear_import_rows(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM import_rows")

    # ── Calc Results CRUD (折扣推算) ──

    def insert_calc_results_batch(self, results: list) -> int:
        """批量插入计算结果。results是CalcResultRow对象列表。"""
        if not results:
            return 0
        data = [(r.import_row_id, int(r.sku_matched), int(r.category_matched),
                 r.matched_product_id, r.product_cost, r.product_category,
                 r.dimensions, r.weight, r.inventory, r.inventory_status,
                 r.seller_stock, r.wb_stock,
                 r.commission_rate, r.commission_source,
                 r.discounted_price, r.shipping_fee, r.breakeven, r.profit,
                 r.max_discount, r.min_price, r.target_discount, r.target_price,
                 r.calc_batch)
                for r in results]
        with self._get_conn() as conn:
            conn.executemany("""
                INSERT INTO calc_results (import_row_id, sku_matched, category_matched,
                    matched_product_id, product_cost, product_category,
                    dimensions, weight, inventory, inventory_status,
                    seller_stock, wb_stock,
                    commission_rate, commission_source,
                    discounted_price, shipping_fee, breakeven, profit,
                    max_discount, min_price, target_discount, target_price, calc_batch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
        return len(data)

    def get_calc_results(self, batch: str = None) -> list:
        """获取计算结果。返回元组列表，列顺序固定：
        (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
         4=matched_product_id, 5=product_cost, 6=product_category,
         7=dimensions, 8=weight,
         9=inventory, 10=inventory_status,
         11=seller_stock, 12=wb_stock,
         13=commission_rate, 14=commission_source,
         15=discounted_price, 16=shipping_fee,
         17=breakeven, 18=profit, 19=max_discount, 20=min_price,
         21=target_discount, 22=target_price,
         23=calc_batch)
        """
        sql = """SELECT id, import_row_id, sku_matched, category_matched,
                 matched_product_id, product_cost, product_category,
                 dimensions, weight, inventory, inventory_status,
                 seller_stock, wb_stock,
                 commission_rate, commission_source,
                 discounted_price, shipping_fee, breakeven, profit,
                 max_discount, min_price, target_discount, target_price,
                 calc_batch
                 FROM calc_results"""
        with self._get_conn() as conn:
            if batch:
                rows = conn.execute(sql + " WHERE calc_batch = ? ORDER BY id", (batch,)).fetchall()
            else:
                rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
            return rows

    def get_calc_result_count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM calc_results").fetchone()[0]

    def clear_calc_results(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM calc_results")
