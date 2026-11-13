import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCashClosureCorrections,
  cashClosureWarnings,
  createLatestDocumentLoader,
  createCashClosureReviewForm,
  reprocessCashClosure,
  updateCashClosureList,
  validateCashClosurePayments,
} from "../src/cashClosureReview.js";

test("mutation updates or removes only the review with the matching intake id", () => {
  const first = { id: 1, status: "pending", receipts_total: null };
  const second = { id: 2, status: "pending", receipts_total: "40.00" };
  const saved = { id: 1, status: "pending", receipts_total: "303.50" };
  assert.deepEqual(updateCashClosureList([first, second], saved), [saved, second]);
  assert.deepEqual(updateCashClosureList([saved, second], { id: 1, status: "approved" }), [second]);
});

test("late older document responses cannot replace a newer review", async () => {
  const waiting = [];
  const applied = [];
  const loader = createLatestDocumentLoader(
    (url) => new Promise((resolve) => waiting.push({ url, resolve })),
    (_documents, reviews) => applied.push(reviews),
    () => assert.fail("unexpected error"),
  );
  const old = loader.load("2023-09");
  const fresh = loader.load("2023-09");
  waiting[2].resolve([]);
  waiting[3].resolve([{ id: 1, receipts_total: "303.50" }]);
  await fresh;
  waiting[0].resolve([]);
  waiting[1].resolve([{ id: 1, receipts_total: null }]);
  await old;
  assert.deepEqual(applied, [[{ id: 1, receipts_total: "303.50" }]]);
});

test("mutation invalidation prevents an earlier pending refresh from applying", async () => {
  const waiting = [];
  const applied = [];
  const loader = createLatestDocumentLoader(
    () => new Promise((resolve) => waiting.push(resolve)),
    (...data) => applied.push(data),
    () => assert.fail("unexpected error"),
  );
  const pending = loader.load("2023-09");
  loader.invalidate();
  waiting.forEach((resolve) => resolve([]));
  await pending;
  assert.deepEqual(applied, []);
});

test("only the latest load reports an error", async () => {
  const pending = [];
  const errors = [];
  const loader = createLatestDocumentLoader(
    () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
    () => {},
    (error) => errors.push(error.message),
  );
  const old = loader.load("2023-09");
  const fresh = loader.load("2023-09");
  pending[0].reject(new Error("old"));
  await old;
  assert.deepEqual(errors, []);
  pending[2].reject(new Error("current"));
  await assert.rejects(fresh, /current/);
  assert.deepEqual(errors, ["current"]);
});

test("reprocess requests preview without updating the list and refreshes only after confirmation", async () => {
  const calls = [];
  let refreshes = 0;
  const preview = { review_version: "old", extraction_version: "new", proposed: {} };
  const fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => calls.length === 1 ? preview : { status: "pending" } };
  };
  const refresh = async () => { refreshes += 1; };
  assert.deepEqual(await reprocessCashClosure(fetch, 7, null, refresh), preview);
  assert.equal(refreshes, 0);
  assert.equal(calls[0].url, "/api/cash-closures/review/7/reprocess/preview");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(await reprocessCashClosure(fetch, 7, preview, refresh), { status: "pending" });
  assert.equal(calls[1].url, "/api/cash-closures/review/7/reprocess");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    review_version: "old", extraction_version: "new",
  });
  assert.equal(refreshes, 1);
});

test("reprocess errors do not refresh and distinguish a saved result from refresh failure", async () => {
  const preview = { review_version: "old", extraction_version: "new" };
  let refreshes = 0;
  const refresh = async () => { refreshes += 1; };
  await assert.rejects(reprocessCashClosure(
    async () => ({ ok: false, status: 409, json: async () => ({ detail: "La scheda è cambiata. Ripeti la rielaborazione." }) }),
    7, preview, refresh,
  ), /La scheda è cambiata/);
  assert.equal(refreshes, 0);
  await assert.rejects(reprocessCashClosure(
    async () => ({ ok: true, json: async () => ({}) }),
    7, preview, async () => { throw new Error("offline"); },
  ), /Rielaborazione salvata.*Ricarica la pagina/);
  await assert.rejects(reprocessCashClosure(
    async () => { throw new TypeError("Failed to fetch"); },
    7, null, refresh,
  ), /Impossibile contattare il server/);
});

test("OCR warnings are translated without exposing internal codes", () => {
  const warnings = cashClosureWarnings({
    anomalies: ["total_amount:missing", "payments:total_mismatch", "new:unknown"],
    ocr_values: { diagnostics: { fields: {
      closure_number: { status: "missing" },
      cash_amount: { status: "conflict" },
    } } },
  });
  assert.ok(warnings.includes("Totale complessivo: non rilevato."));
  assert.ok(warnings.includes("Numero chiusura: non rilevato."));
  assert.ok(warnings.includes("Contanti: valori discordanti."));
  assert.ok(warnings.includes("I pagamenti rilevati non coincidono con il totale."));
  assert.ok(warnings.every((warning) => !warning.includes("_")));
});

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

test("receipt count can be confirmed, corrected or cleared without inventing zero", () => {
  const review = { receipts_count: 25 };
  const form = createCashClosureReviewForm(review);
  assert.equal(form.receipts_count, "25");
  assert.deepEqual(buildCashClosureCorrections(review, form), {});
  assert.deepEqual(buildCashClosureCorrections(review, { ...form, receipts_count: "24" }), {
    receipts_count: "24",
  });
  assert.deepEqual(buildCashClosureCorrections(review, { ...form, receipts_count: "" }), {
    receipts_count: null,
  });
  assert.equal(createCashClosureReviewForm({ receipts_count: null }).receipts_count, "");
});

test("payment validation allows an exact breakdown", () => {
  assert.deepEqual(validateCashClosurePayments("200.00", "80.00", "120.00"), {
    exceedsTotal: false,
    incomplete: false,
    unallocatedCents: null,
  });
});

test("payment validation blocks a breakdown above the total", () => {
  assert.deepEqual(validateCashClosurePayments("200.00", "100.01", "100.00"), {
    exceedsTotal: true,
    incomplete: false,
    unallocatedCents: null,
  });
});

test("payment validation reports a lower breakdown as unallocated", () => {
  assert.deepEqual(validateCashClosurePayments("200.00", "75.00", "100.00"), {
    exceedsTotal: false,
    incomplete: false,
    unallocatedCents: 2500,
  });
});

test("missing amounts remain incomplete and are not treated as zero", () => {
  assert.deepEqual(validateCashClosurePayments("200.00", "", "100.00"), {
    exceedsTotal: false,
    incomplete: true,
    unallocatedCents: null,
  });
});

test("explicit zero amounts are included in the breakdown", () => {
  assert.deepEqual(validateCashClosurePayments("200.00", "0.00", "0"), {
    exceedsTotal: false,
    incomplete: false,
    unallocatedCents: 20000,
  });
});
