#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股涨停复盘自动推送
生成 PDF 文档，匹配模板格式
"""

import requests
import re
import json
import os
import subprocess
from datetime import datetime, timedelta


# =============================================
# 1. 获取东方财富涨停数据
# =============================================
def get_limit_up_stocks(trade_date=None):
    """通过东方财富 push2ex API 获取涨停数据"""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    print(f"📥 正在获取涨停数据（{trade_date}）...")

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
            for item in data["data"]["pool"]:
                code = item.get("c", "")
                name = item.get("n", "")
                bd = item.get("lbc", 1)
                zttj_days = item.get("zttj", {}).get("days", bd)
                stocks.append({
                    "code": code,
                    "name": name,
                    "bd": zttj_days or bd,
                    "amount": item.get("amount", 0),
                    "turnover": item.get("hs", 0),
                    "first_time": item.get("fbt", ""),
                    "last_time": item.get("lbt", ""),
                    "zt_price": item.get("p", 0),
                    "is_20cm": code.startswith("30") or code.startswith("688"),
                    "reason": item.get("hybk", "") or item.get("dp", ""),
                    "zbc": item.get("zbc", 0),
                })

        print(f"✅ 获取到 {len(stocks)} 只涨停股票")

    except Exception as e:
        print(f"❌ push2ex 获取失败: {e}")
        stocks = _get_limit_up_from_clist()

    return stocks


def _get_limit_up_from_clist():
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
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://quote.eastmoney.com/"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        m = re.search(r'jQuery\((.*)\)', resp.text)
        if m:
            data = json.loads(m.group(1))
            if data.get("data") and data["data"].get("diff"):
                for item in data["data"]["diff"]:
                    code = str(item.get("f12", ""))
                    change = item.get("f3", 0)
                    if change < 9.9:
                        continue
                    stocks.append({
                        "code": code, "name": item.get("f14", "未知"),
                        "bd": 1, "amount": item.get("f6", 0) * 100,
                        "turnover": item.get("f8", 0), "first_time": "",
                        "last_time": "", "zt_price": item.get("f15", 0),
                        "is_20cm": code.startswith("30") or code.startswith("688"),
                        "reason": "题材", "zbc": 0,
                    })
    except Exception as e:
        print(f"⚠️ 备用接口也失败: {e}")

    return stocks


# =============================================
# 2. 生成 PDF 文档（调用 Node.js + @sparticuz/chromium）
# =============================================
def generate_pdf(stocks, trade_date, market_comment=None):
    """调用 generate_pdf.js 生成 .pdf 文件"""
    print("📝 正在生成 PDF 文档...")

    # 把股票数据写入临时 JSON 文件
    tmp_json = "/tmp/stocks_for_pdf.json"
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)

    # 调用 Node.js 生成 PDF
    cmd = [
        "node", os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_pdf.js"),
        tmp_json, trade_date,
        f"涨停复盘_{trade_date}.pdf",
        market_comment or ""
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip().startswith("OK:"):
            output_file = result.stdout.strip().split(":", 1)[1].strip()
            print(f"✅ PDF 生成成功: {output_file}")
            return output_file
        else:
            print(f"❌ PDF 生成失败: {result.stderr or result.stdout}")
            return None
    except Exception as e:
        print(f"❌ PDF 生成异常: {e}")
        return None


# =============================================
# 3. 提交到 GitHub
# =============================================
def commit_to_github(filepath):
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
        subprocess.run(["git", "stash"], check=True, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True, capture_output=True)
        # stash pop 只有在 stash 成功时才执行
        result = subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
        # 忽略 "No stash entries found" 这类非致命错误
        subprocess.run(["git", "add", filepath], check=True, capture_output=True)
        subprocess.run([
            "git", "commit", "-m",
            f"📈 涨停复盘 {datetime.now().strftime('%Y-%m-%d')}"
        ], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)

        # 返回 docx 的 raw GitHub 链接
        report_url = f"https://github.com/Kidd-Ye/Daily_stock_report/raw/main/{filepath}"
        print(f"✅ 已提交，报告链接: {report_url}")
        return report_url

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        print(f"⚠️ GitHub 提交失败: {err_msg}")
        return None
    except Exception as e:
        print(f"⚠️ GitHub 提交异常: {e}")
        return None


# =============================================
# 4. 发送飞书卡片
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

    # 成交额前5
    top5 = sorted(stocks, key=lambda x: x.get("amount", 0), reverse=True)[:5]
    stock_lines = ""
    for s in top5:
        bd = f"{s.get('bd', 1)}板" if s.get('bd', 1) > 1 else ""
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
                        "text": {"tag": "plain_text", "content": "📄 下载复盘 PDF 文档"},
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

    # 计算交易日期（取前一交易日）
    today = datetime.now()
    if today.weekday() == 0:  # 周一
        trade_date = (today - timedelta(days=3)).strftime("%Y%m%d")
    elif today.weekday() in (5, 6):  # 周六、周日
        trade_date = (today - timedelta(days=today.weekday() - 4)).strftime("%Y%m%d")
    else:
        trade_date = (today - timedelta(days=1)).strftime("%Y%m%d")

    print(f"📅 交易日期: {trade_date}")

    # 1. 获取涨停数据
    stocks = get_limit_up_stocks(trade_date)

    if not stocks:
        print("❌ 未获取到涨停数据，程序退出")
        exit(1)

    # 2. 生成 PDF 文档
    pdf_file = generate_pdf(stocks, trade_date)

    if not pdf_file:
        print("❌ PDF 文档生成失败，程序退出")
        exit(1)

    # 3. 提交到 GitHub
    url = commit_to_github(pdf_file)
    if not url:
        url = f"https://github.com/Kidd-Ye/Daily_stock_report/raw/main/{pdf_file}"

    # 4. 发送飞书卡片
    send_feishu_card(url, stocks, trade_date)

    print("=" * 50)
    print(f"✅ 完成！链接: {url}")
    print("=" * 50)
