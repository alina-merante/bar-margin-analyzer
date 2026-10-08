import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildUploadError, extractApiErrorMessage } from "../src/apiErrors.js";

test("invoice extraction displays the explicit missing issue date message", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /throw new UploadApiError\(await uploadErrorFromResponse\(response\)\)/);
  assert.match(appSource, /setInvoiceUploadError\(toUploadError\(err\)\)/);

  const detail = "Data di emissione della fattura non rilevata.";
  const error = buildUploadError({
    status: 422,
    detail: extractApiErrorMessage({ detail: { message: detail } }),
  });

  assert.equal(error.message, detail);
});