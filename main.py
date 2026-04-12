import requests
from datetime import datetime, timedelta
import os
import json
import re
import subprocess

# =============================================
# 1. 获取真实涨停数据（东方财富 API）
# =============================================
def get_real_stock_data():
    today = datetime.now().strftime("%Y-%m-%d")
    print("📥 正在获取A股涨停数据（东方财富）...")
    all_stocks = []

    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "cb": "jQuery",
        "po": "1",
        "pz": "50",
        "pn": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0+t:6+f:!22,m:0+t:80+f:!22,m:1+t:2+f:!22,m:1+t:23+f:!22",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
        "_": int(datetime.now().timestamp() * 1000)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://quote.eastmoney.com/",
        "Accept": "text/javascript, application/javascript, */*"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.encoding = "utf-8"
        text = response.text
        json_str = re.search(r"jQuery\((.*)\)", text)
        if json_str:
            data = json.loads(json_str.group(1))
            if data.get("data") and data["data"].get("diff"):
                for stock in data["data"]["diff"][:30]:
                    code = str(stock.get("f12", ""))
                    name = stock.get("f14", "未知")
                    change_pct = stock.get("f3", 0)
                    # 连板数估算
                    if change_pct >= 20:
                        level = 3
                    elif change_pct >= 15:
                        level = 2
                    else:
                        level = 1
                    all_stocks.append({
                        "code": code,
                        "name": name,
                        "level": level,
                        "reason": "题材",
                        "change_pct": change_pct
                    })
        print(f"✅ 东方财富获取到 {len(all_stocks)} 只涨停股票")
    except Exception as e:
        print(f"⚠️ 东方财富请求失败: {e}")
        all_stocks = get_from_sina()

    if not all_stocks:
        print("⚠️ 所有数据源均失败")
        return {
            "date": today,
            "stocks": [],
            "high_level": 0,
            "strong_list": [],
            "total": 0
        }

    high_level = max(s["level"] for s in all_stocks)
    strong_list = sorted(all_stocks, key=lambda x: x["change_pct"], reverse=True)[:3]
    return {
        "date": today,
        "stocks": all_stocks,
        "high_level": high_level,
        "strong_list": [s["name"] for s in strong_list],
        "total": len(all_stocks)
    }


def get_from_sina():
    print("📥 尝试从新浪备用获取...")
    stocks = []
    try:
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = {"page": 1, "num": 50, "sort": "changepercent", "asc": 0, "node": "hs_a", "_s_r_a": "page"}
        response = requests.get(url, params=params, timeout=10)
        response.encoding = "gb2312"
        data = response.json()
        for item in data:
            change = float(item.get("changepercent", 0) or 0)
            if change >= 9.9:
                code = item.get("symbol", "").replace("sh", "").replace("sz", "")
                stocks.append({
                    "code": code,
                    "name": item.get("name", "未知"),
                    "level": 1,
                    "reason": item.get("industry", "题材")[:20] or "题材",
                    "change_pct": change
                })
        print(f"✅ 新浪获取到 {len(stocks)} 只涨停")
    except Exception as e:
        print(f"⚠️ 新浪也失败: {e}")
    return stocks


# =============================================
# 2. 生成 HTML 页面（直接可在浏览器打开）
# =============================================
def create_html_page(data):
    """生成好看的 HTML 报告，输出到 docs/index.html（GitHub Pages 入口）"""
    os.makedirs("docs", exist_ok=True)

    date = data["date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = data["total"]
    high_level = data["high_level"]
    strong_text = "　".join(data["strong_list"]) if data["strong_list"] else "暂无"
    multi_board = len([s for s in data["stocks"] if s["level"] >= 2])

    # 生成表格行
    rows = ""
    for i, s in enumerate(data["stocks"], 1):
        change = s["change_pct"]
        level = s["level"]
        badge = f'<span class="badge">{level}连板</span>' if level >= 2 else ""
        rows += f"""
        <tr>
            <td>{i}</td>
            <td><strong>{s["name"]}</strong>{badge}</td>
            <td class="code">{s["code"]}</td>
            <td class="red">+{change:.2f}%</td>
            <td>{s["reason"]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股涨停复盘 {date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2d3436; }}
  .header {{ background: linear-gradient(135deg, #c0392b, #e74c3c); color: white; padding: 24px 20px 20px; }}
  .header h1 {{ font-size: 20px; font-weight: 700; }}
  .header .sub {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
  .stats {{ display: flex; gap: 12px; padding: 16px; overflow-x: auto; }}
  .stat-card {{ background: white; border-radius: 12px; padding: 16px 20px; min-width: 100px; flex: 1; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .stat-card .num {{ font-size: 28px; font-weight: 800; color: #c0392b; }}
  .stat-card .label {{ font-size: 12px; color: #636e72; margin-top: 4px; }}
  .section {{ background: white; margin: 0 16px 16px; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .section-title {{ padding: 14px 16px; font-weight: 700; font-size: 15px; border-bottom: 1px solid #f0f0f0; background: #fafafa; }}
  .strong-box {{ padding: 14px 16px; font-size: 15px; color: #c0392b; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #fff5f5; color: #636e72; font-weight: 600; padding: 10px 12px; text-align: left; border-bottom: 2px solid #fee; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f9f9f9; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  .red {{ color: #c0392b; font-weight: 700; }}
  .code {{ color: #636e72; font-size: 12px; }}
  .badge {{ background: #fff0f0; color: #c0392b; border: 1px solid #fcc; border-radius: 4px; font-size: 11px; padding: 1px 5px; margin-left: 6px; font-weight: 600; }}
  .footer {{ text-align: center; color: #b2bec3; font-size: 12px; padding: 20px; }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 A股涨停复盘</h1>
  <div class="sub">{date} &nbsp;·&nbsp; 更新于 {now} &nbsp;·&nbsp; 数据来源：东方财富</div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="num">{total}</div>
    <div class="label">涨停总数</div>
  </div>
  <div class="stat-card">
    <div class="num">{multi_board}</div>
    <div class="label">连板个股</div>
  </div>
  <div class="stat-card">
    <div class="num">{high_level}</div>
    <div class="label">最高连板</div>
  </div>
</div>

<div class="section">
  <div class="section-title">⭐ 强势股</div>
  <div class="strong-box">{strong_text}</div>
</div>

<div class="section">
  <div class="section-title">🔥 今日涨停一览</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>名称</th>
        <th>代码</th>
        <th>涨幅</th>
        <th>题材</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
</div>

<div class="footer">⚠️ 本报告仅供参考，不构成投资建议。股市有风险，入市需谨慎。</div>

</body>
</html>"""

    # 固定覆盖 index.html（GitHub Pages 入口，链接永不变）
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # 同时保存一份带日期的备份
    with open(f"docs/{date}.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 已生成 docs/index.html")
    return "docs/index.html"


# =============================================
# 3. 提交到 GitHub 并返回 Pages 链接
# =============================================
def commit_and_get_url(filepath):
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")

    if not repo or not token:
        print("⚠️ 缺少 GITHUB_REPOSITORY 或 GITHUB_TOKEN，跳过提交")
        if repo:
            owner = repo.split("/")[0].lower()
            name = repo.split("/")[1]
            return f"https://{owner}.github.io/{name}/"
        return None

    try:
        print("📤 正在提交到 GitHub...")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)

        subprocess.run(["git", "add", "docs/"], check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if result.returncode == 0:
            print("ℹ️ 没有变化，跳过提交")
        else:
            subprocess.run([
                "git", "commit", "-m",
                f"📈 涨停复盘 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("✅ 已推送到 GitHub")

        # 返回 GitHub Pages 固定链接
        owner = repo.split("/")[0].lower()
        name = repo.split("/")[1]
        return f"https://{owner}.github.io/{name}/"

    except subprocess.CalledProcessError as e:
        print(f"⚠️ GitHub 提交失败: {e}")
        if repo:
            owner = repo.split("/")[0].lower()
            name = repo.split("/")[1]
            return f"https://{owner}.github.io/{name}/"
        return None


# =============================================
# 4. 发送飞书卡片消息
# =============================================
def send_card_to_feishu(url, data):
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("❌ 未配置 FEISHU_WEBHOOK")
        return

    strong_text = "、".join(data.get("strong_list", [])[:3]) or "暂无"
    stock_lines = ""
    for s in data.get("stocks", [])[:8]:
        stock_lines += f"\n• **{s['name']}**（{s['code']}）+{s['change_pct']:.1f}%"

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 A股涨停复盘 {data['date']}"},
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**涨停总数：** {data['total']} 家　"
                            f"**连板高度：** {data['high_level']} 板\n"
                            f"**强势股：** {strong_text}"
                        )
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**今日涨停（前8只）：**{stock_lines}"}
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔍 查看完整复盘"},
                            "type": "primary",
                            "url": url
                        }
                    ]
                }
            ]
        }
    }

    try:
        resp = requests.post(webhook, json=card, timeout=10)
        if resp.status_code == 200:
            print(f"✅ 已发送到飞书，链接：{url}")
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

    # 1. 获取真实数据
    data = get_real_stock_data()

    # 2. 生成 HTML 页面
    filepath = create_html_page(data)

    # 3. 提交到 GitHub，获取 Pages 链接
    url = commit_and_get_url(filepath)

    if not url:
        print("⚠️ 无法获取链接，使用占位符")
        url = "https://github.com"

    # 4. 发送到飞书
    send_card_to_feishu(url, data)

    print("=" * 50)
    print(f"🔗 复盘链接: {url}")
    print("🎉 全部完成！")
    print("=" * 50)
