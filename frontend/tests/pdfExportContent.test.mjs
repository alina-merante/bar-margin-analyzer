import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildPdfInsightItems,
  calculatePdfMetricChanges,
  calculatePdfMarginPercent,
  formatPdfMetricTag,
  formatPendingInvoicesLabel,
  getPdfMarginBarTone,
  getPdfMarginBarWidth,
  hasPdfMonthData,
  localizePdfCategoryLabel,
  translateInsightToItalian,
} from "../src/pdfExportContent.js";

test("July with zero-valued previous month does not invent a percentage", () => {
  const current = { revenue: 2070, expenses: 920, profit: 1150 };
  const previous = { revenue: 0, expenses: 0, profit: 0 };
  const metricChanges = calculatePdfMetricChanges(current, previous);
  const hasMonthlyData = hasPdfMonthData(current, 2);
  const items = buildPdfInsightItems({
    apiInsights: [
      "Revenue increased by 100.0% vs previous month.",
      "Expenses increased by 100.0% vs previous month.",
      "Profit increased by 100.0% vs previous month.",
    ],
    metricChanges,
    hasMonthlyData,
  });

  assert.deepEqual(metricChanges, { revenue: null, expenses: null, profit: null });
  assert.deepEqual(items.map(({ text }) => text), [
    "Confronto non disponibile: il mese precedente non presenta valori registrati.",
  ]);
  assert.equal(
    formatPdfMetricTag(metricChanges.revenue, { hasMonthlyData }).text,
    "Confronto col mese precedente non disponibile"
  );
});

test("cards and insights use the same defined monthly variation", () => {
  const metricChanges = calculatePdfMetricChanges(
    { revenue: 2070, expenses: 920, profit: 1150 },
    { revenue: 1000, expenses: 460, profit: 575 }
  );
  const items = buildPdfInsightItems({ metricChanges, hasMonthlyData: true });

  assert.deepEqual(items.map(({ text }) => text), [
    "I ricavi sono aumentati del 107,0% rispetto al mese precedente.",
    "I costi sono aumentati del 100,0% rispetto al mese precedente.",
    "Il margine netto è aumentato del 100,0% rispetto al mese precedente.",
  ]);
  assert.equal(formatPdfMetricTag(metricChanges.revenue).text, "↑ 107,0%");
  assert.equal(formatPdfMetricTag(metricChanges.expenses, { inverse: true }).text, "↑ 100,0%");
});

test("PDF margin percentage is signed and its bar width stays valid", () => {
  const positiveMargin = calculatePdfMarginPercent(1150, 2070);
  const negativeMargin = calculatePdfMarginPercent(-50, 250);

  assert.equal(Math.round(positiveMargin), 56);
  assert.equal(negativeMargin, -20);
  assert.equal(getPdfMarginBarWidth(positiveMargin), positiveMargin);
  assert.equal(getPdfMarginBarWidth(negativeMargin), 20);
  assert.equal(getPdfMarginBarWidth(-180), 100);
  assert.equal(getPdfMarginBarTone(negativeMargin), "negative");
  assert.equal(getPdfMarginBarTone(positiveMargin), "positive");
  assert.equal(getPdfMarginBarTone(0), "neutral");
  assert.equal(calculatePdfMarginPercent(0, 0), 0);
});

test("summary card copy keeps the signed margin, shared comparison, and no duplicate counts", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /\$\{marginPercent\.toFixed\(0\)\}% dei ricavi/);
  assert.match(appSource, /<div class="kpi-box-sub">\$\{marginPercent\.toFixed\(0\)\}% dei ricavi<\/div>\s*<div class="m-wrap">/);
  assert.match(appSource, /class="m-fill \$\{marginBarTone\}" style="width:\$\{getPdfMarginBarWidth\(marginPercent\)\.toFixed\(1\)\}%"/);
  assert.match(appSource, /\.m-fill \{\s+position: absolute;\s+left: 0;/);
  assert.match(appSource, /\.m-fill\.negative \{ background: var\(--red\); \}/);
  assert.match(appSource, /\.m-fill\.positive \{ background: var\(--green\); \}/);
  assert.doesNotMatch(appSource, /m-axis|m-zero|-100%|\+100%/);
    assert.equal((appSource.match(/kpi-box-sub">\$\{escapeHtml\((?:revenue|expenses)ChangeTag\.text\)\}<\/div>/g) || []).length, 2);
  assert.equal((appSource.match(/Confronto col mese precedente non disponibile/g) || []).length, 1);
  assert.doesNotMatch(appSource, /prodotti più venduti/);
  assert.doesNotMatch(appSource, /currentMonthInvoices\.length\} fatture/);
  assert.match(appSource, /formatPendingInvoicesLabel\(pendingInvoices\.length\)/);
  assert.doesNotMatch(appSource, /class="m-labels"/);
});

test("August with no revenue, costs, or invoices gets one informational message", () => {
  const apiInsights = [
    "Revenue decreased by -100.0% vs previous month.",
    "Expenses decreased by -100.0% vs previous month.",
    "Profit decreased by -100.0% vs previous month.",
  ];
  const hasMonthlyData = hasPdfMonthData({ revenue: 0, expenses: 0 }, 0);
  const metricChanges = calculatePdfMetricChanges(
    { revenue: 0, expenses: 0, profit: 0 },
    { revenue: 2070, expenses: 920, profit: 1150 }
  );
  const items = buildPdfInsightItems({ apiInsights, metricChanges, hasMonthlyData });

  assert.equal(hasMonthlyData, false);
  assert.deepEqual(items, [{
    tone: "info",
    icon: "ℹ️",
    title: "Informazione",
    text: "Nessun dato registrato per il mese selezionato.",
  }]);
  assert.equal(
    formatPdfMetricTag(metricChanges.revenue, { hasMonthlyData }).text,
    "Confronto col mese precedente non disponibile"
  );
});

test("renders a neutral fallback instead of leaking unsupported English", () => {
  assert.equal(
    translateInsightToItalian("Unexpected English insight"),
    "Approfondimento non disponibile."
  );
});

test("localizes known English expense category names", () => {
  assert.equal(localizePdfCategoryLabel("Uncategorized"), "Senza categoria");
  assert.equal(
    translateInsightToItalian("Top expense category 'Utilities' increased by 12.5% vs previous month."),
    "La categoria di costo principale \"Utenze\" è aumentata del 12,5% rispetto al mese precedente."
  );
});

test("localizes the supplier-share insight", () => {
  assert.equal(
    translateInsightToItalian("Top supplier 'Fornitore Uno' represents 80.0% of total expenses."),
    "Il fornitore principale \"Fornitore Uno\" rappresenta l'80,0% dei costi totali."
  );
});

test("DA PAGARE uses a natural zero label and keeps singular/plural counts", () => {
  assert.equal(formatPendingInvoicesLabel(0), "✓ Nessuna fattura da pagare");
  assert.equal(formatPendingInvoicesLabel(1), "⚠ 1 fattura in sospeso");
  assert.equal(formatPendingInvoicesLabel(3), "⚠ 3 fatture in sospeso");
});

test("print stylesheet uses the full A4 page and trims vertical whitespace only", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /@page\s*\{\s*size:\s*A4 portrait;\s*margin:\s*0;\s*\}/);
  assert.match(appSource, /\.a4 \{ box-shadow: none; border-radius: 0; width: 210mm; margin: 0 auto; \}/);
  assert.match(appSource, /\.a4,\s*\.a4 \* \{\s*-webkit-print-color-adjust: exact;\s*print-color-adjust: exact;/);
  assert.match(appSource, /\.bm-bar\.r \{ background: var\(--crema\); \}/);
  assert.match(appSource, /\.doc-body \{ padding: 24px 40px; \}/);
  assert.match(appSource, /\.ftbl td \{ padding-top: 6px; padding-bottom: 6px; \}/);
});