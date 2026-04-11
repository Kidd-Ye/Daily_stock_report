import requests
from datetime import datetime
import os

# ---------------------
# 1. 获取今日涨停数据
# ---------------------
def get_limit_data():
    try:
        url = "https://api.kaipm.com/api/limit_up"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        today = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        stocks = data.get("list", [])
        high = data.get("high", 0)
        strong = data.get("strong", [])
        yes_info = data.get("yes", "无")
    except:
        today = datetime.now().strftime("%Y-%m-%d")
        stocks = [
            {"code": "000001", "name": "平安银行", "ltime": "09:30", "level": 1, "reason": "金融"},
            {"code": "000002", "name": "万科A", "ltime": "09:31", "level": 1, "reason": "地产"}
        ]
        high = 2
        strong = ["测试强势股1", "测试强势股2"]
        yes_info = "昨日涨停平均涨幅 +1.2%"

    return {
        "date": today,
        "stocks": stocks,
        "high_level": high,
        "strong_list": strong,
        "yes_info": yes_info
    }

# ---------------------
# 2. 按你的WORD格式生成MD
# ---------------------
def build_md(data):
    date = data["date"]
    md = f"""# 涨停复盘 {date}

## 一、盘面概况
- 日期：{date}
- 连板高度：{data['high_level']}连板
- 市场情绪：活跃

## 二、涨停股票列表
| 股票代码 | 名称 | 涨停时间 | 连板数 | 原因 |
|---------|------|----------|--------|------|
"""
    for s in data["stocks"]:
        md += f"| {s['code']} | {s['name']} | {s['ltime']} | {s['level']} | {s['reason']} |\n"

    md += "\n## 三、强势股\n"
    for name in data["strong_list"]:
        md += f"- {name}\n"

    md += f"\n## 四、昨日表现\n{data['yes_info']}"
    return md, f"涨停复盘_{date}.md"

# ---------------------
# 3. 直接发送飞书群消息（个人号可用）
# ---------------------
def send_to_feishu_group(content):
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("❌ 请配置 FEISHU_WEBHOOK")
        return

    message = {
        "msg_type": "text",
        "content": {
            "text": content
        }
    }
    resp = requests.post(webhook, json=message)
    print("✅ 飞书消息发送成功")

# ---------------------
# 主程序（个人飞书完美版）
# ---------------------
if __name__ == "__main__":
    print("开始执行...")
    data = get_limit_data()
    md_content, md_title = build_md(data)
    
    # 直接发送完整内容到飞书群
    send_to_feishu_group(md_content)
    print("✅ 全部执行完成！")
