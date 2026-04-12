# Daily_stock_report

A股涨停复盘自动化：抓取数据 → 生成 PDF → 上传飞书并推送。

## 环境变量

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用凭证
- `FEISHU_RECEIVE_ID`：接收对象 ID（群聊用 `chat_id`）
- `FEISHU_RECEIVE_ID_TYPE`：接收类型，默认 `chat_id`
- `GITHUB_TOKEN` / `GITHUB_REPOSITORY`：用于提交报告（可选）
- `TRADE_DATE=YYYYMMDD`：手动指定交易日（可选）
- `USE_TODAY_IF_TRADE_DAY=1`：若今天是交易日则用今天（可选）
