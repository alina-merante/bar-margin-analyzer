import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const invoicesSource = await readFile(
  new URL("../src/pages/InvoicesPage.jsx", import.meta.url),
  "utf8"
);
const uploadSource = await readFile(
  new URL("../src/pages/UploadPage.jsx", import.meta.url),
  "utf8"
);
const styles = await readFile(new URL("../src/App.css", import.meta.url), "utf8");

test("invoice preview closes outside or on Escape without consuming other actions", () => {
  const start = invoicesSource.indexOf("function handlePreviewPointerDown(event)");
  const end = invoicesSource.indexOf("}, [selectedInvoice]);", start);
  const dismissalEffect = invoicesSource.slice(start, end);

  assert.ok(start >= 0 && end > start);
  assert.match(dismissalEffect, /invoicePreviewRef\.current\?\.contains\(event\.target\)/);
  assert.match(dismissalEffect, /setSelectedInvoice\(null\)/);
  assert.match(dismissalEffect, /event\.key === "Escape"/);
  assert.match(dismissalEffect, /addEventListener\("pointerdown"/);
  assert.doesNotMatch(dismissalEffect, /preventDefault|stopPropagation/);
  assert.match(
    invoicesSource,
    /\}, \[statusFilter, categoryFilter, supplierSearch, isYearView, searchParams\]\);/
  );
});

test("upload previews close outside, on Escape, and when the history tab changes", () => {
  const start = uploadSource.indexOf("function handlePreviewPointerDown(event)");
  const end = uploadSource.indexOf(
    "}, [selectedOtherDocument, selectedInvoiceWithoutDocument]);",
    start
  );
  const dismissalEffect = uploadSource.slice(start, end);

  assert.ok(start >= 0 && end > start);
  assert.match(dismissalEffect, /documentPreviewRef\.current\?\.contains\(event\.target\)/);
  assert.match(dismissalEffect, /setSelectedOtherDocument\(null\)/);
  assert.match(dismissalEffect, /setSelectedInvoiceWithoutDocument\(null\)/);
  assert.match(dismissalEffect, /event\.key === "Escape"/);
  assert.doesNotMatch(dismissalEffect, /preventDefault|stopPropagation/);
  assert.match(uploadSource, /}, \[activeHistoryTab\]\);/);
});

test("preview overlay allows first-click actions while keeping modal controls interactive", () => {
  assert.match(styles, /\.invoice-preview-backdrop\s*\{[^}]*pointer-events:\s*none/s);
  assert.match(
    styles,
    /\.invoice-preview-backdrop > \.invoice-preview-modal,[\s\S]*?pointer-events:\s*auto/
  );
  assert.match(
    invoicesSource,
    /className="invoice-preview-floating-close"[\s\S]*?onClick=\{closeInvoicePreview\}/
  );
  assert.match(
    uploadSource,
    /className="invoice-preview-floating-close"[\s\S]*?onClick=\{\(\) => setSelectedOtherDocument\(null\)\}/
  );
});

test("destructive document confirmation remains independent from preview dismissal", () => {
  const confirmationStart = uploadSource.indexOf("{documentToDelete ? (");
  const backdropStart = uploadSource.indexOf(
    '<div className="document-delete-confirm-backdrop">',
    confirmationStart
  );
  const sectionStart = uploadSource.indexOf("<section", backdropStart);
  const confirmation = uploadSource.slice(backdropStart, sectionStart);

  assert.ok(confirmationStart >= 0 && sectionStart > backdropStart);
  assert.match(confirmation, /className="document-delete-confirm-backdrop"/);
  assert.doesNotMatch(confirmation, /onMouseDown|onPointerDown|onClick=/);
  assert.match(uploadSource, /onClick=\{confirmDeleteDocument\}/);
  assert.match(uploadSource, /Elimina definitivamente/);
});
