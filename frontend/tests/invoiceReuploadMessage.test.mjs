import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("protected re-upload explains that linked invoice data was not changed", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(
    appSource,
    /if \(result\.has_payment_links && result\.update_applied === false\)\s*\{\s*setInvoiceUploadMessage\(\s*"Fattura già presente e associata a uno o più pagamenti\. I dati esistenti non sono stati modificati\."\s*\);/
  );
  assert.match(appSource, /setInvoiceUploadMessage\("Fattura acquisita correttamente\."\)/);
});