import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("manual invoice form requires and sends issue date but leaves status to the backend", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const payloadMatch = pageSource.match(/await handleCreateManualInvoice\(\{([\s\S]*?)\n\s*\}\);/);

  assert.ok(payloadMatch, "manual invoice payload should be present");
  assert.match(payloadMatch[1], /issue_date:\s*manualForm\.issue_date/);
  assert.doesNotMatch(payloadMatch[1], /\bstatus\s*:/);
  assert.match(pageSource, /issue_date:\s*""/);
  assert.match(pageSource, /if \(!manualForm\.issue_date\.trim\(\)\)\s*\{\s*setManualError\("Inserisci una data fattura valida con anno a quattro cifre\."\)/);
  assert.match(pageSource, /className="invoice-manual-field">\s*Data fattura\s*<input\s+type="date"\s+required/);
  assert.match(pageSource, /className="invoice-manual-field">\s*Data scadenza\s*<input\s+type="date"\s+required/);
  assert.match(pageSource, /Totale fattura \(IVA inclusa\)/);
  assert.match(pageSource, /di cui IVA/);
  assert.doesNotMatch(pageSource, /(?:Fornitore|Numero fattura|Data fattura|Data scadenza|Categoria|Totale fattura \(IVA inclusa\)|di cui IVA) \*/);
  assert.match(pageSource, /validateInvoiceAmounts\(manualForm\.total, manualForm\.vat\)/);
  assert.match(pageSource, /validateInvoiceDates\(manualForm\.issue_date, manualForm\.due_date\)/);
  assert.match(pageSource, /extractApiErrorMessage\(err\?\.message\)/);
  assert.match(pageSource, /setMonth\?\.\(manualForm\.due_date\.slice\(0, 7\)\)/);
  assert.match(pageSource, /setStatusFilter\("all"\)[\s\S]*setCategoryFilter\(""\)[\s\S]*setSupplierSearch\(""\)/);
});

test("dashboard export and monthly invoice views use the same due-month scope", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /const currentMonthInvoices = safeArray\(invoices\)\s*\.filter\(\(invoice\) => isInvoiceInDueMonth\(invoice, month\)\)/);
  assert.match(appSource, /const invoiceMonth = invoiceData\.due_date\.slice\(0, 7\)/);
});

test("invoice preview keeps the eye action and shows the documentless manual-invoice message", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");
  const previewStart = pageSource.indexOf('className="invoice-preview-empty"');
  const previewEnd = pageSource.indexOf("</div>", previewStart);
  const documentlessPreview = pageSource.slice(previewStart, previewEnd);

  assert.match(pageSource, /onClick=\{\(\) => setSelectedInvoice\(invoice\)\}/);
  assert.ok(previewStart >= 0 && previewEnd > previewStart);
  assert.match(documentlessPreview, /<h3>Documento non disponibile<\/h3>/);
  assert.match(
    documentlessPreview,
    /Questa fattura è stata inserita manualmente e non ha un file associato\./
  );
  assert.doesNotMatch(documentlessPreview, /🧾|📄/);
  assert.match(cssSource, /\.invoice-preview-modal\.only-document \.invoice-preview-empty\s*\{[\s\S]*?background:\s*#fff/);
  assert.match(pageSource, /className="invoice-preview-floating-close"[\s\S]*?onClick=\{closeInvoicePreview\}/);
});

test("manual invoice dialog has primary and secondary actions and resets active filters on save", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");

  assert.match(pageSource, /className="invoice-manual-cancel"/);
  assert.match(pageSource, /className="invoice-manual-submit"/);
  assert.match(cssSource, /\.invoice-manual-actions \.invoice-manual-cancel\s*\{/);
  assert.match(cssSource, /\.invoice-manual-actions \.invoice-manual-submit\s*\{[\s\S]*?background:\s*var\(--crema\)/);
  assert.match(pageSource, /setStatusFilter\("all"\)[\s\S]*setCategoryFilter\(""\)[\s\S]*setSupplierSearch\(""\)/);
});