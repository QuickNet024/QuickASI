# -*- coding: utf-8 -*-
"""数据迁移脚本 — 将旧 loss_calc.db 的数据拆分到独立模块数据库

用法: python scripts/migrate_db.py
前置: 确保 src/ 目录可导入（从项目根目录运行）

迁移策略:
- products        → data/feishu.db
- commissions     → data/commission.db
- exchange_rates  → data/exchange_rate.db
- app_config      → data/app.db（全部 key-value，包括主题、参数、接口启用状态等）
"""

import os
import sys
import sqlite3
import shutil

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

OLD_DB = os.path.join(DATA_DIR, "loss_calc.db")
APP_DB = os.path.join(DATA_DIR, "app.db")
FEISHU_DB = os.path.join(DATA_DIR, "feishu.db")
COMMISSION_DB = os.path.join(DATA_DIR, "commission.db")
EXCHANGE_RATE_DB = os.path.join(DATA_DIR, "exchange_rate.db")

BACKUP_SUFFIX = ".bak_pre_migration"


def migrate_table(old_conn, new_db_path, table_name, init_tables):
    """将旧库的一张表迁移到新库。

    Args:
        old_conn: 旧库连接
        new_db_path: 新库文件路径
        table_name: 表名
        init_tables: 需要初始化的表列表（传入 DatabaseManager）
    """
    if not os.path.exists(new_db_path):
        print(f"  跳过 {table_name}: 目标库 {new_db_path} 不存在（应由应用自动创建）")
        return 0

    # 读取旧库数据
    rows = old_conn.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        print(f"  跳过 {table_name}: 0 行数据")
        return 0

    columns = [desc[0] for desc in old_conn.execute(f"SELECT * FROM {table_name} LIMIT 0").description]
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)

    # 写入新库（使用 INSERT OR IGNORE 避免主键冲突）
    new_conn = sqlite3.connect(new_db_path)
    count = 0
    for row in rows:
        try:
            new_conn.execute(
                f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})",
                row
            )
            count += 1
        except Exception as e:
            print(f"    警告: 跳过一行 ({e})")
    new_conn.commit()
    new_conn.close()

    print(f"  {table_name}: 迁移 {count}/{len(rows)} 行 → {os.path.basename(new_db_path)}")
    return count


def migrate_app_config(old_conn):
    """迁移 app_config 表到 app.db。
    需要特殊处理：只迁移非模块特有的 key，模块特有的 key 迁移到对应模块 DB。

    app_config key 分布:
    - 全局 key (theme, risk_rate, dropship_fee, ...): → app.db
    - feishu_sync_config: → feishu.db
    - enabled_interfaces: → app.db（接口启用状态是全局的）
    - *_commission_api_*: → commission.db
    - exchange_rate_*: → exchange_rate.db
    """
    rows = old_conn.execute("SELECT key, value FROM app_config").fetchall()
    if not rows:
        print("  app_config: 0 行数据")
        return

    # 分类 key
    feishu_keys = {"feishu_sync_config"}
    commission_prefixes = ("wb_commission_", "ozon_commission_", "market_commission_")
    exchange_rate_prefixes = ("exchange_rate_",)
    # 其余全部归 app.db

    app_rows = []
    feishu_rows = []
    commission_rows = []
    exchange_rate_rows = []

    for key, value in rows:
        if key in feishu_keys or key.startswith("feishu_"):
            feishu_rows.append((key, value))
        elif key.startswith(commission_prefixes):
            commission_rows.append((key, value))
        elif key.startswith(exchange_rate_prefixes):
            exchange_rate_rows.append((key, value))
        else:
            app_rows.append((key, value))

    # 写入各库
    for db_path, label, data_rows in [
        (APP_DB, "app.db (全局)", app_rows),
        (FEISHU_DB, "feishu.db (飞书)", feishu_rows),
        (COMMISSION_DB, "commission.db (佣金)", commission_rows),
        (EXCHANGE_RATE_DB, "exchange_rate.db (汇率)", exchange_rate_rows),
    ]:
        if not data_rows:
            continue
        if not os.path.exists(db_path):
            print(f"    跳过 {label}: 目标库不存在")
            continue
        conn = sqlite3.connect(db_path)
        for key, value in data_rows:
            conn.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        print(f"    {label}: {len(data_rows)} 条配置")

    print(f"  app_config: 共 {len(rows)} 条配置已分发到各模块数据库")


def main():
    print("=" * 60)
    print("数据迁移: loss_calc.db → 独立模块数据库")
    print("=" * 60)

    # 检查旧库是否存在
    if not os.path.exists(OLD_DB):
        print("旧数据库 loss_calc.db 不存在，无需迁移")
        return

    # 先启动一次应用，让它创建新的独立数据库文件
    print("\n检查目标数据库文件...")
    for db_path, name in [
        (APP_DB, "app.db"),
        (FEISHU_DB, "feishu.db"),
        (COMMISSION_DB, "commission.db"),
        (EXCHANGE_RATE_DB, "exchange_rate.db"),
    ]:
        if os.path.exists(db_path):
            print(f"  ✓ {name} 已存在")
        else:
            print(f"  ✗ {name} 不存在，需要先启动一次应用以创建")

    # 备份旧库
    backup_path = OLD_DB + BACKUP_SUFFIX
    if not os.path.exists(backup_path):
        shutil.copy2(OLD_DB, backup_path)
        print(f"\n已备份旧库: {os.path.basename(backup_path)}")
    else:
        print(f"\n备份已存在，跳过: {os.path.basename(backup_path)}")

    # 打开旧库
    old_conn = sqlite3.connect(OLD_DB)

    # 迁移各表
    print("\n开始迁移数据...")
    print("\n[1/4] 产品数据 (products → feishu.db)")
    migrate_table(old_conn, FEISHU_DB, "products", ["products", "app_config"])

    print("\n[2/4] 佣金数据 (commissions → commission.db)")
    migrate_table(old_conn, COMMISSION_DB, "commissions", ["commissions", "app_config"])

    print("\n[3/4] 汇率数据 (exchange_rates → exchange_rate.db)")
    migrate_table(old_conn, EXCHANGE_RATE_DB, "exchange_rates", ["exchange_rates", "app_config"])

    print("\n[4/4] 应用配置 (app_config → 各模块数据库)")
    migrate_app_config(old_conn)

    old_conn.close()

    print("\n" + "=" * 60)
    print("迁移完成!")
    print(f"  旧库保留: {OLD_DB} (备份: {os.path.basename(backup_path)})")
    print("  可手动删除旧库: del data\\loss_calc.db")
    print("=" * 60)


if __name__ == "__main__":
    main()
