import assert from "node:assert/strict";
import test from "node:test";

import {
  UploadApiError,
  buildUploadError,
  extractApiErrorMessage,
  toUploadError,
  uploadErrorFromResponse,
} from "../src/apiErrors.js";

const DUPLICATE_DETAIL =
  "Questa chiusura cassa è già stata caricata (07/10/2026 – chiusura n. 123 – 1.234,50 €).";

function fakeResponse(status, body) {
  return {
    status,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

test("extractApiErrorMessage reads a string detail", () => {
  assert.equal(extractApiErrorMessage({ detail: DUPLICATE_DETAIL }), DUPLICATE_DETAIL);
  assert.equal(
    extractApiErrorMessage(JSON.stringify({ detail: DUPLICATE_DETAIL })),
    DUPLICATE_DETAIL
  );
});

test("extractApiErrorMessage formats FastAPI validation detail arrays", () => {
  const body = JSON.stringify({
    detail: [
      { loc: ["body", "month"], msg: "Field required", type: "missing" },
      { loc: ["body", "file"], msg: "Invalid file", type: "value_error" },
      { msg: "Senza posizione" },
    ],
  });

  assert.equal(
    extractApiErrorMessage(body),
    "month: Field required\nInvalid file\nSenza posizione"
  );
});

test("extractApiErrorMessage reads object detail", () => {
  assert.equal(
    extractApiErrorMessage({ detail: { message: "Data di emissione mancante." } }),
    "Data di emissione mancante."
  );
  assert.equal(extractApiErrorMessage({ detail: { code: 42 } }), "");
});

test("extractApiErrorMessage handles non JSON, HTML, empty and missing bodies", () => {
  assert.equal(extractApiErrorMessage("Bad gateway"), "Bad gateway");
  assert.equal(extractApiErrorMessage("<html><body>502</body></html>"), "");
  assert.equal(extractApiErrorMessage(""), "");
  assert.equal(extractApiErrorMessage("   "), "");
  assert.equal(extractApiErrorMessage(null), "");
  assert.equal(extractApiErrorMessage(undefined), "");
  assert.equal(extractApiErrorMessage("{}"), "");
});

test("409 keeps the original backend detail under the duplicate title", () => {
  const error = buildUploadError({ status: 409, detail: DUPLICATE_DETAIL });

  assert.equal(error.title, "Documento già presente");
  assert.equal(error.message, DUPLICATE_DETAIL);
  assert.equal(error.variant, "error");
});

test("409 without detail uses a readable fallback", () => {
  const error = buildUploadError({ status: 409, detail: "" });

  assert.equal(error.title, "Documento già presente");
  assert.ok(error.message.length > 0);
});

test("422 shows the backend detail for missing date and closure number", () => {
  for (const detail of [
    "Data della chiusura non rilevata o non valida. Carica un'immagine o un PDF più leggibile.",
    "Numero di chiusura non rilevato. Carica un'immagine o un PDF più leggibile.",
  ]) {
    const error = buildUploadError({ status: 422, detail });

    assert.equal(error.title, "Dati non validi");
    assert.equal(error.message, detail);
    assert.equal(error.variant, "error");
  }
});

test("422 with a FastAPI detail array is rendered through the response parser", async () => {
  const error = await uploadErrorFromResponse(
    fakeResponse(422, { detail: [{ loc: ["body", "month"], msg: "Field required" }] })
  );

  assert.equal(error.title, "Dati non validi");
  assert.equal(error.message, "month: Field required");
});

test("500 hides technical details and gives an understandable message", async () => {
  const error = await uploadErrorFromResponse(
    fakeResponse(500, { detail: "invoice extraction failed: Traceback (most recent call last)" })
  );

  assert.equal(error.title, "Errore del server");
  assert.doesNotMatch(error.message, /Traceback|extraction failed/);
  assert.match(error.message, /riprova/i);
});

test("500 with a non JSON body is handled", async () => {
  const error = await uploadErrorFromResponse(fakeResponse(500, "Internal Server Error"));

  assert.equal(error.title, "Errore del server");
  assert.doesNotMatch(error.message, /Internal Server Error/);
});

test("409 response is parsed end to end", async () => {
  const error = await uploadErrorFromResponse(fakeResponse(409, { detail: DUPLICATE_DETAIL }));

  assert.equal(error.title, "Documento già presente");
  assert.equal(error.message, DUPLICATE_DETAIL);
});

test("unreadable response body falls back to the status message", async () => {
  const error = await uploadErrorFromResponse({
    status: 400,
    text: async () => {
      throw new Error("stream failed");
    },
  });

  assert.equal(error.title, "Caricamento non riuscito");
  assert.match(error.message, /400/);
});

test("network errors produce a connection message", () => {
  const error = toUploadError(new TypeError("Failed to fetch"));

  assert.equal(error.title, "Connessione non riuscita");
  assert.doesNotMatch(error.message, /Failed to fetch/);
});

test("UploadApiError carries the prepared upload error", () => {
  const prepared = buildUploadError({ status: 409, detail: DUPLICATE_DETAIL });

  assert.deepEqual(toUploadError(new UploadApiError(prepared)), prepared);
});

test("unknown errors produce a generic message", () => {
  const error = toUploadError(new Error("boom"));

  assert.equal(error.title, "Caricamento non riuscito");
  assert.doesNotMatch(error.message, /boom/);
});
