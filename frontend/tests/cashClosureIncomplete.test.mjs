import test from "node:test";
import assert from "node:assert/strict";

import { createCashClosureReviewForm, hasMissingCashClosureRequiredFields } from "../src/cashClosureReview.js";

test("chiusura OCR incompleta richiede verifica", () => {
  const form = createCashClosureReviewForm({
    date: "2023-09-26",
    closure_number: null,
    total_amount: null,
    cash_amount: "255.50",
    card_amount: null,
    receipts_count: 25,
  });

  assert.equal(hasMissingCashClosureRequiredFields(form), true);
});

test("chiusura con campi obbligatori compilati non è incompleta", () => {
  const form = createCashClosureReviewForm({
    date: "2023-09-26",
    closure_number: "123",
    total_amount: "350.00",
    cash_amount: "200.00",
    card_amount: "150.00",
    receipts_count: 20,
  });

  assert.equal(hasMissingCashClosureRequiredFields(form), false);
});

test("totale zero esplicito è diverso da totale non rilevato", () => {
  const form = createCashClosureReviewForm({
    date: "2023-09-26",
    closure_number: "123",
    total_amount: "0.00",
    cash_amount: "0.00",
    card_amount: "0.00",
    receipts_count: 0,
  });

  assert.equal(hasMissingCashClosureRequiredFields(form), false);
});
