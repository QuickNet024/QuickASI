# -*- coding: utf-8 -*-
"""接口配置管理器 — 每个接口模块独立的 JSON 配置文件

配置优先级: DB app_config > config/{module_id}.json > 代码默认值
纯 Python 实现，无 Qt 依赖，可被 Web/Win 程序直接调用。
"""

import json
import os
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 配置文件根目录（相对于项目根目录）
CONFIG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")


class InterfaceConfig:
    """单个接口模块的配置管理器。

    用法:
        cfg = InterfaceConfig("feishu", defaults={
            "sync.thread_count": 4,
            "sync.rate_limit": 5.0,
        })
        threads = cfg.get("sync.thread_count")  # 返回 4
        cfg.set("sync.rate_limit", 10.0)        # 写入 DB + 文件
    """

    def __init__(self, module_id: str, defaults: Optional[Dict[str, Any]] = None, db=None):
        """
        Args:
            module_id: 模块ID，如 "feishu", "exchange_rate"
            defaults: 默认配置字典（嵌套结构会自动打平）
            db: DatabaseManager 实例（可选，为 None 时仅使用文件）
        """
        self._module_id = module_id
        self._db = db
        self._defaults = defaults or {}
        self._file_path = os.path.join(CONFIG_ROOT, f"{module_id}.json")
        self._lock = threading.Lock()
        self._file_cache: Optional[Dict] = None

    # ═══ 读取 ═══════════════════════════════════

    def get(self, key: str, default: Any = None) -> Any:
        """读取配置值。优先级: DB → 文件 → 默认值 → 参数 default"""
        # 1. DB 最高优先级（运行时修改）
        db_val = self._get_from_db(key)
        if db_val is not None:
            return db_val

        # 2. 配置文件
        file_val = self._get_from_file(key)
        if file_val is not None:
            return file_val

        # 3. 代码默认值
        if key in self._defaults:
            return self._defaults[key]

        # 4. 参数 default
        return default

    def get_all(self) -> Dict[str, Any]:
        """返回合并后的完整配置（defaults + file + DB overrides）"""
        result = {}

        # 1. 代码默认值
        result.update(self._defaults)

        # 2. 文件配置覆盖
        file_cfg = self._read_file()
        if file_cfg:
            result.update(file_cfg)

        # 3. DB 覆盖
        if self._db:
            try:
                db_cfg_raw = self._db.get_config(f"{self._module_id}_config_overrides", "")
                if db_cfg_raw:
                    db_overrides = json.loads(db_cfg_raw)
                    result.update(db_overrides)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to read DB overrides for {self._module_id}: {e}")

        return result

    def get_section(self, section: str) -> Dict[str, Any]:
        """获取某个配置段的完整字典。
        
        例: cfg.get_section("sync") → {"thread_count": 4, "rate_limit": 5.0, ...}
        """
        all_cfg = self.get_all()
        section_data = {}
        prefix = f"{section}."
        for k, v in all_cfg.items():
            if k.startswith(prefix):
                sub_key = k[len(prefix):]
                section_data[sub_key] = v
        # 也检查嵌套字典形式
        if section in all_cfg and isinstance(all_cfg[section], dict):
            section_data.update(all_cfg[section])
        return section_data

    # ═══ 写入 ═══════════════════════════════════

    def set(self, key: str, value: Any):
        """写入配置值（同时更新 DB + 文件）"""
        with self._lock:
            # 更新文件
            file_cfg = self._read_file()
            if file_cfg is None:
                file_cfg = {}
            file_cfg[key] = value
            self._write_file(file_cfg)
            self._file_cache = file_cfg

            # 更新 DB（作为 override 层）
            if self._db:
                try:
                    db_raw = self._db.get_config(f"{self._module_id}_config_overrides", "")
                    db_overrides = json.loads(db_raw) if db_raw else {}
                    db_overrides[key] = value
                    self._db.save_config(
                        f"{self._module_id}_config_overrides",
                        json.dumps(db_overrides, ensure_ascii=False)
                    )
                except Exception as e:
                    logger.warning(f"Failed to write DB override for {self._module_id}.{key}: {e}")

    def set_many(self, updates: Dict[str, Any]):
        """批量写入多个配置值"""
        with self._lock:
            # 更新文件
            file_cfg = self._read_file() or {}
            file_cfg.update(updates)
            self._write_file(file_cfg)
            self._file_cache = file_cfg

            # 更新 DB
            if self._db:
                try:
                    db_raw = self._db.get_config(f"{self._module_id}_config_overrides", "")
                    db_overrides = json.loads(db_raw) if db_raw else {}
                    db_overrides.update(updates)
                    self._db.save_config(
                        f"{self._module_id}_config_overrides",
                        json.dumps(db_overrides, ensure_ascii=False)
                    )
                except Exception as e:
                    logger.warning(f"Failed to batch write DB overrides for {self._module_id}: {e}")

    def save_to_file(self, config: Dict[str, Any]):
        """将完整配置写入文件（覆盖式）"""
        with self._lock:
            self._write_file(config)
            self._file_cache = config

    def reload(self):
        """清除缓存，下次读取时重新从文件加载"""
        with self._lock:
            self._file_cache = None

    # ═══ 内部方法 ═══════════════════════════════

    def _get_from_db(self, key: str) -> Optional[Any]:
        """从 DB 读取特定 key，支持 dot-notation 嵌套访问"""
        if not self._db:
            return None
        try:
            db_raw = self._db.get_config(f"{self._module_id}_config_overrides", "")
            if db_raw:
                db_overrides = json.loads(db_raw)
                # 先尝试直接匹配
                if key in db_overrides:
                    return db_overrides[key]
                # 再尝试 dot-notation 嵌套
                parts = key.split(".")
                current = db_overrides
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return None
                return current
        except (json.JSONDecodeError, Exception):
            pass
        return None

    def _get_from_file(self, key: str) -> Optional[Any]:
        """从文件读取特定 key，支持 dot-notation 嵌套访问"""
        file_cfg = self._read_file()
        if file_cfg is None:
            return None
        # 先尝试直接匹配（扁平键）
        if key in file_cfg:
            return file_cfg[key]
        # 再尝试 dot-notation 嵌套访问: "sync.thread_count" → file_cfg["sync"]["thread_count"]
        parts = key.split(".")
        current = file_cfg
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _read_file(self) -> Optional[Dict]:
        """读取 JSON 配置文件"""
        if self._file_cache is not None:
            return self._file_cache

        if not os.path.exists(self._file_path):
            return None

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read config file {self._file_path}: {e}")
            return None

    def _write_file(self, config: Dict[str, Any]):
        """写入 JSON 配置文件"""
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Failed to write config file {self._file_path}: {e}")

    @property
    def file_path(self) -> str:
        """配置文件路径"""
        return self._file_path

    @property
    def module_id(self) -> str:
        return self._module_id


def ensure_config_dir():
    """确保配置目录存在"""
    os.makedirs(CONFIG_ROOT, exist_ok=True)
