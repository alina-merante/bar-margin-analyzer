import assert from "node:assert/strict";
import test from "node:test";

import { validateInvoiceAmounts, validateInvoiceDates } from "../src/invoiceValidation.js";

test("invoice amounts reject a VAT amount greater than the gross total", () => {
  assert.equal(
    validateInvoiceAmounts("100", "150"),
    "L'IVA non può essere superiore al totale della fattura."
  );
});

test("invoice amounts reject negative VAT and non-positive totals", () => {
  assert.equal(
    validateInvoiceAmounts("100", "-0.01"),
    "L'IVA non può essere negativa."
  );
  assert.equal(
    validateInvoiceAmounts("0", "0"),
    "Il totale della fattura deve essere maggiore di zero."
  );
  assert.equal(
    validateInvoiceAmounts("-1", "0"),
    "Il totale della fattura deve essere maggiore di zero."
  );
});

test("invoice amounts reject values that are not finite numbers", () => {
  const errorMessage = "Inserisci importi validi e finiti per totale e IVA.";

  assert.equal(validateInvoiceAmounts("NaN", "0"), errorMessage);
  assert.equal(validateInvoiceAmounts("Infinity", "0"), errorMessage);
  assert.equal(validateInvoiceAmounts("100", "Infinity"), errorMessage);
  assert.equal(validateInvoiceAmounts("abc", "10"), errorMessage);
});

test("invoice amounts accept valid gross totals including zero or equal VAT", () => {
  assert.equal(validateInvoiceAmounts("100", "0"), "");
  assert.equal(validateInvoiceAmounts("100", "20"), "");
  assert.equal(validateInvoiceAmounts("100", "100"), "");
});

test("invoice dates reject missing, malformed, impossible and six-digit-year values", () => {
  assert.match(validateInvoiceDates("", "2026-10-01"), /data fattura valida/i);
  assert.match(validateInvoiceDates("2026-10-01", ""), /data di scadenza valida/i);
  assert.match(validateInvoiceDates("120026-10-01", "120026-10-02"), /anno a quattro cifre/i);
  assert.match(validateInvoiceDates("2026-02-29", "2026-03-01"), /data fattura non è valida/i);
  assert.equal(validateInvoiceDates("2024-02-29", "2024-03-01"), "");
});

test("invoice dates reject an earlier due date and accept same-day valid dates", () => {
  assert.equal(
    validateInvoiceDates("2026-10-02", "2026-10-01"),
    "La data di scadenza non può precedere la data fattura."
  );
  assert.equal(validateInvoiceDates("2026-10-02", "2026-10-02"), "");
  assert.equal(validateInvoiceDates("0001-01-01", "0001-01-01"), "");
  assert.equal(validateInvoiceDates("9999-12-31", "9999-12-31"), "");
});
