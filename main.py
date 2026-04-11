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
    """
    使用东方财富涨停榜 API 获取真实数据
    API: http://push2.eastmoney.com/api/qt/clist/get
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    print("📥 正在获取A股涨停数据（东方财富）...")
    
    all_stocks = []
    
    # 东方财富涨停数据 API（涨幅达到10%的股票）
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
        response.encoding = 'utf-8'
        
        # 解析 JSONP 响应
        text = response.text
        json_str = re.search(r'jQuery\((.*)\)', text)
        
        if json_str:
            data = json.loads(json_str.group(1))
            if data.get("data") and data["data"].get("diff"):
                stocks_raw = data["data"]["diff"]
                
                for stock in stocks_raw[:20]:  # 取前20个涨停
                    code = str(stock.get("f12", ""))
                    name = stock.get("f14", "未知")
                    change_pct = stock.get("f3", 0)  # 涨幅百分比
                    # f15=最新价, f16=最高价, f17=最低价, f18=时间
                    reason = stock.get("f15", "") or stock.get("f17", "") or "题材"
                    
                    # 连板数判断（通过涨幅估算）
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
                        "reason": reason[:20] if reason else "题材",
                        "change_pct": change_pct
                    })
        
        print(f"✅ 获取到 {len(all_stocks)} 只涨停股票")
        
    except Exception as e:
        print(f"⚠️ 东方财富 API 请求失败: {e}")
        # 备用：尝试新浪财经
        all_stocks = get_from_sina()
    
    # 如果 API 都失败，返回空列表而非假数据
    if not all_stocks:
        print("⚠️ 所有数据源均失败，请检查网络连接")
        return {
            "date": today,
            "stocks": [],
            "high_level": 0,
            "strong_list": [],
            "yes_info": "数据获取失败，请检查网络"
        }
    
    # 计算连板高度
    high_level = max([s["level"] for s in all_stocks]) if all_stocks else 0
    
    # 强势股（涨幅最大的前3只）
    strong_list = sorted(all_stocks, key=lambda x: x.get("change_pct", 0), reverse=True)[:3]
    
    return {
        "date": today,
        "stocks": all_stocks,
        "high_level": high_level,
        "strong_list": [s["name"] for s in strong_list],
        "yes_info": f"共 {len(all_stocks)} 只个股涨停（数据来源：东方财富）"
    }


def get_from_sina():
    """备用：新浪财经涨停数据"""
    print("📥 尝试从新浪获取...")
    stocks = []
    
    try:
        # 新浪涨幅榜（按涨幅排序，取涨停股）
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = {
            "page": 1,
            "num": 50,
            "sort": "changepercent",
            "asc": 0,
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.encoding = 'gb2312'  # 新浪用 GB2312 编码
        
        data = response.json()
        
        for item in data:
            change = float(item.get("changepercent", 0) or 0)
            # 只取涨停股（涨幅>=9.9%）
            if change >= 9.9:
                code = item.get("symbol", "")
                # 处理代码前缀
                if code.startswith("sh"):
                    code = code[2:]
                elif code.startswith("sz"):
                    code = code[2:]
                
                stocks.append({
                    "code": code,
                    "name": item.get("name", "未知"),
                    "level": 1,
                    "reason": item.get("industry", "题材")[:20] or "题材",
                    "change_pct": change
                })
        
        print(f"✅ 新浪获取到 {len(stocks)} 只涨停")
    except Exception as e:
        print(f"⚠️ 新浪 API 也失败: {e}")
    
    return stocks


# =============================================
# 2. 生成MD并提交到GitHub仓库
# =============================================
def create_md_file(data):
    date = data["date"]
    filename = f"涨停复盘_{date}.md"
    filepath = f"reports/{filename}"
    
    # 确保 reports 目录存在
    os.makedirs("reports", exist_ok=True)

    # 生成连板股票列表
    stocks_table = ""
    for i, s in enumerate(data['stocks'], 1):
        name = s.get('name', '未知')
        code = s.get('code', 'N/A')
        reason = s.get('reason', '题材')
        change = s.get('change_pct', 0)
        level = s.get('level', 1)
        stocks_table += f"| {i} | {name} | {code} | {level}板 | {reason} | +{change:.1f}% |\n"

    # 生成强势股列表
    strong_stocks = ""
    for s in data.get('strong_list', []):
        strong_stocks += f"- **{s}**\n"

    md = f"""# A股涨停复盘

> **日期：** {date}  
> **数据来源：** 东方财富  
> **更新时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 市场整体数据

| 指标 | 数值 | 说明 |
|:---:|:---:|:---|
| 涨停总数 | **{len(data['stocks'])}** 家 | 实时统计 |
| 连板个股 | **{len([s for s in data['stocks'] if s.get('level', 1) >= 2])}** 家 | 强势股 |
| 连板高度 | **{data['high_level']}** 板 | 市场空间 |

---

## 🔥 涨停股票一览

| 序号 | 股票名称 | 代码 | 连板 | 概念题材 | 涨幅 |
|:---:|:---:|:---:|:---:|:---|:---:|
{stocks_table}

---

## ⭐ 强势股点评

{strong_stocks if strong_stocks else '_暂无数据_'}

---

## 📝 行情简评

{data.get('yes_info', '数据已更新')}

---

> ⚠️ **免责声明**：本报告仅供参考，不构成投资建议。股市有风险，入市需谨慎。
"""

    # 保存文件到 reports 目录
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"✅ 已生成 {filepath}")
    return filepath, md


def commit_to_github(filepath):
    """将文件提交到 GitHub 仓库"""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")
    
    if not repo:
        print("⚠️ 未配置 GITHUB_REPOSITORY，跳过提交")
        return None
    
    if not token:
        print("⚠️ 未配置 GITHUB_TOKEN，跳过提交")
        return None
    
    try:
        print("📤 正在提交到 GitHub...")
        
        # 配置远程仓库（带 token 认证）
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        
        # 配置 git
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        
        # 添加文件并提交
        subprocess.run(["git", "add", filepath], check=True)
        subprocess.run([
            "git", "commit", "-m", 
            f"📈 更新涨停复盘 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        
        print("✅ 已提交到 GitHub")
        
        # 返回 raw.githubusercontent.com 链接（直接可访问）
        raw_url = f"https://raw.githubusercontent.com/{repo}/main/{filepath}"
        return raw_url
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️ GitHub 提交失败: {e}")
        return None
    except Exception as e:
        print(f"⚠️ GitHub 提交异常: {e}")
        return None


# =============================================
# 3. 发送飞书卡片消息
# =============================================
def send_card_to_feishu(link, data):
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("❌ 未配置 FEISHU_WEBHOOK")
        return

    # 构建卡片内容
    stock_list = ""
    for s in data.get('stocks', [])[:5]:  # 只显示前5只
        stock_list += f"\n• {s.get('name', '未知')} ({s.get('code', 'N/A')}) +{s.get('change_pct', 0):.1f}%"
    
    strong_text = "、".join(data.get('strong_list', [])[:3]) or "暂无"
    
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 A股涨停复盘 {data['date']}"},
                "template": "red"  # 涨停用红色
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md", 
                        "content": f"**涨停总数：** {len(data['stocks'])} 家\n"
                                   f"**连板高度：** {data['high_level']} 板\n"
                                   f"**强势股：** {strong_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div", 
                    "text": {"tag": "lark_md", "content": f"**今日涨停：**{stock_list}"}
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📄 查看完整复盘"},
                            "type": "primary",
                            "url": link
                        }
                    ]
                }
            ]
        }
    }

    try:
        resp = requests.post(webhook, json=card, timeout=10)
        if resp.status_code == 200:
            print("✅ 已发送卡片到飞书")
        else:
            print(f"❌ 飞书发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ 飞书请求异常: {e}")


# =============================================
# 主程序
# =============================================
if __name__ == "__main__":
    print("=" * 40)
    print("🚀 A股涨停复盘自动推送")
    print("=" * 40)
    
    # 1. 获取真实数据
    data = get_real_stock_data()
    
    # 2. 生成 MD 文件
    filepath, content = create_md_file(data)
    
    # 3. 提交到 GitHub 并获取链接
    url = commit_to_github(filepath)
    
    if not url:
        # 如果 GitHub 提交失败，使用备用链接
        repo = os.getenv("GITHUB_REPOSITORY", "")
        if repo:
            url = f"https://raw.githubusercontent.com/{repo}/main/{filepath}"
        else:
            url = "https://example.com"  # 备用
    
    # 4. 发送到飞书
    send_card_to_feishu(url, data)
    
    print("=" * 40)
    print(f"✅ 复盘链接: {url}")
    print("🎉 全部完成！")
    print("=" * 40)
