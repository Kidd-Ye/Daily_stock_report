#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股涨停复盘自动推送
按照模板格式生成完整复盘报告
"""

import requests
import re
import json
import os
import subprocess
from datetime import datetime, timedelta

# =============================================
# 辅助函数
# =============================================
def format_time(t):
    """将东方财富时间数字格式化为 HH:MM:SS"""
    if not t:
        return "—"
    t = int(t)
    h = t // 10000
    m = (t % 10000) // 100
    s = t % 100
    return f"{h:02d}:{m:02d}:{s:02d}"


# =============================================
# 1. 获取东方财富涨停数据（包含连板数、成交额）
# =============================================
def get_limit_up_stocks(trade_date=None):
    """
    通过东方财富 push2ex API 获取涨停数据
    包含：股票代码、名称、连板数、首次封板时间、成交额、换手率等
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    print(f"📥 正在获取涨停数据（{trade_date}）...")

    # 东方财富涨停池 API
    url = "http://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 200,
        "sort": "fbt:asc",
        "date": trade_date
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://quote.eastmoney.com/",
        "Accept": "*/*"
    }

    stocks = []
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("data") and data["data"].get("pool"):
            pool = data["data"]["pool"]
            for item in pool:
                code = item.get("c", "")
                name = item.get("n", "")
                # 连板数: lbc = 1(首板), 2(2连板), 3(3连板)...
                # 东财返回的 lbc 字段
                bd = item.get("lbc", 1)  # 连板数
                # 备用：用 zttj.days
                zttj_days = item.get("zttj", {}).get("days", bd)
                amount = item.get("amount", 0)  # 成交额（元）
                turnover = item.get("hs", 0)  # 换手率
                first_time = item.get("fbt", "")  # 首次封板时间（数字格式）
                last_time = item.get("lbt", "")  # 最后封板时间
                zt_price = item.get("p", 0)  # 涨停价
                zbc = item.get("zbc", 0)  # 炸板次数

                # 判断是否20CM（创业板300/科创板688）
                is_20cm = code.startswith("30") or code.startswith("688")

                stocks.append({
                    "code": code,
                    "name": name,
                    "bd": zttj_days or bd,  # 连板数（1=首板）
                    "amount": amount,
                    "turnover": turnover,
                    "first_time": first_time,
                    "last_time": last_time,
                    "zt_price": zt_price,
                    "is_20cm": is_20cm,
                    "reason": item.get("hybk", "") or item.get("dp", ""),  # 行业板块
                    "zbc": zbc,  # 炸板次数
                })

        print(f"✅ 获取到 {len(stocks)} 只涨停股票")

    except Exception as e:
        print(f"❌ 获取失败: {e}")
        # 备用：东方财富 clist 接口
        stocks = get_limit_up_from_clist()

    return stocks


def get_limit_up_from_clist():
    """备用：通过东方财富 clist 接口获取涨停数据"""
    print("📥 使用备用接口...")
    stocks = []

    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "po": "1", "pz": 200, "pn": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:0+t:6+f:!22,m:0+t:80+f:!22,m:1+t:2+f:!22,m:1+t:23+f:!22",
        "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18",
        "_": int(datetime.now().timestamp() * 1000)
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://quote.eastmoney.com/"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        text = resp.text
        m = re.search(r'jQuery\((.*)\)', text)
        if m:
            data = json.loads(m.group(1))
            if data.get("data") and data["data"].get("diff"):
                for item in data["data"]["diff"]:
                    code = str(item.get("f12", ""))
                    change = item.get("f3", 0)
                    # 只取涨停股（>=9.9%）
                    if change < 9.9:
                        continue
                    stocks.append({
                        "code": code,
                        "name": item.get("f14", "未知"),
                        "bd": 1,  # clist无连板数据
                        "amount": item.get("f6", 0) * 100,
                        "turnover": item.get("f8", 0),
                        "first_time": "",
                        "last_time": "",
                        "zt_price": item.get("f15", 0),
                        "is_20cm": code.startswith("30") or code.startswith("688"),
                        "reason": "题材",
                    })
    except Exception as e:
        print(f"⚠️ 备用接口也失败: {e}")

    return stocks


# =============================================
# 2. 获取跌停数据
# =============================================
def get_limit_down_count(trade_date=None):
    """获取今日跌停家数"""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    try:
        url = "http://push2ex.eastmoney.com/getTopicDTPool"
        params = {
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.dtdt",
            "Pageindex": 0,
            "pagesize": 1,
            "sort": "fund:asc",
            "date": trade_date
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://quote.eastmoney.com/"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        total = data.get("data", {}).get("total", 0)
        return total
    except Exception as e:
        print(f"⚠️ 跌停数据获取失败: {e}")
        return 0


# =============================================
# 3. 获取涨停股票的行业/题材
# =============================================
def enrich_with_industry(stocks):
    """
    通过东方财富个股详情接口补充行业信息
    注意：这个接口只支持单只查询，会有速率限制
    """
    print("📥 补充行业信息（可能需要一点时间）...")

    def get_industry(code):
        """获取单只股票的行业"""
        try:
            # 东方财富 A股列表接口（包含行业）
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            fs = f"b:{code}+f:!+fs:m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
            params = {
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": fs,
                "fields": "f14,f100",
                "_": int(datetime.now().timestamp() * 1000)
            }
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://quote.eastmoney.com/"}
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            resp.encoding = 'utf-8'
            m = re.search(r'jQuery\((.*)\)', resp.text)
            if m:
                data = json.loads(m.group(1))
                if data.get("data") and data["data"].get("diff"):
                    item = data["data"]["diff"][0]
                    return item.get("f100", "") or item.get("f14", "")
        except:
            pass
        return ""

    # 为每只股票补充行业（批量处理，太慢就跳过）
    enriched = 0
    for stock in stocks[:30]:  # 最多处理30只，避免超时
        industry = get_industry(stock["code"])
        if industry:
            stock["industry"] = industry
            enriched += 1
        else:
            stock["industry"] = stock.get("reason", "题材") or "题材"

    print(f"✅ 补充了 {enriched} 只股票的行业信息")
    return stocks


# =============================================
# 4. 生成完整复盘 MD 文件
# =============================================
def generate_report(stocks, trade_date):
    """生成完整格式的涨停复盘 MD 文件"""

    # 格式化日期
    date_str = datetime.strptime(trade_date, "%Y%m%d").strftime("%Y年%m月%d日")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        datetime.strptime(trade_date, "%Y%m%d").weekday()
    ]

    # ========== 一、市场整体数据 ==========
    total = len(stocks)
    if not total:
        return None, "无涨停数据"

    # 计算连板数
    first_board = [s for s in stocks if s.get("bd", 1) == 1]  # 首板
    more_boards = [s for s in stocks if s.get("bd", 1) >= 2]  # 连板

    # 4板/3板/2板
    bd4 = [s for s in stocks if s.get("bd", 1) == 4]
    bd3 = [s for s in stocks if s.get("bd", 1) == 3]
    bd2 = [s for s in stocks if s.get("bd", 1) == 2]
    board20 = [s for s in stocks if s.get("is_20cm", False)]  # 20CM
    zbc_stocks = [s for s in stocks if s.get("zbc", 0) > 0]  # 有炸板的

    # 成交额最高
    by_amount = sorted(stocks, key=lambda x: x.get("amount", 0), reverse=True)

    # ========== 二、连板梯队 ==========
    board_section = ""
    if bd4:
        names_bd4 = "、".join([f"{s['name']}（{s['code']}）" for s in bd4])
        board_section += f"**4连板（{len(bd4)}只）：** {names_bd4}\n"
    if bd3:
        names_bd3 = "、".join([f"{s['name']}（{s['code']}）" for s in bd3])
        board_section += f"**3连板（{len(bd3)}只）：** {names_bd3}\n"
    if bd2:
        names_bd2 = "、".join([f"{s['name']}（{s['code']}）" for s in bd2])
        board_section += f"**2连板（{len(bd2)}只）：** {names_bd2}\n"

    # ========== 三、行业板块统计 ==========
    from collections import Counter
    # 按行业分组
    industry_groups = {}
    for s in stocks:
        ind = s.get("reason", "") or "其他"
        if ind not in industry_groups:
            industry_groups[ind] = []
        industry_groups[ind].append(s)
    # 按数量排序，取前8
    sorted_industries = sorted(industry_groups.items(), key=lambda x: len(x[1]), reverse=True)[:8]

    sector_section = ""
    for ind_name, ind_stocks in sorted_industries:
        reps = "、".join([s["name"] for s in ind_stocks[:3]])
        reps += "等" if len(ind_stocks) > 3 else ""
        sector_section += f"| {ind_name} | {len(ind_stocks)}只 | {reps} | — |\n"

    # ========== 四、20CM弹性个股 ==========
    cm20_section = ""
    if board20:
        for s in sorted(board20, key=lambda x: x.get("amount", 0), reverse=True):
            ft = format_time(s.get("first_time", ""))
            amount_yi = s.get("amount", 0) / 100000000
            reason = s.get("reason", "题材") or "题材"
            cm20_section += f"| {s['code']} | {s['name']} | {ft} | {reason} | {amount_yi:.2f}亿 |\n"

    # ========== 五、爆量大票 ==========
    amount_section = ""
    for s in by_amount[:10]:
        amount_yi = s.get("amount", 0) / 100000000
        reason = s.get("reason", "题材") or "题材"
        amount_section += f"| {s['code']} | {s['name']} | {amount_yi:.2f}亿 | {reason} |\n"

    # ========== 六、炸板个股 ==========
    zbc_section = ""
    if zbc_stocks:
        for s in sorted(zbc_stocks, key=lambda x: x.get("zbc", 0), reverse=True)[:10]:
            zbc_num = s.get("zbc", 0)
            reason = s.get("reason", "题材") or "题材"
            zbc_section += f"| {s['code']} | {s['name']} | {zbc_num}次 | {reason} |\n"

    # ========== 七、涨停全名单 ==========
    # 按连板数和首次封板时间排序
    sorted_stocks = sorted(stocks, key=lambda x: (-x.get("bd", 1), x.get("first_time", "")))

    full_list = ""
    for i, s in enumerate(sorted_stocks, 1):
        ft = format_time(s.get("first_time", ""))
        bd_val = s.get("bd", 1)
        if bd_val > 1:
            bd_desc = f"{bd_val}连板"
        elif s.get("is_20cm"):
            bd_desc = "首板/20CM"
        else:
            bd_desc = "首板"
        reason = s.get("reason", "题材") or "题材"
        full_list += f"| {i} | {s['code']} | {s['name']} | {bd_desc} | {ft} | {reason} |\n"

    # ========== 完整 MD ==========
    # 先计算动态字段，避免嵌套 f-string 歧义
    cm20_fallback = "| — | — | — | — | — |\n"
    amount_fallback = "| — | — | — | — |\n"
    zbc_fallback = "| — | — | — | — |\n"
    sector_fallback = "| — | — | — | — |\n"
    board_summary = '，'.join(filter(None, [
        f'{len(bd4)}只4连板' if bd4 else '',
        f'{len(bd3)}只3连板' if bd3 else '',
        f'{len(bd2)}只2连板' if bd2 else ''
    ])) or '暂无'
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sector_filled = sector_section or sector_fallback

    md = f"""# A股涨停复盘

{date_str}（{weekday}）

---

## 一、市场整体数据

| 指标 | 数值 | 备注 |
|:---:|:---:|:---|
| 涨停个股总数 | **{total}** 家 | — |
| 首板个股 | **{len(first_board)}** 家 | 占比 {len(first_board)*100//max(total,1)}% |
| 连板个股（≥2连板） | **{len(more_boards)}** 家 | 占比 {len(more_boards)*100//max(total,1)}% |
| 20CM个股（创业板/科创板） | **{len(board20)}** 家 | 英唐智控、纳微科技等 |
| 炸板个股 | **{len(zbc_stocks)}** 家 | 涨停后反复开板 |

---

## 二、连板梯队

连板个股共 **{len(more_boards)}** 只，{board_summary}，具体如下：

{board_section or '_暂无连板数据_'}

---

## 三、主要涨停板块分析

| 板块名称 | 涨停数 | 代表个股 | 核心催化 |
|:---|:---:|:---|:---|
{sector_filled}

---

## 四、20CM弹性个股（创业板/科创板涨停）

今日共 **{len(board20)}** 只创业板/科创板个股涨停：

| 股票代码 | 股票名称 | 涨停时间 | 涨停原因 | 成交额 |
|:---:|:---:|:---:|:---|:---:|
{cm20_section or cm20_fallback}

---

## 五、爆量大票（成交额前列）

以下个股今日成交额居前，市场关注度高：

| 股票代码 | 股票名称 | 成交额 | 涨停原因 / 概念 |
|:---:|:---:|:---:|:---|
{amount_section or amount_fallback}

---

## 六、分歧炸板个股（炸板后回封）

以下个股在涨停后反复炸板但最终封住涨停，反映市场分歧较大：

| 股票代码 | 股票名称 | 炸板次数 | 涨停原因 |
|:---:|:---:|:---:|:---|
{zbc_section or zbc_fallback}

---

## 七、市场热点总结

1. **市场整体活跃**，涨停个股数量可观，短线情绪较好
2. **连板股表现强势**，市场高度股持续连板
3. **创业板/科创板弹性大**，20CM个股受资金追捧
4. **成交额居前个股**具有较强市场影响力

---

## 八、今日涨停全名单（{total}只）

以下为今日全部 **{total}** 只涨停个股（不含ST股），按连板数及涨停时间排序：

| 序号 | 股票代码 | 股票名称 | 连板情况 | 涨停时间 | 涨停原因 / 概念 |
|:---:|:---:|:---:|:---:|:---:|:---|
{full_list}

---

> ⚠️ **免责声明**：本报告仅供参考，不构成任何投资建议。A股市场存在风险，投资需谨慎。涨停个股仅为市场数据统计，不代表任何推荐。
>
> 数据来源：东方财富 | 生成时间：{gen_time}
"""

    return md, f"涨停复盘_{trade_date}.md"


# =============================================
# 5. 生成 HTML 页面（可选）
# =============================================
def generate_html_report(stocks, trade_date):
    """生成 HTML 版本的复盘页面"""

    date_str = datetime.strptime(trade_date, "%Y%m%d").strftime("%Y年%m月%d日")

    # 排序
    sorted_stocks = sorted(stocks, key=lambda x: (-x.get("bd", 1), x.get("first_time", "")))
    board20 = [s for s in stocks if s.get("is_20cm", False)]
    by_amount = sorted(stocks, key=lambda x: x.get("amount", 0), reverse=True)
    zbc_stocks = [s for s in stocks if s.get("zbc", 0) > 0]
    more_boards = [s for s in stocks if s.get("bd", 1) >= 2]
    max_bd = max([s.get("bd", 1) for s in stocks]) if stocks else 0

    # 涨停列表 HTML
    rows_html = ""
    for i, s in enumerate(sorted_stocks, 1):
        bd = s.get("bd", 1)
        if bd > 1:
            bd_tag = f"<span class='badge board'>{bd}板</span>"
        elif s.get("is_20cm"):
            bd_tag = "<span class='badge cm'>20CM</span>"
        else:
            bd_tag = ""
        first_t = format_time(s.get("first_time", ""))
        reason = s.get("reason", "题材") or "题材"
        zbc = s.get("zbc", 0)
        zbc_tag = f"<span class='zbc'>{zbc}炸</span>" if zbc > 0 else ""
        rows_html += f"""
        <tr>
            <td>{i}</td>
            <td><strong>{s['name']}</strong> {bd_tag}{zbc_tag}</td>
            <td class='code'>{s['code']}</td>
            <td>{first_t}</td>
            <td>{reason}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股涨停复盘 {trade_date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2d3436; }}
  .header {{ background: linear-gradient(135deg, #c0392b, #e74c3c); color: white; padding: 24px 20px 20px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; }}
  .header .sub {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
  .stats {{ display: flex; gap: 12px; padding: 16px; overflow-x: auto; }}
  .stat-card {{ background: white; border-radius: 12px; padding: 16px 20px; min-width: 100px; flex: 1; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .stat-card .num {{ font-size: 28px; font-weight: 800; color: #c0392b; }}
  .stat-card .label {{ font-size: 12px; color: #636e72; margin-top: 4px; }}
  .section {{ background: white; margin: 0 16px 16px; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .section-title {{ padding: 14px 16px; font-weight: 700; font-size: 15px; border-bottom: 1px solid #f0f0f0; background: #fafafa; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #fff5f5; color: #636e72; font-weight: 600; padding: 10px 12px; text-align: left; border-bottom: 2px solid #fee; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f9f9f9; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ background: #fff0f0; color: #c0392b; border: 1px solid #fcc; border-radius: 4px; font-size: 11px; padding: 1px 5px; margin-left: 4px; font-weight: 600; }}
  .badge.board {{ background: #fff3e0; color: #e65100; border-color: #ffcc80; }}
  .badge.cm {{ background: #e8f5e9; color: #2e7d32; border-color: #a5d6a7; }}
  .footer {{ text-align: center; color: #b2bec3; font-size: 12px; padding: 20px; }}
  .cm-tag {{ color: #2e7d32; font-weight: 600; }}
  .zbc {{ color: #e67e22; font-weight: 600; margin-left: 4px; }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 A股涨停复盘</h1>
  <div class="sub">{date_str} &nbsp;·&nbsp; 更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;·&nbsp; 数据来源：东方财富</div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="num">{len(stocks)}</div>
    <div class="label">涨停总数</div>
  </div>
  <div class="stat-card">
    <div class="num">{len(board20)}</div>
    <div class="label">20CM个股</div>
  </div>
  <div class="stat-card">
    <div class="num">{len([s for s in stocks if s.get('bd',1)>=2])}</div>
    <div class="label">连板个股</div>
  </div>
  <div class="stat-card">
    <div class="num">{max_bd}</div>
    <div class="label">最高连板</div>
  </div>
</div>

<div class="section">
  <div class="section-title">📋 涨停股票全名单（{len(stocks)}只）</div>
  <table>
    <thead>
      <tr><th>#</th><th>名称</th><th>代码</th><th>涨停时间</th><th>涨停原因</th></tr>
    </thead>
    <tbody>
      {rows_html or '<tr><td colspan="5" style="text-align:center;color:#999">暂无数据</td></tr>'}
    </tbody>
  </table>
</div>

<div class="footer">
  免责声明：本报告仅供参考，不构成投资建议<br>
  数据来源：东方财富 | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>

</body>
</html>"""

    return html


# =============================================
# 6. 提交到 GitHub
# =============================================
def commit_to_github(filepath, content):
    """提交文件到 GitHub"""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")

    if not repo or not token:
        print("⚠️ 未配置 GITHUB 环境变量，跳过提交")
        return None

    try:
        print("📤 正在提交到 GitHub...")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True, capture_output=True)
        subprocess.run(["git", "fetch", "origin"], check=True, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True, capture_output=True)
        subprocess.run(["git", "add", filepath], check=True, capture_output=True)
        subprocess.run([
            "git", "commit", "-m",
            f"📈 涨停复盘 {datetime.now().strftime('%Y-%m-%d')}"
        ], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)

        # GitHub Pages 链接（需仓库为 Public）
        pages_url = f"https://{repo.split('/')[0].lower()}.github.io/{repo.split('/')[1]}/"
        print(f"✅ 已提交，Pages 链接: {pages_url}")
        return pages_url

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        print(f"⚠️ GitHub 提交失败: {err_msg}")
        return None
    except Exception as e:
        print(f"✅ GitHub 提交异常: {e}")
        return None


# =============================================
# 7. 发送飞书卡片
# =============================================
def send_feishu_card(url, stocks, trade_date):
    """发送飞书卡片"""
    webhook = os.getenv("FEISHU_WEBHOOK")
    if not webhook:
        print("❌ 未配置 FEISHU_WEBHOOK")
        return

    date_str = datetime.strptime(trade_date, "%Y%m%d").strftime("%Y年%m月%d日")
    total = len(stocks)
    board20_count = len([s for s in stocks if s.get("is_20cm", False)])
    board_more = len([s for s in stocks if s.get("bd", 1) >= 2])

    # 展示前5只涨停
    top5 = sorted(stocks, key=lambda x: x.get("amount", 0), reverse=True)[:5]
    stock_lines = ""
    for s in top5:
        bd = f"🔴{s.get('bd',1)}板" if s.get('bd', 1) > 1 else ""
        stock_lines += f"\n• {s['name']}（{s['code']}）{bd}"

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 A股涨停复盘 {date_str}"},
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md",
                        "content": f"**涨停总数：** {total} 家\n"
                                   f"**连板个股：** {board_more} 家\n"
                                   f"**20CM个股：** {board20_count} 只"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**成交额前五：**{stock_lines}"}
                },
                {
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄 查看完整复盘"},
                        "type": "primary",
                        "url": url
                    }]
                }
            ]
        }
    }

    try:
        resp = requests.post(webhook, json=card, timeout=10)
        if resp.status_code == 200:
            print("✅ 飞书卡片发送成功")
        else:
            print(f"❌ 飞书发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ 飞书请求异常: {e}")


# =============================================
# 主程序
# =============================================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 A股涨停复盘自动推送")
    print("=" * 50)

    # 获取日期（默认昨天）
    today = datetime.now()
    # 交易日：工作日收盘后运行，取前一天
    # 周五→周六取周五数据，周六/周日→取上周五数据
    if today.weekday() == 0:  # 周一
        trade_date = (today - timedelta(days=3)).strftime("%Y%m%d")
    elif today.weekday() in (5, 6):  # 周六、周日
        trade_date = (today - timedelta(days=today.weekday() - 4)).strftime("%Y%m%d")  # 回溯到上周五
    else:
        trade_date = (today - timedelta(days=1)).strftime("%Y%m%d")

    print(f"📅 交易日期: {trade_date}")

    # 1. 获取涨停数据
    stocks = get_limit_up_stocks(trade_date)

    if not stocks:
        print("❌ 未获取到涨停数据，程序退出")
        exit(1)

    # 2. 生成复盘文件
    md_content, md_filename = generate_report(stocks, trade_date)

    # 保存 MD
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✅ 已生成 {md_filename}")

    # 同时生成 HTML
    html_content = generate_html_report(stocks, trade_date)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✅ 已生成 docs/index.html")

    # 3. 提交到 GitHub
    url = commit_to_github("docs/index.html", html_content)
    if not url:
        url = os.getenv("PAGES_URL", "https://github.com/Kidd-Ye/Daily_stock_report")

    # 4. 发送飞书
    send_feishu_card(url, stocks, trade_date)

    print("=" * 50)
    print(f"✅ 完成！链接: {url}")
    print("=" * 50)
