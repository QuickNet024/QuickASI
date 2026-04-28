# -*- coding: utf-8 -*-
"""
WB亏损计算系统 — 版本管理

- APP_VERSION: 项目整体版本号
- MODULE_VERSIONS: 每个接口模块的独立版本号

升级模块时只改对应版本号即可。
"""

APP_VERSION = "2.5.0"
APP_NAME = "WB亏损计算系统"

# ═══ 接口模块版本 ═══════════════════════════════
# key = module_id, value = 语义版本号
MODULE_VERSIONS = {
    "feishu":        "1.3.0",   # 飞书数据同步 — 同步数据一致性 + 增量图片下载
    "commission":    "1.0.0",   # 佣金数据
    "exchange_rate": "1.0.0",   # 汇率数据
    "shipping":      "1.0.0",   # 运费配置
}


def get_app_version() -> str:
    """返回项目版本号，带 v 前缀"""
    return f"v{APP_VERSION}"


def get_module_version(module_id: str) -> str:
    """返回指定模块的版本号"""
    return MODULE_VERSIONS.get(module_id, "0.0.0")


def get_all_versions() -> dict:
    """返回完整版本信息 dict"""
    return {
        "app": APP_VERSION,
        "modules": dict(MODULE_VERSIONS),
    }


def get_version_text() -> str:
    """返回单行版本摘要文字（用于状态栏等）"""
    return f"{APP_NAME} v{APP_VERSION}"
