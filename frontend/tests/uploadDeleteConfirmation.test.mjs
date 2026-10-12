import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("document history opens a confirmation without calling the delete handler", async () => {
  const pageSource = await readFile(new URL("../src/pages/UploadPage.jsx", import.meta.url), "utf8");
  const start = pageSource.indexOf("async function deleteHistoryEntry(entry)");
  const end = pageSource.indexOf("async function confirmDeleteDocument()", start);
  const deleteHistoryEntry = pageSource.slice(start, end);

  assert.ok(start >= 0 && end > start);
  assert.match(deleteHistoryEntry, /setDocumentToDelete\(entry\.raw\)/);
  assert.doesNotMatch(deleteHistoryEntry, /handleDeleteDocument\s*\(/);
  assert.match(pageSource, /onClick=\{\(\) => setDocumentToDelete\(null\)\}/);
  assert.match(pageSource, /Annulla/);
  assert.match(pageSource, /Elimina definitivamente/);
  assert.match(pageSource, /documentToDelete\.original_filename/);
});

test("document deletion is called only by explicit confirmation and reports API failures", async () => {
  const pageSource = await readFile(new URL("../src/pages/UploadPage.jsx", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const start = pageSource.indexOf("async function confirmDeleteDocument()");
  const end = pageSource.indexOf("\n}\n", start);
  const confirmHandler = pageSource.slice(start, end);
  const deleteHandlerStart = appSource.indexOf("async function handleDeleteDocument(documentId)");
  const deleteHandlerEnd = appSource.indexOf("\n}\n", deleteHandlerStart);
  const deleteHandler = appSource.slice(deleteHandlerStart, deleteHandlerEnd);

  assert.ok(start >= 0 && end > start);
  assert.match(confirmHandler, /await handleDeleteDocument\(documentToDelete\.id\)/);
  assert.match(confirmHandler, /if \(deleted\) setDocumentToDelete\(null\)/);
  assert.match(deleteHandler, /method:\s*"DELETE"/);
  assert.match(deleteHandler, /if \(!response\.ok\)/);
  assert.match(deleteHandler, /setDocumentDeleteError\("Errore durante l'eliminazione del documento\."\)/);
  assert.match(deleteHandler, /Promise\.all\(\[loadDocuments\(\), loadDashboardData\(month\)\]\)/);
  assert.match(deleteHandler, /return false/);
});
