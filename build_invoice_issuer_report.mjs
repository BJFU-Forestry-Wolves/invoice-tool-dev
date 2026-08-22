import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath, previewDir] = process.argv.slice(2);
if (!inputPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build_invoice_issuer_report.mjs <result.json> <output.xlsx> <preview-dir>");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const summary = workbook.worksheets.add("单日同公司汇总");
const details = workbook.worksheets.add("发票识别明细");
const review = workbook.worksheets.add("待人工复核");
const stats = workbook.worksheets.add("运行统计");

const colors = {
  navy: "#16324F",
  blue: "#2563EB",
  paleBlue: "#EAF2FF",
  paleRed: "#FDECEC",
  red: "#B91C1C",
  paleYellow: "#FFF7D6",
  green: "#18794E",
  line: "#D8E1EA",
  text: "#1F2937",
};

function title(sheet, range, text, note) {
  sheet.getRange(range).merge();
  sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { bold: true, color: "#FFFFFF", size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 30;
  if (note) {
    const noteRange = sheet.getRange(range.replace(/1/g, "2"));
    noteRange.merge();
    noteRange.values = [[note]];
    noteRange.format = { fill: colors.paleBlue, font: { color: colors.text }, wrapText: true };
    noteRange.format.rowHeight = 34;
  }
}

function header(range) {
  range.format = {
    fill: colors.blue,
    font: { bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.line },
  };
  range.format.rowHeight = 28;
}

function body(range) {
  range.format = {
    font: { color: colors.text },
    verticalAlignment: "top",
    borders: { insideHorizontal: { style: "thin", color: colors.line } },
  };
}

for (const sheet of [summary, details, review, stats]) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(3);
}

title(
  summary,
  "A1:H1",
  "单日同开票公司限额核验",
  "口径：按订单日期＋规范化销售方名称汇总；同一报销编号金额只计一次；合计大于 1000 元为超额。铁路电子客票按业务类别归组，不代表票面展示了具体法人名称。",
);
summary.getRange("A3:H3").values = [["订单日期", "开票公司/业务归组", "当日合计（元）", "核验状态", "报销编号数", "报销编号", "发票文件", "证据"]];
header(summary.getRange("A3:H3"));
const groups = payload.daily_groups || [];
if (groups.length) {
  summary.getRangeByIndexes(3, 0, groups.length, 8).values = groups.map((item) => [
    new Date(`${item.order_date}T00:00:00`),
    item.issuer_name,
    Number(item.total_amount),
    null,
    item.bx_ids.length,
    item.bx_ids.join("、"),
    item.source_files.join("、"),
    item.evidence_text,
  ]);
  const end = groups.length + 3;
  summary.getRange(`D4`).formulas = [["=IF(C4>'运行统计'!$B$2,\"超额\",\"通过\")"]];
  summary.getRange(`D4:D${end}`).fillDown();
  summary.getRange(`A4:A${end}`).format.numberFormat = "yyyy-mm-dd";
  summary.getRange(`C4:C${end}`).format.numberFormat = "#,##0.00";
  summary.getRange(`D4:D${end}`).conditionalFormats.add("containsText", { text: "超额", format: { fill: colors.paleRed, font: { bold: true, color: colors.red } } });
  body(summary.getRange(`A4:H${end}`));
  summary.tables.add(`A3:H${end}`, true, "DailyMerchantTable").style = "TableStyleMedium2";
}
summary.getRange("A:H").format.wrapText = true;
summary.getRange("A:A").format.columnWidth = 13;
summary.getRange("B:B").format.columnWidth = 34;
summary.getRange("C:E").format.columnWidth = 15;
summary.getRange("F:G").format.columnWidth = 30;
summary.getRange("H:H").format.columnWidth = 46;

title(details, "A1:J1", "发票销售方 OCR 明细", "AUTO_ACCEPTED 可直接用于汇总；NOT_INVOICE 表示识别为运单/对账等辅助附件，未参与金额归组。原发票仍保存在附件目录，不嵌入工作簿。" );
details.getRange("A3:J3").values = [["报销编号", "发票文件", "销售方名称", "规范化名称", "置信度", "识别状态", "页码", "候选数", "证据", "错误代码"]];
header(details.getRange("A3:J3"));
const files = payload.files || [];
if (files.length) {
  details.getRangeByIndexes(3, 0, files.length, 10).values = files.map((item) => [
    item.bx_id,
    item.source_file,
    item.issuer_name || "",
    item.normalized_issuer || "",
    Number(item.confidence_score || 0) / 100,
    item.status,
    item.page_index === null ? null : Number(item.page_index) + 1,
    item.candidate_count,
    item.evidence_text,
    item.error_code || "",
  ]);
  const end = files.length + 3;
  details.getRange(`E4:E${end}`).format.numberFormat = "0%";
  body(details.getRange(`A4:J${end}`));
  details.tables.add(`A3:J${end}`, true, "InvoiceDetailTable").style = "TableStyleMedium2";
}
details.getRange("A:A").format.columnWidth = 18;
details.getRange("B:B").format.columnWidth = 24;
details.getRange("C:D").format.columnWidth = 34;
details.getRange("E:H").format.columnWidth = 13;
details.getRange("I:I").format.columnWidth = 52;
details.getRange("J:J").format.columnWidth = 20;
details.getRange("A:J").format.wrapText = true;

title(review, "A1:J1", "待人工复核", "这里主要是订单日期缺失、清单关联异常或一条报销记录出现多个销售方。黄色列可填写人工结论；销售方 OCR 本轮没有待复核项。" );
review.getRange("A3:J3").values = [["报销编号", "发票文件", "复核原因", "OCR销售方", "关联日期", "报销金额", "人工确认销售方", "人工确认日期", "复核人", "备注"]];
header(review.getRange("A3:J3"));
const reviews = payload.review_items || [];
if (reviews.length) {
  review.getRangeByIndexes(3, 0, reviews.length, 10).values = reviews.map((item) => [
    item.bx_id,
    item.source_files.join("、"),
    item.reason,
    item.issuer_names.join("、"),
    item.order_dates.join("、"),
    item.amount === null ? null : Number(item.amount),
    "",
    null,
    "",
    "",
  ]);
  const end = reviews.length + 3;
  review.getRange(`F4:F${end}`).format.numberFormat = "#,##0.00";
  review.getRange(`H4:H${end}`).format.numberFormat = "yyyy-mm-dd";
  review.getRange(`G4:J${end}`).format.fill = colors.paleYellow;
  body(review.getRange(`A4:J${end}`));
  review.tables.add(`A3:J${end}`, true, "ManualReviewTable").style = "TableStyleMedium2";
}
review.getRange("A:A").format.columnWidth = 18;
review.getRange("B:B").format.columnWidth = 34;
review.getRange("C:C").format.columnWidth = 38;
review.getRange("D:E").format.columnWidth = 28;
review.getRange("F:F").format.columnWidth = 15;
review.getRange("G:J").format.columnWidth = 22;
review.getRange("A:J").format.wrapText = true;

title(stats, "A1:D1", "运行统计与核验口径", "本页的单日限额是汇总表公式的唯一阈值来源，可按制度调整。" );
stats.getRange("A3:B3").values = [["指标", "值"]];
header(stats.getRange("A3:B3"));
const statRows = [
  ["单日同公司限额（元）", Number(payload.daily_limit)],
  ["发票文件数", payload.stats.total_files],
  ["销售方自动确认", payload.stats.auto_accepted],
  ["销售方待复核", payload.stats.needs_review],
  ["忽略的非发票附件", payload.stats.ignored_non_invoice || 0],
  ["OCR失败", payload.stats.ocr_failed],
  ["已形成日期＋公司组", payload.stats.daily_groups],
  ["超额组", payload.stats.exceeded_groups],
  ["聚合待复核项", payload.stats.aggregation_review_items],
  ["OCR缓存命中", payload.stats.ocr_cache_hits],
  ["扫描异常", payload.stats.scan_issues],
  ["耗时（秒）", payload.stats.elapsed_seconds],
  ["生成时间", payload.generated_at],
  ["提取规则版本", payload.extractor_version],
  ["OCR引擎指纹", payload.engine_fingerprint],
];
stats.getRangeByIndexes(3, 0, statRows.length, 2).values = statRows;
body(stats.getRange(`A4:B${statRows.length + 3}`));
stats.getRange("B4").format.numberFormat = "#,##0.00";
stats.getRange("B5:B14").format.numberFormat = "#,##0";
stats.getRange("B15").format.numberFormat = "#,##0.00";
stats.getRange("A:A").format.columnWidth = 30;
stats.getRange("B:B").format.columnWidth = 58;
stats.getRange("A:B").format.wrapText = true;
stats.getRange("A20:D20").values = [["关键口径", "说明", null, null]];
stats.getRange("A20:D20").merge();
header(stats.getRange("A20:D20"));
stats.getRange("A21:D25").values = [
  ["日期口径", "使用订单日期，不以具体时分秒作为分组条件。", null, null],
  ["公司口径", "普通发票取销售方/销货方名称；统一规范空格和括号后归组。", null, null],
  ["铁路票口径", "票面不展示具体销售方法人名称，统一按“中国铁路（铁路电子客票）”业务类别归组。", null, null],
  ["金额口径", "同一报销编号、同一日期、同一公司只累计一次，避免多附件重复计数。", null, null],
  ["阈值口径", "大于 1000 元为超额；等于 1000 元允许。", null, null],
];
for (let row = 21; row <= 25; row += 1) stats.getRange(`B${row}:D${row}`).merge();
stats.getRange("A21:D25").format = { wrapText: true, verticalAlignment: "top", borders: { insideHorizontal: { style: "thin", color: colors.line } } };
stats.getRange("A21:A25").format.font = { bold: true, color: colors.navy };
stats.getRange("C:D").format.columnWidth = 14;

const check = await workbook.inspect({ kind: "table", range: "单日同公司汇总!A1:H12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 8 });
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
console.log(check.ndjson);
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["单日同公司汇总", "发票识别明细", "待人工复核", "运行统计"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewDir, groups: groups.length, reviews: reviews.length }));
