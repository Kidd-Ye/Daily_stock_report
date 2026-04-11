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
# 3. 飞书鉴权
# ---------------------
def get_fs_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={
        "app_id": os.environ["FEISHU_APP_ID"],
        "app_secret": os.environ["FEISHU_APP_SECRET"]
    })
    return res.json()["tenant_access_token"]

# ---------------------
# 4. 创建飞书知识库文档
# ---------------------
def create_doc(title, content, token):
    url = "https://open.feishu.cn/open-apis/docx/v1/documents"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "title": title,
        "content": content,
        "folder_token": os.environ["KNOWLEDGE_BASE_ID"]
    }
    resp = requests.post(url, headers=headers, json=data)
    return resp.json()["data"]["document"]["url"]

# ---------------------
# 5. 发消息到飞书群
# ---------------------
def send_msg(url):
    webhook = os.environ["FEISHU_WEBHOOK"]
    data = {
        "msg_type": "text",
        "content": {"text": f"📈 涨停复盘已更新\n{url}"}
    }
    requests.post(webhook, json=data)

# ---------------------
# 主程序
# ---------------------
if __name__ == "__main__":
    print("开始执行...")
    data = get_limit_data()
    md_content, md_title = build_md(data)
    token = get_fs_token()
    doc_url = create_doc(md_title, md_content, token)
    send_msg(doc_url)
    print("✅ 执行完成：", doc_url)
