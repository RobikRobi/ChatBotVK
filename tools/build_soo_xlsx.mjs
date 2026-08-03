import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const inputPath = path.join(root, "tmp", "pdfs", "soo_table.json");
const outputDir = path.join(root, "outputs", "soo_pdf_conversion");
const outputPath = path.join(outputDir, "soo_schedule.xlsx");
const previewPath = path.join(outputDir, "soo_schedule_preview.png");

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rawRows = payload.rows;
const rows = rawRows.map((row) => row.map((cell) => (cell == null ? "" : String(cell))));
const dayNames = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"];
const headerRows = rows
  .map((row, index) => (row[1] === "Звонки" ? index : -1))
  .filter((index) => index >= 0);

const dayBlocks = headerRows.map((headerRow, index) => {
  const start = headerRow + 1;
  const end = (headerRows[index + 1] ?? rows.length) - 1;
  return { name: dayNames[index] ?? `День ${index + 1}`, start, end };
});

for (const block of dayBlocks) {
  for (let row = block.start; row <= block.end; row += 1) {
    rows[row][0] = row === block.start ? block.name : "";
  }
}

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Расписание");
sheet.showGridLines = false;

const rowCount = rows.length;
const colCount = rows[0].length;
const usedRange = sheet.getRangeByIndexes(0, 0, rowCount, colCount);
usedRange.values = rows;

sheet.getRangeByIndexes(0, 0, 1, colCount).merge();
sheet.getRangeByIndexes(0, 0, 1, colCount).format = {
  fill: "#1F4E79",
  font: { bold: true, color: "#FFFFFF", size: 14 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A1").format.rowHeight = 34;

sheet.getRangeByIndexes(1, 0, 1, colCount).format = {
  fill: "#D9EAF7",
  font: { bold: true, color: "#17365D" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#9EADBA" },
};

const body = sheet.getRangeByIndexes(2, 0, rowCount - 2, colCount);
body.format = {
  font: { size: 10 },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#D6DEE6" },
};

sheet.getRangeByIndexes(0, 0, rowCount, 1).format = {
  fill: "#F4F7FB",
  font: { bold: true, color: "#17365D" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#C6D3DF" },
};
for (const block of dayBlocks) {
  const dayRange = sheet.getRangeByIndexes(block.start, 0, block.end - block.start + 1, 1);
  dayRange.merge();
  dayRange.format = {
    fill: "#EAF2F8",
    font: { bold: true, color: "#17365D" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#9EADBA" },
  };
}
sheet.getRangeByIndexes(0, 1, rowCount, 1).format = {
  fill: "#F8FAFC",
  font: { bold: true, color: "#17365D" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#C6D3DF" },
};

sheet.getRangeByIndexes(0, 0, rowCount, 1).format.columnWidth = 8;
sheet.getRangeByIndexes(0, 1, rowCount, 1).format.columnWidth = 13;
sheet.getRangeByIndexes(0, 2, rowCount, colCount - 2).format.columnWidth = 18;
usedRange.format.autofitRows();

sheet.freezePanes.freezeRows(2);
sheet.freezePanes.freezeColumns(2);

await fs.mkdir(outputDir, { recursive: true });

const preview = await workbook.render({
  sheetName: "Расписание",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const inspected = await workbook.inspect({
  kind: "region",
  range: `Расписание!A1:${String.fromCharCode(64 + colCount)}${Math.min(rowCount, 10)}`,
  include: "values",
  tableMaxRows: 10,
  tableMaxCols: colCount,
  maxChars: 4000,
});
console.log(inspected.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`saved ${outputPath}`);
