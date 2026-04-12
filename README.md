# Daily_stock_report

A股涨停复盘自动化：抓取数据 → 生成 PDF → 上传飞书并推送。

## 数据源

本项目支持两种数据源，通过 `DATA_SOURCE` 环境变量切换：

| 数据源 | `DATA_SOURCE` | 说明 | 额外配置 |
|--------|:---:|------|----------|
| 东方财富 push2ex（默认） | `eastmoney` | 公开免费接口，无需 Key | 无 |
| 妙想 API | `mx` | 东方财富妙想 AI 接口，数据更规范 | 需要 `MX_APIKEY` |

## 环境变量

### 基础配置

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用凭证
- `FEISHU_RECEIVE_ID`：接收对象 ID（群聊用 `chat_id`）
- `FEISHU_RECEIVE_ID_TYPE`：接收类型，默认 `chat_id`
- `GITHUB_TOKEN` / `GITHUB_REPOSITORY`：用于提交报告（可选）

### 数据源配置

- `DATA_SOURCE`：数据源选择，`eastmoney`（默认）或 `mx`
- `MX_APIKEY`：妙想 API Key（使用妙想数据源时必需，在 [妙想 Skills 页面](https://dl.dfcfs.com/m/itc4) 获取）

### 其他

- `TRADE_DATE=YYYYMMDD`：手动指定交易日（可选）
- `USE_TODAY_IF_TRADE_DAY=1`：若今天是交易日则用今天（可选）

## 使用示例

```bash
# 默认数据源（东方财富）
python main.py

# 使用妙想 API 数据源
DATA_SOURCE=mx MX_APIKEY=your_key python main.py

# 指定日期 + 妙想数据源
DATA_SOURCE=mx MX_APIKEY=your_key TRADE_DATE=20260410 python main.py
```

## GitHub Actions 配置

切换数据源时，在仓库 Settings → Secrets and variables → Actions 中：

- **使用妙想数据源**：
  1. Variables 中添加 `DATA_SOURCE` = `mx`
  2. Secrets 中添加 `MX_APIKEY` = 你的 API Key
- **切回东方财富**：Variables 中将 `DATA_SOURCE` 改为 `eastmoney` 或删除即可
