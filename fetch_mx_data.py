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
    每个元素是一个"指标单元"（1个证券 + 1个指标的数据），
    但对于列表类查询，一个 dto 可能包含多只股票的数据（多行）。
    """
    status = result.get("status")
    if status != 0:
        print(f"❌ 妙想 API 错误: {result.get('message', '未知错误')}")
        return []

    data = result.get("data", {})
    inner_data = data.get("data", {})
    search_result = inner_data.get("searchDataResultDTO", {})

    # 优先从 inner_data 直接取，其次从 searchDataResultDTO 取
    dto_list = inner_data.get("dataTableDTOList", []) or search_result.get("dataTableDTOList", [])

    if not dto_list:
        print("⚠️ 妙想 API 返回数据为空（dataTableDTOList 为空）")
        return []

    print(f"🔍 [DEBUG] 获取到 {len(dto_list)} 个数据表")

    stocks = []
    for idx, dto in enumerate(dto_list):
        table = dto.get("table") or {}
        name_map = dto.get("nameMap") or {}
        title = dto.get("title", f"表{idx}")
        entity_name = dto.get("entityName", "")

        if isinstance(name_map, list):
            name_map = {str(i): v for i, v in enumerate(name_map)}

        print(f"🔍 [DEBUG] 处理 dto[{idx}]: title={title}, entity={entity_name}")
        print(f"🔍 [DEBUG]   nameMap: {name_map}")
        print(f"🔍 [DEBUG]   table keys: {list(table.keys())}")

        # 检测数据行数
        indicator_keys = [k for k in table.keys() if k != "headName"]
        if not indicator_keys:
            continue

        first_indicator = table.get(indicator_keys[0], [])
        row_count = len(first_indicator)
        print(f"🔍 [DEBUG]   行数: {row_count}, 指标列: {indicator_keys[:5]}")

        if row_count == 0:
            continue

        # 构建字段映射
        code_field = _find_field(name_map, ["股票代码", "代码", "secuCode", "证券代码"])
        name_field = _find_field(name_map, ["股票名称", "名称", "证券简称", "secuName", "名称"])
        change_field = _find_field(name_map, ["涨跌幅", "涨跌", "涨幅"])
        amount_field = _find_field(name_map, ["成交额", "成交金额", "总金额"])
        turnover_field = _find_field(name_map, ["换手率", "换手"])
        price_field = _find_field(name_map, ["最新价", "收盘价", "涨停价"])
        reason_field = _find_field(name_map, ["所属行业", "行业", "概念", "板块", "涨停原因"])

        print(f"🔍 [DEBUG]   字段映射: code={code_field}, name={name_field}, change={change_field}, "
              f"amount={amount_field}, turnover={turnover_field}, price={price_field}, reason={reason_field}")

        for i in range(row_count):
            stock = {
                "code": _get_value(table, code_field, i) or "",
                "name": _get_value(table, name_field, i) or "",
                "bd": 1,
                "amount": _parse_amount(_get_value(table, amount_field, i)),
                "turnover": _parse_float(_get_value(table, turnover_field, i)),
                "first_time": "",
                "last_time": "",
                "zt_price": _parse_float(_get_value(table, price_field, i)),
                "is_20cm": False,
                "reason": _get_value(table, reason_field, i) or "",
                "zbc": 0,
            }

            code = stock.get("code", "")
            if code.startswith("30") or code.startswith("688"):
                stock["is_20cm"] = True

            # 判断涨停（涨幅 >= 9.9%）
            change = _parse_float(_get_value(table, change_field, i))
            if change and change < 9.9:
                continue

            if stock["code"] and stock["name"]:
                stocks.append(stock)
                print(f"🔍 [DEBUG]   ✓ 涨停股: {stock['name']}({stock['code']}) 涨幅={change}")

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

    策略：妙想 API 是自然语言查询引擎，不支持"涨停股票池"这种筛选查询。
    采用多轮查询 + 本地筛选的方式：
    1. 查询 A 股涨幅排行数据
    2. 在本地筛选涨幅 >= 9.9% 的股票

    :param trade_date: 交易日期 (YYYYMMDD)，如 "20260410"
    :return: 标准化的涨停股票列表（与 push2ex 接口返回格式一致）
    """
    api_key = os.getenv("MX_APIKEY")
    if not api_key:
        print("❌ MX_APIKEY 环境变量未设置，无法使用妙想数据源")
        print("   请设置: export MX_APIKEY=your_api_key_here")
        print("   获取地址: https://dl.dfcfs.com/m/itc4")
        return []

    date_str = ""
    if trade_date and len(trade_date) == 8:
        date_str = f"{trade_date[:4]}年{int(trade_date[4:6])}月{int(trade_date[6:8])}日"

    # 多种查询语句尝试，妙想 API 对自然语言的理解有限，需要找到它支持的问法
    queries = []
    if date_str:
        queries = [
            f"{date_str}沪深A股涨幅排名前100 涨跌幅 成交额 换手率 所属行业 最新价",
            f"{date_str}A股市场涨幅排行榜 股票名称 涨跌幅 成交额",
            f"{date_str}所有A股涨跌幅排行 涨跌幅 成交额 换手率",
        ]
    else:
        queries = [
            "今日沪深A股涨幅排名前100 涨跌幅 成交额 换手率 所属行业 最新价",
            "今日A股市场涨幅排行榜 股票名称 涨跌幅 成交额",
            "今日所有A股涨跌幅排行 涨跌幅 成交额 换手率",
        ]

    all_stocks = []

    for i, query in enumerate(queries):
        print(f"📥 [妙想] 查询 {i+1}/{len(queries)}: {query}")

        try:
            result = _mx_query(query, api_key)
            stocks = _extract_stocks_from_mx(result)

            if stocks:
                print(f"✅ [妙想] 查询 {i+1} 获取到 {len(stocks)} 只涨停股票")
                # 合并去重
                existing_codes = {s["code"] for s in all_stocks}
                for s in stocks:
                    if s["code"] not in existing_codes:
                        all_stocks.append(s)
                        existing_codes.add(s["code"])
                break  # 有数据就不再尝试下一个查询
            else:
                print(f"⚠️ [妙想] 查询 {i+1} 未返回涨停数据")

        except requests.exceptions.RequestException as e:
            print(f"❌ [妙想] 查询 {i+1} 网络请求失败: {e}")
        except Exception as e:
            print(f"❌ [妙想] 查询 {i+1} 异常: {e}")

    if all_stocks:
        print(f"✅ [妙想] 共获取到 {len(all_stocks)} 只涨停股票")
    else:
        print("❌ [妙想] 所有查询均未返回涨停数据，妙想 API 可能不支持涨停池查询")

    return all_stocks
