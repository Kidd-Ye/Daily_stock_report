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
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CALENDAR_FILE = os.path.join(ROOT_DIR, "trading_calendar.json")


def _date_str_to_date(s):
    return datetime.strptime(s, "%Y%m%d").date()


def _normalize_time(t):
    if not t:
        return ""
    t = re.sub(r"[^0-9]", "", str(t))
    if len(t) == 4:
        return t + "00"
    if len(t) == 5:
        return t
    return t.zfill(6)


def _pick_earlier_time(a, b):
    na = _normalize_time(a)
    nb = _normalize_time(b)
    if not na:
        return b or a
    if not nb:
        return a
    return a if na <= nb else b


def _pick_later_time(a, b):
    na = _normalize_time(a)
    nb = _normalize_time(b)
    if not na:
        return b or a
    if not nb:
        return a
    return a if na >= nb else b


def _merge_reason(r1, r2):
    r1 = r1 or ""
    r2 = r2 or ""
    if not r1:
        return r2
    if not r2:
        return r1
    if r1 == r2:
        return r1
    if r2 in r1:
        return r1
    if r1 in r2:
        return r2
    return f"{r1}/{r2}"


def _normalize_industry(reason):
    """规范化行业名称"""
    if not reason:
        return "题材"
    mappings = {
        "自动化设": "自动化设备",
        "房地产开": "房地产开发",
        "家电零部": "家电零部件",
        "汽车零部": "汽车零部件",
        "电子元器": "电子元器件",
        "光学光电": "光学光电",
        "输配电气": "输配电设备",
        "通用设备": "通用设备",
        "专用设备": "专用设备",
        "工程机械": "工程机械",
        "铁路公路": "铁路公路",
        "航运港口": "航运港口",
        "石油化工": "石油化工",
        "化学制药": "化学制药",
        "生物制药": "生物制药",
        "医疗器械": "医疗器械",
        "软件开发": "软件开发",
        "互联网": "互联网服务",
        "通信设备": "通信设备",
        "电子消费": "电子消费",
        "食品饮片": "食品饮料",
        "纺织服装": "纺织服装",
        "贵金属": "贵金属",
        "稀土永磁": "稀土永磁",
        "锂电池": "锂电池",
        "光伏设备": "光伏设备",
        "储能": "储能",
        "氢能源": "氢能源",
        "机器人": "机器人",
        "人工智能": "人工智能",
        "大模型": "大模型",
        "算力": "算力",
        "数据中心": "数据中心",
        "芯片": "芯片",
        "半导体": "半导体",
    }
    for short, full in mappings.items():
        if reason == short or reason.startswith(short):
            return full
    return reason


def dedupe_stocks(stocks):
    """按股票代码去重，保留更完整的数据"""
    by_code = {}
    for s in stocks:
        code = s.get("code")
        if not code:
            continue
        if code not in by_code:
            by_code[code] = dict(s)
        else:
            a = by_code[code]
            b = s
            merged = dict(a)
            merged["name"] = a.get("name") or b.get("name") or ""
            merged["bd"] = max(a.get("bd", 1), b.get("bd", 1))
            merged["amount"] = max(a.get("amount", 0), b.get("amount", 0))
            merged["turnover"] = max(a.get("turnover", 0), b.get("turnover", 0))
            merged["first_time"] = _pick_earlier_time(a.get("first_time", ""), b.get("first_time", ""))
            merged["last_time"] = _pick_later_time(a.get("last_time", ""), b.get("last_time", ""))
            merged["zt_price"] = max(a.get("zt_price", 0), b.get("zt_price", 0))
            merged["is_20cm"] = bool(a.get("is_20cm")) or bool(b.get("is_20cm"))
            merged["reason"] = _merge_reason(a.get("reason", ""), b.get("reason", ""))
            merged["zbc"] = max(a.get("zbc", 0), b.get("zbc", 0))
            by_code[code] = merged
    deduped = list(by_code.values())
    if len(deduped) != len(stocks):
        print(f"🔁 去重完成: {len(stocks)} -> {len(deduped)}")
    return deduped


def _load_trading_calendar():
    if not os.path.exists(CALENDAR_FILE):
        return None, None
    try:
        with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data, None
        if isinstance(data, dict):
            return data.get("dates", []), data.get("updated_at")
    except Exception as e:
        print(f"⚠️ 读取交易日历失败: {e}")
    return None, None


def _save_trading_calendar(dates):
    try:
        payload = {
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
            "dates": sorted(dates),
        }
        with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"✅ 交易日历已更新: {CALENDAR_FILE}")
    except Exception as e:
        print(f"⚠️ 写入交易日历失败: {e}")


def _calendar_is_stale(dates, updated_at, today):
    if not dates:
        return True
    if not updated_at:
        return True
    try:
        updated_date = datetime.strptime(updated_at, "%Y-%m-%d").date()
    except Exception:
        return True
    if (today - updated_date).days >= 7:
        return True
    try:
        latest_date = _date_str_to_date(max(dates))
    except Exception:
        return True
    if (today - latest_date).days > 10:
        return True
    return False


def _fetch_trading_calendar_from_eastmoney(today, days=400):
    """通过东方财富指数K线获取近一段时间交易日历"""
    beg = (today - timedelta(days=days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": "1.000001",  # 上证指数
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": beg,
        "end": end,
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])
        dates = [k.split(",")[0].replace("-", "") for k in klines if k]
        return dates
    except Exception as e:
        print(f"⚠️ 拉取交易日历失败: {e}")
        return []


def ensure_trading_calendar():
    today = datetime.now().date()
    dates, updated_at = _load_trading_calendar()
    if _calendar_is_stale(dates, updated_at, today):
        print("📅 交易日历缺失或过期，尝试在线更新...")
        dates = _fetch_trading_calendar_from_eastmoney(today)
        if dates:
            _save_trading_calendar(dates)
    return dates or []


def get_trade_date():
    """通过交易日历计算上一交易日，支持环境变量覆盖"""
    env_date = os.getenv("TRADE_DATE", "").strip()
    if env_date:
        print(f"📌 使用环境变量指定交易日: {env_date}")
        return env_date

    today = datetime.now().date()
    use_today = os.getenv("USE_TODAY_IF_TRADE_DAY", "").lower() in ("1", "true", "yes")
    dates = ensure_trading_calendar()
    if dates:
        dates_sorted = sorted(dates)
        today_str = today.strftime("%Y%m%d")
        if today_str not in dates_sorted:
            print("📅 今日不在交易日历中，强制刷新...")
            new_dates = _fetch_trading_calendar_from_eastmoney(today)
            if new_dates:
                _save_trading_calendar(new_dates)
                dates_sorted = sorted(new_dates)
        if use_today:
            candidates = [d for d in dates_sorted if d <= today_str]
        else:
            candidates = [d for d in dates_sorted if d <= today_str]
        if candidates:
            trade_date = candidates[-1]
            print(f"📅 交易日历计算交易日: {trade_date}")
            return trade_date

    # 兜底：沿用原有简单规则
    if today.weekday() == 0:  # 周一
        return (today - timedelta(days=3)).strftime("%Y%m%d")
    if today.weekday() in (5, 6):  # 周六、周日
        return (today - timedelta(days=today.weekday() - 4)).strftime("%Y%m%d")
    return (today - timedelta(days=1)).strftime("%Y%m%d")
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
    reports_dir = os.path.join(ROOT_DIR, "reports", trade_date[:4])
    os.makedirs(reports_dir, exist_ok=True)
    output_rel = os.path.join("reports", trade_date[:4], f"涨停复盘_{trade_date}.pdf")

    cmd = [
        "node", os.path.join(ROOT_DIR, "generate_pdf.js"),
        tmp_json, trade_date,
        output_rel,
        market_comment or ""
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT_DIR)
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

        subprocess.run(["git", "config", "user.name", "GitHub Actions"], check=True, capture_output=True, cwd=ROOT_DIR)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True, capture_output=True, cwd=ROOT_DIR)
        subprocess.run(["git", "stash"], check=True, capture_output=True, cwd=ROOT_DIR)
        subprocess.run(["git", "pull", "--rebase", remote_url, "main"], check=True, capture_output=True, cwd=ROOT_DIR)
        # stash pop 只有在 stash 成功时才执行
        result = subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=ROOT_DIR)
        # 忽略 "No stash entries found" 这类非致命错误
        subprocess.run(["git", "add", "-f", filepath], check=True, capture_output=True, cwd=ROOT_DIR)
        subprocess.run([
            "git", "commit", "-m",
            f"📈 涨停复盘 {datetime.now().strftime('%Y-%m-%d')}"
        ], check=True, capture_output=True, cwd=ROOT_DIR)
        subprocess.run(["git", "push", remote_url, "main"], check=True, capture_output=True, cwd=ROOT_DIR)

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
# 4. 发送飞书消息（应用身份）
# =============================================
def get_tenant_access_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0 and data.get("tenant_access_token"):
            return data["tenant_access_token"]
        print(f"❌ 获取 tenant_access_token 失败: {data}")
    except Exception as e:
        print(f"❌ tenant_access_token 请求异常: {e}")
    return None


def upload_file_to_feishu(token, file_path):
    url = "https://open.feishu.cn/open-apis/im/v1/files"
    ext = os.path.splitext(file_path)[1].lstrip(".").lower() or "pdf"
    file_type = ext if ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx") else "pdf"
    try:
        basename = os.path.basename(file_path)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", basename) or f"report.{file_type}"
        mime = "application/pdf" if file_type == "pdf" else "application/octet-stream"
        with open(file_path, "rb") as f:
            files = {"file": (safe_name, f, mime)}
            data = {"file_type": file_type, "file_name": safe_name}
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            if resp.status_code != 200:
                logid = resp.headers.get("X-Tt-Logid", "")
                print(f"❌ 上传文件失败: HTTP {resp.status_code} {resp.text} {logid}".strip())
                return None
            res = resp.json()
            if res.get("code") == 0 and res.get("data", {}).get("file_key"):
                return res["data"]["file_key"]
            print(f"❌ 上传文件失败: {res}")
    except Exception as e:
        print(f"❌ 上传文件异常: {e}")
    return None


def send_feishu_message(token, receive_id, msg_type, content, receive_id_type="chat_id"):
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    payload = {
        "receive_id": receive_id,
        "msg_type": msg_type,
        "content": json.dumps(content, ensure_ascii=False)
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code != 200:
            logid = resp.headers.get("X-Tt-Logid", "")
            print(f"❌ 飞书发送失败: HTTP {resp.status_code} {resp.text} {logid}".strip())
            return False
        data = resp.json()
        if data.get("code") == 0:
            return True
        print(f"❌ 飞书发送失败: {data}")
    except Exception as e:
        print(f"❌ 飞书请求异常: {e}")
    return False


def send_feishu_report(file_path, stocks, trade_date, backup_url=None):
    """上传文件到飞书并发送消息"""
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    receive_id = os.getenv("FEISHU_RECEIVE_ID") or os.getenv("FEISHU_CHAT_ID")
    receive_id_type = os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id")

    if not app_id or not app_secret or not receive_id:
        print("❌ 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_RECEIVE_ID")
        return

    token = get_tenant_access_token(app_id, app_secret)
    if not token:
        return

    file_key = upload_file_to_feishu(token, file_path)
    # 先尝试发送文件；失败则降级为文本
    if file_key:
        ok = send_feishu_message(token, receive_id, "file", {"file_key": file_key}, receive_id_type)
        if not ok:
            file_key = None

    # 发送简要数据（若文件失败则作为降级通知）
    date_str = datetime.strptime(trade_date, "%Y%m%d").strftime("%Y年%m月%d日")
    total = len(stocks)
    board20_count = len([s for s in stocks if s.get("is_20cm", False)])
    board_more = len([s for s in stocks if s.get("bd", 1) >= 2])
    top5 = sorted(stocks, key=lambda x: x.get("amount", 0), reverse=True)[:5]
    top5_text = "、".join([f"{s['name']}({s['code']})" for s in top5]) if top5 else "—"
    text = (
        f"A股涨停复盘 {date_str}\n"
        f"涨停总数：{total} 家 | 连板：{board_more} 家 | 20CM：{board20_count} 只\n"
        f"成交额前五：{top5_text}"
    )
    if backup_url:
        text += f"\n备用链接：{backup_url}"
    if not file_key:
        text += "\n（文件上传失败，已发送文字通知）"
    send_feishu_message(token, receive_id, "text", {"text": text}, receive_id_type)


# =============================================
# 主程序
# =============================================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 A股涨停复盘自动推送")
    print("=" * 50)

    # 计算交易日期（取前一交易日）
    trade_date = get_trade_date()
    print(f"📅 交易日期: {trade_date}")

    # 1. 获取涨停数据
    stocks = get_limit_up_stocks(trade_date)
    stocks = dedupe_stocks(stocks)
    for s in stocks:
        s["reason"] = _normalize_industry(s.get("reason", ""))

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

    # 4. 发送飞书消息（文件）
    abs_pdf = pdf_file if os.path.isabs(pdf_file) else os.path.join(ROOT_DIR, pdf_file)
    send_feishu_report(abs_pdf, stocks, trade_date, backup_url=url)

    print("=" * 50)
    print(f"✅ 完成！链接: {url}")
    print("=" * 50)
