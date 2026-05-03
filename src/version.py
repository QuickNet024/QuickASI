# -*- coding: utf-8 -*-
"""
WB浜忔崯璁＄畻绯荤粺 鈥?鐗堟湰绠＄悊

- APP_VERSION: 椤圭洰鏁翠綋鐗堟湰鍙?- MODULE_VERSIONS: 姣忎釜鎺ュ彛妯″潡鐨勭嫭绔嬬増鏈彿

鍗囩骇妯″潡鏃跺彧鏀瑰搴旂増鏈彿鍗冲彲銆?"""

APP_VERSION = "2.6.0"
APP_NAME = "WB浜忔崯璁＄畻绯荤粺"

# 鈺愨晲鈺?鎺ュ彛妯″潡鐗堟湰 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# key = module_id, value = 璇箟鐗堟湰鍙?MODULE_VERSIONS = {
    "feishu":        "1.4.0",   # 椋炰功鏁版嵁鍚屾 鈥?鍚屾鏁版嵁涓€鑷存€?+ 澧為噺鍥剧墖涓嬭浇
    "commission":    "1.0.0",   # 浣ｉ噾鏁版嵁
    "exchange_rate": "1.0.0",   # 姹囩巼鏁版嵁
    "shipping":      "1.0.0",   # 杩愯垂閰嶇疆
}


def get_app_version() -> str:
    """杩斿洖椤圭洰鐗堟湰鍙凤紝甯?v 鍓嶇紑"""
    return f"v{APP_VERSION}"


def get_module_version(module_id: str) -> str:
    """杩斿洖鎸囧畾妯″潡鐨勭増鏈彿"""
    return MODULE_VERSIONS.get(module_id, "0.0.0")


def get_all_versions() -> dict:
    """杩斿洖瀹屾暣鐗堟湰淇℃伅 dict"""
    return {
        "app": APP_VERSION,
        "modules": dict(MODULE_VERSIONS),
    }


def get_version_text() -> str:
    """杩斿洖鍗曡鐗堟湰鎽樿鏂囧瓧锛堢敤浜庣姸鎬佹爮绛夛級"""
    return f"{APP_NAME} v{APP_VERSION}"
