import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("invoice extraction displays the explicit missing issue date message", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /const detail = errorPayload\?\.detail;/);
  assert.match(appSource, /detail\?\.message \|\| `Upload fattura fallito/);
  assert.match(appSource, /setInvoiceUploadError\(\s*err\.message \|\|/);
});