#!/usr/bin/env node
/**
 * generate_docx.js
 * 生成涨停复盘 Word 文档，完全匹配模板格式
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, ExternalHyperlink,
  LevelFormat, UnderlineType
} = require('./node_modules/docx');
const fs = require('fs');
const path = require('path');

// ========== 样式常量 ==========
const RED = 'C0392B';
const DARK = '2C3E50';
const GRAY = '7F8C8D';
const LIGHT_RED = 'FDEDEC';
const LIGHT_GRAY = 'F2F3F4';
const BORDER_COLOR = 'BDC3C7';
const CONTENT_WIDTH = 9360; // A4 内容宽度

// 边框样式
const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: BORDER_COLOR };
const cellBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };

// ========== 工具函数 ==========
function txt(text, opts = {}) {
  return new TextRun({ text, ...opts });
}

function bold(text, opts = {}) {
  return txt(text, { bold: true, ...opts });
}

function heading(text) {
  return new Paragraph({
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true, size: 28, color: RED, font: '微软雅黑' })]
  });
}

function para(children, opts = {}) {
  return new Paragraph({ children, spacing: { before: 60, after: 60 }, ...opts });
}

function cell(text, opts = {}) {
  const {
    w,      // 列宽
    bold: isBold = false,
    align = AlignmentType.LEFT,
    bg,     // 背景色
    color,
    size = 20, // 半磅
    vAlign = VerticalAlign.CENTER,
  } = opts;

  return new TableCell({
    borders: cellBorders,
    width: { size: w, type: WidthType.DXA },
    verticalAlign: vAlign,
    shading: bg ? { fill: bg, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({
        text,
        bold: isBold,
        color: color || DARK,
        size,
        font: '微软雅黑'
      })]
    })]
  });
}

// ========== 表格生成器 ==========
function makeTable(headers, rows, colWidths) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => cell(h, {
      w: colWidths[i],
      bold: true,
      bg: LIGHT_RED,
      color: RED,
      size: 20,
      align: AlignmentType.CENTER
    }))
  });

  const dataRows = rows.map((row, ri) => {
    const bg = ri % 2 === 0 ? 'FFFFFF' : LIGHT_GRAY;
    return new TableRow({
      children: row.map((text, ci) => cell(String(text ?? '—'), {
        w: colWidths[ci],
        bg,
        size: 20,
        align: AlignmentType.CENTER
      }))
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...dataRows]
  });
}

// ========== 主要生成函数 ==========
function generateDocx(stocks, tradeDate, marketComment) {
  // 日期格式化
  const dateObj = new Date(`${tradeDate.slice(0,4)}-${tradeDate.slice(4,6)}-${tradeDate.slice(6,8)}`);
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const dateStr = `${dateObj.getFullYear()}年${dateObj.getMonth()+1}月${dateObj.getDate()}日（${weekdays[dateObj.getDay()]}）`;

  // ===== 数据统计 =====
  const total = stocks.length;
  const firstBoard = stocks.filter(s => s.bd === 1);
  const board2 = stocks.filter(s => s.bd === 2);
  const board3 = stocks.filter(s => s.bd === 3);
  const board4 = stocks.filter(s => s.bd >= 4);
  const board20 = stocks.filter(s => s.is_20cm);
  const moreBoards = stocks.filter(s => s.bd >= 2);
  const zbcStocks = stocks.filter(s => s.zbc > 0);

  // 成交额排序
  const byAmount = [...stocks].sort((a, b) => (b.amount || 0) - (a.amount || 0));

  // 行业分组
  const industryMap = {};
  stocks.forEach(s => {
    const ind = s.reason || '其他';
    if (!industryMap[ind]) industryMap[ind] = [];
    industryMap[ind].push(s);
  });
  const sortedIndustry = Object.entries(industryMap).sort((a, b) => b[1].length - a[1].length);

  // 连板梯队描述
  const boardSummary = [];
  if (board4.length) boardSummary.push(`${board4.length}只4连板`);
  if (board3.length) boardSummary.push(`${board3.length}只3连板`);
  if (board2.length) boardSummary.push(`${board2.length}只2连板`);
  const boardSummaryText = boardSummary.length ? `连板个股共${moreBoards.length}只，${boardSummary.join('、')}，具体如下：` : `连板个股共${moreBoards.length}只，具体如下：`;

  // ===== 文档结构 =====
  const children = [];

  // 标题
  children.push(new Paragraph({
    spacing: { before: 0, after: 120 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: 'A股涨停复盘',
      bold: true, size: 48, color: RED, font: '微软雅黑'
    })]
  }));

  // 日期 + 市场概况
  children.push(para([
    bold(dateStr, { size: 26, color: DARK }),
    txt('  |  ', { size: 26, color: GRAY }),
    txt(marketComment || `涨停${total}家，市场整体活跃，详见以下数据。`, { size: 24, color: GRAY })
  ], { alignment: AlignmentType.LEFT }));

  // ===== 一、市场整体数据 =====
  children.push(heading('一、市场整体数据'));

  const marketRows = [
    ['涨停个股总数', `${total} 家`, '短线情绪良好'],
    ['封板率', zbcStocks.length > 0 ? `${Math.round((total - zbcStocks.length) / total * 100)}%` : '正常', '短线情绪稳定'],
    ['首板个股', `${firstBoard.length} 家`, `占比 ${Math.round(firstBoard.length / total * 100)}%`],
    ['连板个股', `${moreBoards.length} 家`, `最高 ${Math.max(...stocks.map(s=>s.bd||1), 1)} 连板`],
    ['20CM个股', `${board20.length} 只`, '创业板/科创板涨停'],
    ['跌停个股', '关注明日数据', '数据待补充'],
  ];
  children.push(makeTable(['指标', '数值', '备注'], marketRows, [2500, 2000, 4860]));

  // ===== 二、连板梯队 =====
  children.push(heading('二、连板梯队'));
  children.push(para([txt(boardSummaryText, { size: 22, color: DARK })]));

  const boardRows = [];
  if (board4.length) {
    boardRows.push(['4连板', board4.length, board4.map(s => `${s.name}（${s.code}）`).join('、'), (board4[0].reason || '并购重组')]);
  }
  if (board3.length) {
    boardRows.push(['3连板', board3.length, board3.map(s => `${s.name}（${s.code}）`).join('、'), (board3[0].reason || '算力租赁')]);
  }
  if (board2.length) {
    const names = board2.slice(0, 5).map(s => `${s.name}（${s.code}）`).join('、');
    boardRows.push(['2连板', board2.length, names + (board2.length > 5 ? '...' : ''), (board2[0].reason || '题材')]);
  }
  if (boardRows.length) {
    children.push(makeTable(['连板数', '家数', '股票名称（代码）', '涨停原因 / 概念'], boardRows, [1500, 1200, 3660, 3000]));
  } else {
    children.push(para([txt('暂无连板数据', { color: GRAY, size: 22 })]));
  }

  // ===== 三、主要涨停板块分析 =====
  children.push(heading('三、主要涨停板块分析'));
  const sectorRows = sortedIndustry.slice(0, 10).map(([name, ss]) => {
    const reps = ss.slice(0, 4).map(s => `${s.name}${s.bd > 1 ? '(2板)' : ''}`).join('、');
    const cat = ss.length > 4 ? '等' : '';
    return [name, `${ss.length}只`, reps + cat, (ss[0].reason || '题材')];
  });
  if (sectorRows.length) {
    children.push(makeTable(['板块名称', '涨停数', '涨停个股', '核心催化'], sectorRows, [2500, 1500, 3360, 2000]));
  } else {
    children.push(para([txt('暂无板块数据', { color: GRAY, size: 22 })]));
  }

  // ===== 四、20CM弹性个股 =====
  children.push(heading('四、20CM弹性个股（创业板/科创板涨停）'));
  children.push(para([txt(`今日共${board20.length}只创业板/科创板个股涨停（涨幅达20%），均为首板：`, { size: 22, color: DARK })]));
  const cm20Rows = board20.slice(0, 10).map(s => {
    const ft = formatTime(s.first_time);
    const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
    return [s.code, s.name, ft, s.reason || '题材', `${amountYi}亿成交`];
  });
  if (cm20Rows.length) {
    children.push(makeTable(['股票代码', '股票名称', '涨停时间', '涨停原因', '备注'], cm20Rows, [1800, 2000, 1500, 2060, 2000]));
  } else {
    children.push(para([txt('今日无20CM涨停个股', { color: GRAY, size: 22 })]));
  }

  // ===== 五、爆量大票 =====
  children.push(heading('五、爆量大票（成交额前列）'));
  children.push(para([txt('以下个股今日成交额居前，市场关注度高：', { size: 22, color: DARK })]));
  const amountRows = byAmount.slice(0, 10).map(s => {
    const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
    return [s.code, s.name, `${amountYi}亿`, s.reason || '题材'];
  });
  if (amountRows.length) {
    children.push(makeTable(['股票代码', '股票名称', '成交额', '涨停原因 / 概念'], amountRows, [2000, 2200, 2160, 3000]));
  }

  // ===== 六、分歧炸板个股 =====
  children.push(heading('六、分歧炸板个股（炸板后回封）'));
  children.push(para([txt('以下个股在涨停后反复炸板但最终封住涨停，反映市场分歧较大：', { size: 22, color: DARK })]));
  const zbcRows = [...zbcStocks].sort((a, b) => (b.zbc || 0) - (a.zbc || 0)).slice(0, 10).map(s => {
    const amountYi = ((s.amount || 0) / 100000000).toFixed(2);
    return [s.code, s.name, `${s.zbc || 0}次`, `${s.reason || '题材'}，${amountYi}亿成交`];
  });
  if (zbcRows.length) {
    children.push(makeTable(['股票代码', '股票名称', '炸板次数', '备注 / 涨停原因'], zbcRows, [2000, 2200, 1500, 3660]));
  } else {
    children.push(para([txt('今日无炸板个股，市场封板情绪稳定', { color: GRAY, size: 22 })]));
  }

  // ===== 七、市场热点总结 =====
  children.push(heading('七、主要舆论点与市场热点总结'));

  // 生成6条市场热点（基于数据自动生成）
  const hotspots = generateHotspots(stocks, board20, moreBoards, sortedIndustry, zbcStocks);
  hotspots.forEach((h, idx) => {
    // 标题行
    children.push(para([
      txt(`${idx + 1}. `, { bold: true, size: 22, color: RED }),
      txt(h.title, { bold: true, size: 22, color: DARK })
    ], { spacing: { before: 120, after: 60 } }));
    // 描述行
    children.push(para([txt(h.desc, { size: 20, color: GRAY })], { indent: { left: 360 } }));
  });

  // ===== 八、涨停全名单 =====
  children.push(heading('八、今日涨停全名单（' + total + '只）'));
  children.push(para([txt(`以下为今日全部${total}只涨停个股（不含ST股），按连板数及涨停时间排序：`, { size: 22, color: DARK })]));

  const sortedStocks = [...stocks].sort((a, b) => {
    if (b.bd !== a.bd) return (b.bd || 1) - (a.bd || 1);
    return String(a.first_time || '').localeCompare(String(b.first_time || ''));
  });

  const fullListRows = sortedStocks.map((s, i) => {
    let bdDesc;
    if (s.bd >= 2) bdDesc = `${s.bd}连板`;
    else if (s.is_20cm) bdDesc = '首板/20CM';
    else bdDesc = '首板';
    return [s.code, s.name, bdDesc, s.reason || '题材'];
  });
  children.push(makeTable(['股票代码', '股票名称', '连板情况', '涨停原因 / 概念'], fullListRows, [2000, 2360, 2000, 3000]));

  // ===== 免责声明 =====
  children.push(new Paragraph({ spacing: { before: 240, after: 60 }, children: [
    new TextRun({ text: '免责声明：本报告仅供参考，不构成任何投资建议。A股市场存在风险，投资需谨慎。涨停个股仅为市场数据统计，不代表任何推荐。', size: 18, color: GRAY, italics: true })
  ]}));

  // ===== 生成文档 ======
  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: '微软雅黑', size: 22, color: DARK } }
      }
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RED, space: 1 } },
            children: [new TextRun({ text: 'A股涨停复盘  |  数据来源：东方财富', size: 18, color: GRAY })]
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            border: { top: { style: BorderStyle.SINGLE, size: 4, color: BORDER_COLOR, space: 1 } },
            children: [
              new TextRun({ text: '第 ', size: 18, color: GRAY }),
              new TextRun({ children: [PageNumber.CURRENT], size: 18, color: GRAY }),
              new TextRun({ text: ' 页', size: 18, color: GRAY }),
              new TextRun({ text: '  |  免责声明：本报告仅供参考，不构成投资建议', size: 18, color: GRAY })
            ]
          })]
        })
      },
      children
    }]
  });

  return doc;
}

// 格式化时间
function formatTime(t) {
  if (!t) return '—';
  t = String(t);
  if (t.length === 5) return `${t.slice(0,2)}:${t.slice(2,4)}:${t.slice(4)}`;
  if (t.length === 4) return `${t.slice(0,2)}:${t.slice(2,4)}:00`;
  return t;
}

// 生成市场热点（基于数据智能分析）
function generateHotspots(stocks, board20, moreBoards, sortedIndustry, zbcStocks) {
  const hotspots = [];
  const total = stocks.length;

  // 1. 整体情绪
  if (total >= 50) {
    hotspots.push({ title: '市场整体活跃，涨停家数处于高位', desc: `今日涨停${total}家，短线情绪较好，市场整体参与度较高。` });
  } else if (total >= 20) {
    hotspots.push({ title: '市场整体平稳，涨停数量处于正常区间', desc: `今日涨停${total}家，市场短线情绪一般，整体表现平稳。` });
  } else {
    hotspots.push({ title: '市场情绪低迷，涨停数量较少', desc: `今日涨停${total}家，短线情绪较弱，市场观望情绪浓厚。` });
  }

  // 2. 20CM
  if (board20.length > 0) {
    hotspots.push({ title: '创业板/科创板弹性显现', desc: `今日共${board20.length}只20CM涨停个股，资金追逐高弹性方向，创业板赚钱效应明显。` });
  }

  // 3. 连板股
  if (moreBoards.length > 0) {
    const maxBd = Math.max(...moreBoards.map(s => s.bd || 1));
    hotspots.push({ title: `连板股表现强势，市场高度达${maxBd}连板`, desc: `连板个股${moreBoards.length}只，龙头股持续连板带动短线情绪，高位股空间打开。` });
  }

  // 4. 板块热点
  if (sortedIndustry.length > 0) {
    const topSector = sortedIndustry[0];
    hotspots.push({ title: `${topSector[0]}成为今日最强板块`, desc: `${topSector[0]}涨停${topSector[1].length}只，${topSector[1].slice(0,3).map(s=>s.name).join('、')}等领涨，板块内个股批量涨停。` });
  }

  // 5. 炸板
  if (zbcStocks.length > 3) {
    hotspots.push({ title: '市场分歧加大，多只个股炸板', desc: `${zbcStocks.length}只个股出现炸板，资金分歧明显，高位股追涨需谨慎。` });
  }

  // 6. 补满6条
  while (hotspots.length < 6) {
    hotspots.push({ title: '市场结构性分化', desc: '不同板块和个股之间表现差异较大，资金在热点板块和个股间快速轮动。' });
  }

  return hotspots.slice(0, 6);
}

// ========== 主程序 ==========
if (require.main === module) {
  const inputFile = process.argv[2] || 'stocks.json';
  const tradeDate = process.argv[3] || new Date().toISOString().slice(0,10).replace(/-/g,'');
  const outputFile = process.argv[4] || `涨停复盘_${tradeDate}.docx`;
  const marketComment = process.argv[5] || null;

  const stocks = JSON.parse(fs.readFileSync(inputFile, 'utf8'));
  const doc = generateDocx(stocks, tradeDate, marketComment);
  const outDir = path.dirname(outputFile);
  if (outDir && outDir !== '.') {
    fs.mkdirSync(outDir, { recursive: true });
  }
  Packer.toBuffer(doc).then(buf => {
    fs.writeFileSync(outputFile, buf);
    console.log('OK:' + outputFile);
  }).catch(err => {
    console.error('ERROR:', err.message);
    process.exit(1);
  });
}

module.exports = { generateDocx, generateHotspots };
