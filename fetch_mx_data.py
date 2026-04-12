#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
妙想金融数据源 (mx-data)
通过东方财富妙想 API 获取涨停数据，作为 push2ex 接口的替代方案。

需要设置环境变量 MX_APIKEY（在妙想 Skills 页面获取）
"""

import json
import os
from typing import List, Dict, Any, Optional

import requests


MX_BASE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"


def _mx_query(tool_query: str, api_key: str) -> Dict[str, Any]:
    """调用妙想 API"""
    headers = {
        "Content-Type": "application/json",
        "apikey": api_key,
    }
    data = {"toolQuery": tool_query}
    resp = requests.post(MX_BASE_URL, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _extract_stocks_from_mx(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从妙想 API 返回结果中提取涨停股票列表。
    妙想 API 返回的是标准化表格数据，需要解析 dataTableDTOList。
    """
    status = result.get("status")
    if status != 0:
        print(f"❌ 妙想 API 错误: {result.get('message', '未知错误')}")
        return []

    data = result.get("data", {})
    # DEBUG: 打印返回结构的关键路径
    print(f"🔍 [DEBUG] result keys: {list(result.keys())}")
    print(f"🔍 [DEBUG] data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    inner_data = data.get("data", {})
    print(f"🔍 [DEBUG] inner_data keys: {list(inner_data.keys()) if isinstance(inner_data, dict) else type(inner_data)}")
    # 检查多个可能的路径
    print(f"🔍 [DEBUG] inner_data.dataTableDTOList: {len(inner_data.get('dataTableDTOList', []))}")
    search_result = inner_data.get("searchDataResultDTO", {})
    print(f"🔍 [DEBUG] search_result keys: {list(search_result.keys()) if isinstance(search_result, dict) else type(search_result)}")
    print(f"🔍 [DEBUG] search_result.dataTableDTOList: {len(search_result.get('dataTableDTOList', []))}")
    # 打印 inner_data 的完整结构（截断）
    inner_data_str = json.dumps(inner_data, ensure_ascii=False)
    print(f"🔍 [DEBUG] inner_data full (first 3000 chars): {inner_data_str[:3000]}")

    # 优先从 inner_data 直接取 dataTableDTOList，其次从 searchDataResultDTO 取
    dto_list = inner_data.get("dataTableDTOList", []) or search_result.get("dataTableDTOList", [])
    print(f"🔍 [DEBUG] final dto_list count: {len(dto_list)}")

    if not dto_list:
        print("⚠️ 妙想 API 返回数据为空")
        return []

    stocks = []
    for dto in dto_list:
        table = dto.get("table") or {}
        name_map = dto.get("nameMap") or {}

        if isinstance(name_map, list):
            name_map = {str(i): v for i, v in enumerate(name_map)}

        head_names = table.get("headName") or []

        # 检测是否有多行数据（每行一只股票）
        # 如果 headName 长度 > 1，则每行是一个日期/维度
        # 如果 headName 长度 == 0 且有 headNameSub，则可能是按股票列表
        indicator_keys = [k for k in table.keys() if k != "headName"]
        if not indicator_keys:
            continue

        # 取第一个指标列的长度作为行数
        first_indicator = table.get(indicator_keys[0], [])
        row_count = len(first_indicator)

        # 尝试构建字段映射（妙想 API 编码 → 标准字段名）
        # 通过 nameMap 识别关键字段
        code_field = _find_field(name_map, ["股票代码", "代码", "secuCode", "证券代码"])
        name_field = _find_field(name_map, ["股票名称", "名称", "证券简称", "secuName"])
        change_field = _find_field(name_map, ["涨跌幅", "涨跌", "涨幅"])
        amount_field = _find_field(name_map, ["成交额", "成交金额", "总金额"])
        turnover_field = _find_field(name_map, ["换手率", "换手"])
        price_field = _find_field(name_map, ["最新价", "收盘价", "涨停价"])
        reason_field = _find_field(name_map, ["所属行业", "行业", "概念", "板块", "涨停原因"])

        for i in range(row_count):
            stock = {
                "code": _get_value(table, code_field, i) or "",
                "name": _get_value(table, name_field, i) or "",
                "bd": 1,  # 妙想默认不提供连板数
                "amount": _parse_amount(_get_value(table, amount_field, i)),
                "turnover": _parse_float(_get_value(table, turnover_field, i)),
                "first_time": "",  # 妙想不提供涨停时间
                "last_time": "",
                "zt_price": _parse_float(_get_value(table, price_field, i)),
                "is_20cm": False,
                "reason": _get_value(table, reason_field, i) or "",
                "zbc": 0,
            }

            # 判断 20CM
            code = stock.get("code", "")
            if code.startswith("30") or code.startswith("688"):
                stock["is_20cm"] = True

            # 判断涨停（涨幅 >= 9.9% 或 19.9%）
            change = _parse_float(_get_value(table, change_field, i))
            if change and change < 9.9:
                continue  # 不是涨停，跳过

            if stock["code"] and stock["name"]:
                stocks.append(stock)

    # 去重
    seen = set()
    deduped = []
    for s in stocks:
        if s["code"] not in seen:
            seen.add(s["code"])
            deduped.append(s)

    return deduped


def _find_field(name_map: Dict[str, Any], keywords: List[str]) -> Optional[str]:
    """在 nameMap 中查找匹配的关键字段，返回对应的 key"""
    for key, value in name_map.items():
        if not isinstance(value, str):
            continue
        for kw in keywords:
            if kw in value:
                return key
    return None


def _get_value(table: Dict[str, Any], field_key: Optional[str], index: int) -> Optional[str]:
    """从表格中获取指定字段指定行的值"""
    if not field_key or field_key == "headName":
        return None
    values = table.get(field_key, [])
    if isinstance(values, list) and index < len(values):
        return str(values[index]) if values[index] is not None else ""
    return None


def _parse_float(val: Optional[str]) -> float:
    """安全解析浮点数"""
    if not val:
        return 0
    try:
        return float(str(val).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return 0


def _parse_amount(val: Optional[str]) -> float:
    """解析成交额，支持 亿元/万元 等单位"""
    if not val:
        return 0
    val = str(val).strip()
    try:
        if "亿" in val:
            return float(val.replace("亿", "").replace(",", "")) * 100000000
        if "万" in val:
            return float(val.replace("万", "").replace(",", "")) * 10000
        return float(val.replace(",", ""))
    except (ValueError, TypeError):
        return 0


def get_limit_up_stocks_mx(trade_date: str = None) -> List[Dict[str, Any]]:
    """
    通过妙想 API 获取涨停股票数据。

    :param trade_date: 交易日期 (YYYYMMDD)，如 "20260410"
    :return: 标准化的涨停股票列表（与 push2ex 接口返回格式一致）
    """
    api_key = os.getenv("MX_APIKEY")
    if not api_key:
        print("❌ MX_APIKEY 环境变量未设置，无法使用妙想数据源")
        print("   请设置: export MX_APIKEY=your_api_key_here")
        print("   获取地址: https://dl.dfcfs.com/m/itc4")
        return []

    # 构建查询语句
    date_str = ""
    if trade_date and len(trade_date) == 8:
        date_str = f"{trade_date[:4]}年{int(trade_date[4:6])}月{int(trade_date[6:8])}日"

    if date_str:
        query = f"{date_str}A股涨停股票 涨停价 涨跌幅 成交额 换手率 所属行业"
    else:
        query = "今日A股涨停股票 涨停价 涨跌幅 成交额 换手率 所属行业"

    print(f"📥 [妙想] 正在获取涨停数据: {query}")

    try:
        result = _mx_query(query, api_key)
        stocks = _extract_stocks_from_mx(result)

        if stocks:
            print(f"✅ [妙想] 获取到 {len(stocks)} 只涨停股票")
        else:
            print("⚠️ [妙想] 未能提取涨停数据，尝试补充查询...")

            # 补充查询：尝试用不同的问句
            if date_str:
                query2 = f"{date_str}涨幅超过9.9%的股票 涨跌幅 成交额 所属行业"
            else:
                query2 = "今日涨幅超过9.9%的股票 涨跌幅 成交额 所属行业"

            print(f"📥 [妙想] 补充查询: {query2}")
            result2 = _mx_query(query2, api_key)
            stocks = _extract_stocks_from_mx(result2)

            if stocks:
                print(f"✅ [妙想] 补充查询获取到 {len(stocks)} 只涨停股票")
            else:
                print("❌ [妙想] 所有查询均未返回涨停数据")

        return stocks

    except requests.exceptions.RequestException as e:
        print(f"❌ [妙想] 网络请求失败: {e}")
        return []
    except Exception as e:
        print(f"❌ [妙想] 获取涨停数据异常: {e}")
        return []
