import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCashClosureCorrections,
  createCashClosureReviewForm,
} from "../src/cashClosureReview.js";

test("review form keeps missing amounts blank and explicit zeros as zero", () => {
  const form = createCashClosureReviewForm({
    date: null,
    closure_number: null,
    total_amount: "0.00",
    cash_amount: null,
    card_amount: "0.00",
  });

  assert.equal(form.date, "");
  assert.equal(form.total_amount, "0.00");
  assert.equal(form.cash_amount, "");
  assert.equal(form.card_amount, "0.00");
});

test("only changed review fields are submitted and blank corrections become null", () => {
  const review = {
    date: "2026-11-03",
    closure_number: "5",
    total_amount: null,
    cash_amount: null,
    card_amount: "0.00",
  };
  const form = {
    ...createCashClosureReviewForm(review),
    total_amount: "200.00",
    card_amount: "",
  };

  assert.deepEqual(buildCashClosureCorrections(review, form), {
    total_amount: "200.00",
    card_amount: null,
  });
});
