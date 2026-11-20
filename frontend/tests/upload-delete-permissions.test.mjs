import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(
  new URL("../src/pages/UploadPage.jsx", import.meta.url),
  "utf8"
);

const start = source.indexOf("  const canDeleteHistoryEntry = (entry) => {");
const end = source.indexOf("\n  const [activeHistoryTab", start);

assert.ok(start !== -1 && end !== -1, "Funzione permessi non trovata");

const functionSource = source.slice(start, end);

function canDelete({ isOwner = false, permissions = [], invoiceHandler = true, documentHandler = true }, entry) {
  const context = {
    isOwner,
    permissions: new Set(permissions),
    handleDeleteInvoice: invoiceHandler ? () => {} : null,
    handleDeleteDocument: documentHandler ? () => {} : null,
  };

  return vm.runInNewContext(
    `
      const hasPermission = (permission) =>
        isOwner || permissions.has(permission);
      ${functionSource}
      canDeleteHistoryEntry(entry);
    `,
    { ...context, entry }
  );
}

const invoice = { kind: "invoice", raw: { id: 1 } };
const document = { kind: "document", raw: { section: "other" } };
const bank = { kind: "document", raw: { section: "bank" } };
const cash = { kind: "document", raw: { section: "cash" } };
const closure = { kind: "document", raw: { section: "cash_closure" } };

test("dipendente senza permessi: nessuna eliminazione", () => {
  for (const entry of [invoice, document, bank, cash, closure]) {
    assert.equal(canDelete({}, entry), false);
  }
});

test("documents.delete: soltanto documenti generici e bancari", () => {
  const user = { permissions: ["documents.delete"] };
  assert.equal(canDelete(user, document), true);
  assert.equal(canDelete(user, bank), true);
  assert.equal(canDelete(user, invoice), false);
  assert.equal(canDelete(user, cash), false);
  assert.equal(canDelete(user, closure), false);
});

test("cash_closures.delete: soltanto documenti di cassa", () => {
  const user = { permissions: ["cash_closures.delete"] };
  assert.equal(canDelete(user, cash), true);
  assert.equal(canDelete(user, closure), true);
  assert.equal(canDelete(user, document), false);
  assert.equal(canDelete(user, invoice), false);
});

test("invoices.delete: soltanto fatture", () => {
  const user = { permissions: ["invoices.delete"] };
  assert.equal(canDelete(user, invoice), true);
  assert.equal(canDelete(user, document), false);
  assert.equal(canDelete(user, cash), false);
});

test("proprietario: tutti i permessi di eliminazione", () => {
  for (const entry of [invoice, document, bank, cash, closure]) {
    assert.equal(canDelete({ isOwner: true }, entry), true);
  }
});

test("handler assente: eliminazione non disponibile", () => {
  assert.equal(canDelete({ isOwner: true, invoiceHandler: false }, invoice), false);
  assert.equal(canDelete({ isOwner: true, documentHandler: false }, document), false);
});
