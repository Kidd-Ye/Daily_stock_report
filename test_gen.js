const { generateDocx } = require('./generate_docx.js');
const { Packer } = require('./node_modules/docx');
const fs = require('fs');

const stocks = [
  {code:'600743',name:'华远控股',bd:4,amount:1234567890,is_20cm:false,first_time:'093000',zbc:0,reason:'并购重组'},
  {code:'000889',name:'中嘉博创',bd:3,amount:987654321,is_20cm:false,first_time:'093500',zbc:0,reason:'算力租赁'},
  {code:'001309',name:'德明利',bd:1,amount:10190000000,is_20cm:false,first_time:'100500',zbc:1,reason:'半导体/存储芯片'},
  {code:'300131',name:'英唐智控',bd:1,amount:3781000000,is_20cm:true,first_time:'140327',zbc:2,reason:'其他电子'},
  {code:'688690',name:'纳微科技',bd:1,amount:704000000,is_20cm:true,first_time:'093522',zbc:0,reason:'化学制药'},
  {code:'000762',name:'西藏矿业',bd:1,amount:876000000,is_20cm:false,first_time:'101500',zbc:8,reason:'能源金属'},
  {code:'002580',name:'圣阳股份',bd:2,amount:654000000,is_20cm:false,first_time:'094500',zbc:9,reason:'储能锂电'},
];

const doc = generateDocx(stocks, '20260410', '创业板指大涨3.78%创阶段新高，储能锂电与算力产业链成最大亮点。');
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('test_report.docx', buf);
  console.log('OK: test_report.docx');
}).catch(e => { console.error(e.stack); process.exit(1); });
