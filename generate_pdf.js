#!/usr/bin/env node
/**
 * generate_pdf.js
 * 生成涨停复盘 PDF 文档，使用 @sparticuz/chromium（支持 Linux GitHub Actions）
 */

const chromium = require('@sparticuz/chromium');
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

// ========== 样式常量 ==========
const RED = '#C0392B';
const DARK = '#2C3E50';
const GRAY = '#7F8C8D';
const LIGHT_RED_BG = '#FDEDEC';
const LIGHT_GRAY_BG = '#F2F3F4';
const BORDER_COLOR = '#BDC3C7';

// ========== 工具函数 ==========
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime(t) {
  if (!t) return '—';
  t = String(t);
  if (t.length === 5) return `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4)}`;
  if (t.length === 4) return `${t.slice(0, 2)}:${t.slice(2, 4)}:00`;
  return t;
}

// ========== 表格生成器 ==========
function makeTable(headers, rows, colWidths) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  const ths = headers.map((h, i) =>
    `<th style="width:${colWidths[i]}px;background:${LIGHT_RED_BG};color:${RED};font-weight:bold;font-size:10pt;text-align:center;padding:6px 8px;border:1px solid ${BORDER_COLOR};font-family:'Noto Sans CJK SC','Microsoft YaHei','PingFang SC',sans-serif;">${escapeHtml(h)}</th>`
  ).join('');

  const trs = rows.map((row, ri) => {
    const bg = ri % 2 === 0 ? '#FFFFFF' : LIGHT_GRAY_BG;
    const tds = row.map((text, ci) =>
      `<td style="width:${colWidths[ci]}px;background:${bg};color:${DARK};font-size:10pt;text-align:center;padding:6px 8px;border:1px solid ${BORDER_COLOR};font-family:'Noto Sans CJK SC','Microsoft YaHei','PingFang SC',sans-serif;">${escapeHtml(text ?? '—')}</td>`
    ).join('');
    return `<tr>${tds}</tr>`;
  }).join('');

  return `<table style="border-collapse:collapse;width:${total}px;font-size:10pt;">${ths}${trs}</table>`;
}

// ========== 生成市场热点 ==========
function generateHotspots(stocks, board20, moreBoards, sortedIndustry, zbcStocks) {
  const hotspots = [];
  const total = stocks.length;

  if (total >= 50) {
    hotspots.push({ title: '市场整体活跃，涨停家数处于高位', desc: `今日涨停${total}家，短线情绪较好，市场整体参与度较高。` });
  } else if (total >= 20) {
    hotspots.push({ title: '市场整体平稳，涨停数量处于正常区间', desc: `今日涨停${total}家，市场短线情绪一般，整体表现平稳。` });
  } else {
    hotspots.push({ title: '市场情绪低迷，涨停数量较少', desc: `今日涨停${total}家，短线情绪较弱，市场观望情绪浓厚。` });
  }

  if (board20.length > 0) {
    hotspots.push({ title: '创业板/科创板弹性显现', desc: `今日共${board20.length}只20CM涨停个股，资金追逐高弹性方向，创业板赚钱效应明显。` });
  }

  if (moreBoards.length > 0) {
    const maxBd = Math.max(...moreBoards.map(s => s.bd || 1));
    hotspots.push({ title: `连板股表现强势，市场高度达${maxBd}连板`, desc: `连板个股${moreBoards.length}只，龙头股持续连板带动短线情绪，高位股空间打开。` });
  }

  if (sortedIndustry.length > 0) {
    const topSector = sortedIndustry[0];
    hotspots.push({ title: `${topSector[0]}成为今日最强板块`, desc: `${topSector[0]}涨停${topSector[1].length}只，${topSector[1].slice(0, 3).map(s => s.name).join('、')}等领涨，板块内个股批量涨停。` });
  }

  if (zbcStocks.length > 3) {
    hotspots.push({ title: '市场分歧加大，多只个股炸板', desc: `${zbcStocks.length}只个股出现炸板，资金分歧明显，高位股追涨需谨慎。` });
  }

  while (hotspots.length < 6) {
    hotspots.push({ title: '市场结构性分化', desc: '不同板块和个股之间表现差异较大，资金在热点板块和个股间快速轮动。' });
  }

  return hotspots.slice(0, 6);
}

// ========== 构建 HTML ==========
function buildHtml(stocks, tradeDate, marketComment) {
  const dateObj = new Date(`${tradeDate.slice(0, 4)}-${tradeDate.slice(4, 6)}-${tradeDate.slice(6, 8)}`);
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const dateStr = `${dateObj.getFullYear()}年${dateObj.getMonth() + 1}月${dateObj.getDate()}日（${weekdays[dateObj.getDay()]}）`;

  const total = stocks.length;
  const firstBoard = stocks.filter(s => s.bd === 1);
  const board2 = stocks.filter(s => s.bd === 2);
  const board3 = stocks.filter(s => s.bd === 3);
  const board4 = stocks.filter(s => s.bd >= 4);
  const board20 = stocks.filter(s => s.is_20cm);
  const moreBoards = stocks.filter(s => s.bd >= 2);
  const zbcStocks = stocks.filter(s => s.zbc > 0);

  const byAmount = [...stocks].sort((a, b) => (b.amount || 0) - (a.amount || 0));

  const industryMap = {};
  stocks.forEach(s => {
    const ind = s.reason || '其他';
    if (!industryMap[ind]) industryMap[ind] = [];
    industryMap[ind].push(s);
  });
  const sortedIndustry = Object.entries(industryMap).sort((a, b) => b[1].length - a[1].length);

  const boardSummary = [];
  if (board4.length) boardSummary.push(`${board4.length}只4连板`);
  if (board3.length) boardSummary.push(`${board3.length}只3连板`);
  if (board2.length) boardSummary.push(`${board2.length}只2连板`);
  const boardSummaryText = boardSummary.length
    ? `连板个股共${moreBoards.length}只，${boardSummary.join('、')}，具体如下：`
    : `连板个股共${moreBoards.length}只，具体如下：`;

  const hotspots = generateHotspots(stocks, board20, moreBoards, sortedIndustry, zbcStocks);

  const sortedStocks = [...stocks].sort((a, b) => {
    if (b.bd !== a.bd) return (b.bd || 1) - (a.bd || 1);
    return String(a.first_time || '').localeCompare(String(b.first_time || ''));
  });

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>A股涨停复盘 ${tradeDate}</title>
<style>
  @page {
    size: A4;
    margin: 1.2cm 1.5cm 1.2cm 1.5cm;
    @bottom-center {
      content: "第 " counter(page) " 页  |  免责声明：本报告仅供参考，不构成投资建议";
      font-size: 8pt;
      color: ${GRAY};
      font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', 'PingFang SC', sans-serif;
    }
    @top-right {
      content: "A股涨停复盘  |  数据来源：东方财富";
      font-size: 8pt;
      color: ${GRAY};
      font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', 'PingFang SC', sans-serif;
    }
  }
  body {
    font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', 'PingFang SC', sans-serif;
    font-size: 10pt;
    color: ${DARK};
    margin: 0;
    padding: 0;
    background: #fff;
  }
  .title {
    text-align: center;
    font-size: 22pt;
    font-weight: bold;
    color: ${RED};
    margin-bottom: 6px;
    letter-spacing: 2px;
  }
  .subtitle {
    text-align: center;
    font-size: 11pt;
    color: ${GRAY};
    margin-bottom: 16px;
  }
  .market-comment {
    font-size: 10pt;
    color: ${GRAY};
    margin-bottom: 16px;
  }
  h2 {
    font-size: 13pt;
    font-weight: bold;
    color: ${RED};
    border-left: 4px solid ${RED};
    padding-left: 8px;
    margin: 18px 0 10px 0;
    page-break-after: avoid;
  }
  .intro {
    font-size: 10pt;
    color: ${DARK};
    margin-bottom: 8px;
  }
  p.hotspot-title {
    font-size: 11pt;
    font-weight: bold;
    color: ${DARK};
    margin: 10px 0 4px 0;
    page-break-after: avoid;
  }
  p.hotspot-title span.num {
    color: ${RED};
    margin-right: 4px;
  }
  p.hotspot-desc {
    font-size: 9pt;
    color: ${GRAY};
    margin: 0 0 8px 20px;
  }
  .disclaimer {
    font-size: 8pt;
    color: ${GRAY};
    font-style: italic;
    margin-top: 20px;
    text-align: center;
    border-top: 1px solid ${BORDER_COLOR};
    padding-top: 8px;
  }
  .page-break { page-break-before: always; }
  table { page-break-inside: avoid; }
</style>
</head>
<body>

<!-- 标题 -->
<p class="title">A股涨停复盘</p>
<p class="subtitle">${dateStr}  |  ${marketComment || `涨停${total}家，市场整体活跃，详见以下数据。`}</p>

<!-- 一、市场整体数据 -->
<h2>一、市场整体数据</h2>
${makeTable(['指标', '数值', '备注'], [
  ['涨停个股总数', `${total} 家`, '短线情绪良好'],
  ['封板率', zbcStocks.length > 0 ? `${Math.round((total - zbcStocks.length) / total * 100)}%` : '正常', '短线情绪稳定'],
  ['首板个股', `${firstBoard.length} 家`, `占比 ${Math.round(firstBoard.length / total * 100)}%`],
  ['连板个股', `${moreBoards.length} 家`, `最高 ${Math.max(...stocks.map(s => s.bd || 1), 1)} 连板`],
  ['20CM个股', `${board20.length} 只`, '创业板/科创板涨停'],
  ['跌停个股', '关注明日数据', '数据待补充'],
], [2500, 2000, 4360])}

<!-- 二、连板梯队 -->
<h2>二、连板梯队</h2>
<p class="intro">${boardSummaryText}</p>
${board4.length || board3.length || board2.length ? makeTable(['连板数', '家数', '股票名称（代码）', '涨停原因 / 概念'], [
  ...(board4.length ? [['4连板', board4.length, board4.map(s => `${s.name}（${s.code}）`).join('、'), board4[0].reason || '并购重组']] : []),
  ...(board3.length ? [['3连板', board3.length, board3.map(s => `${s.name}（${s.code}）`).join('、'), board3[0].reason || '算力租赁']] : []),
  ...(board2.length ? [['2连板', board2.length, board2.slice(0, 5).map(s => `${s.name}（${s.code}）`).join('、') + (board2.length > 5 ? '...' : ''), board2[0].reason || '题材']] : []),
], [1500, 1200, 4160, 2500]) : '<p class="intro" style="color:' + GRAY + '">暂无连板数据</p>'}

<!-- 三、主要涨停板块分析 -->
<h2>三、主要涨停板块分析</h2>
${sortedIndustry.length ? makeTable(['板块名称', '涨停数', '涨停个股', '核心催化'], sortedIndustry.slice(0, 10).map(([name, ss]) => {
  const reps = ss.slice(0, 4).map(s => `${s.name}${s.bd > 1 ? '(2板)' : ''}`).join('、');
  return [name, `${ss.length}只`, reps + (ss.length > 4 ? '等' : ''), ss[0].reason || '题材'];
}), [2500, 1500, 3360, 2500]) : '<p class="intro" style="color:' + GRAY + '">暂无板块数据</p>'}

<!-- 四、20CM弹性个股 -->
<h2 class="page-break">四、20CM弹性个股（创业板/科创板涨停）</h2>
<p class="intro">今日共${board20.length}只创业板/科创板个股涨停（涨幅达20%），均为首板：</p>
${board20.length ? makeTable(['股票代码', '股票名称', '涨停时间', '涨停原因', '备注'], board20.slice(0, 10).map(s => {
  const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
  return [s.code, s.name, formatTime(s.first_time), s.reason || '题材', `${amountYi}亿成交`];
}), [1800, 2000, 1500, 2060, 2500]) : '<p class="intro" style="color:' + GRAY + '">今日无20CM涨停个股</p>'}

<!-- 五、爆量大票 -->
<h2>五、爆量大票（成交额前列）</h2>
<p class="intro">以下个股今日成交额居前，市场关注度高：</p>
${makeTable(['股票代码', '股票名称', '成交额', '涨停原因 / 概念'], byAmount.slice(0, 10).map(s => {
  const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
  return [s.code, s.name, `${amountYi}亿`, s.reason || '题材'];
}), [2000, 2200, 2160, 3500])}

<!-- 六、分歧炸板个股 -->
<h2>六、分歧炸板个股（炸板后回封）</h2>
<p class="intro">以下个股在涨停后反复炸板但最终封住涨停，反映市场分歧较大：</p>
${zbcStocks.length ? makeTable(['股票代码', '股票名称', '炸板次数', '备注 / 涨停原因'], [...zbcStocks].sort((a, b) => (b.zbc || 0) - (a.zbc || 0)).slice(0, 10).map(s => {
  const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
  return [s.code, s.name, `${s.zbc || 0}次`, `${s.reason || '题材'}，${amountYi}亿成交`];
}), [2000, 2200, 1500, 4160]) : '<p class="intro" style="color:' + GRAY + '">今日无炸板个股，市场封板情绪稳定</p>'}

<!-- 七、市场热点总结 -->
<h2 class="page-break">七、主要舆论点与市场热点总结</h2>
${hotspots.map((h, idx) =>
  `<p class="hotspot-title"><span class="num">${idx + 1}.</span>${escapeHtml(h.title)}</p><p class="hotspot-desc">${escapeHtml(h.desc)}</p>`
).join('\n')}

<!-- 八、涨停全名单 -->
<h2 class="page-break">八、今日涨停全名单（${total}只）</h2>
<p class="intro">以下为今日全部${total}只涨停个股（不含ST股），按连板数及涨停时间排序：</p>
${makeTable(['股票代码', '股票名称', '连板情况', '涨停原因 / 概念'], sortedStocks.map(s => {
  let bdDesc;
  if (s.bd >= 2) bdDesc = `${s.bd}连板`;
  else if (s.is_20cm) bdDesc = '首板/20CM';
  else bdDesc = '首板';
  return [s.code, s.name, bdDesc, s.reason || '题材'];
}), [2000, 2360, 2000, 3500])}

<!-- 免责声明 -->
<p class="disclaimer">免责声明：本报告仅供参考，不构成任何投资建议。A股市场存在风险，投资需谨慎。涨停个股仅为市场数据统计，不代表任何推荐。</p>

</body>
</html>`;

  return html;
}

// ========== 主程序 ==========
if (require.main === module) {
  const inputFile = process.argv[2] || 'stocks.json';
  const tradeDate = process.argv[3] || new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const outputFile = process.argv[4] || `涨停复盘_${tradeDate}.pdf`;
  const marketComment = process.argv[5] || null;

  const stocks = JSON.parse(fs.readFileSync(inputFile, 'utf8'));
  const html = buildHtml(stocks, tradeDate, marketComment);

  (async () => {
    const outDir = path.dirname(outputFile);
    if (outDir && outDir !== '.') {
      fs.mkdirSync(outDir, { recursive: true });
    }
    const browser = await puppeteer.launch({
      args: chromium.args,
      defaultViewport: chromium.defaultViewport,
      executablePath: await chromium.executablePath(),
      headless: chromium.headless,
    });
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'networkidle0' });
    await page.pdf({
      path: outputFile,
      format: 'A4',
      printBackground: true,
      margin: { top: '1.2cm', right: '1.5cm', bottom: '1.2cm', left: '1.5cm' },
      displayHeaderFooter: true,
      headerTemplate: `<span></span>`,
      footerTemplate: `<div style="width:100%;text-align:center;font-size:8pt;color:${GRAY};font-family:微软雅黑,sans-serif;">第 <span class="pageNumber"></span> 页 | 免责声明：本报告仅供参考，不构成投资建议</div>`,
    });
    await browser.close();
    process.stdout.write('OK:' + outputFile);
  })().catch(err => {
    process.stderr.write('ERROR:' + err.message);
    process.exit(1);
  });
}

module.exports = { buildHtml, generateHotspots };
