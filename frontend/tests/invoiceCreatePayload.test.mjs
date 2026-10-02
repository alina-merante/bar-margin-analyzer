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
  assert.match(pageSource, /if \(!manualForm\.issue_date\.trim\(\)\)\s*\{\s*setManualError\("Inserisci la data della fattura\."\)/);
  assert.match(pageSource, /className="invoice-manual-date-field">\s*Data fattura\s*<input\s+type="date"\s+required/);
});