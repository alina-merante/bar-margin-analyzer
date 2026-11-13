import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let server;
let Card;
let UploadPage;
before(async () => {
  server = await createServer({
    root: new URL("..", import.meta.url).pathname,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  const module = await server.ssrLoadModule("/src/pages/UploadPage.jsx");
  Card = module.CashClosureReviewCard;
  UploadPage = module.default;
});
after(async () => { await server?.close(); });

const review = {
  id: 1, date: "2023-09-26", closure_number: "10", total_amount: null,
  cash_amount: "255.50", card_amount: null, receipts_count: 25,
  receipts_total: null, anomalies: [], ocr_values: {},
  created_at: "2026-11-13T14:41:51",
  document: { id: 9, original_filename: "report.png", file_url: "" },
};

function button(renderer, label) {
  return renderer.root.findAllByType("button").find((item) => item.children.includes(label));
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("unchanged refresh preserves in-progress edits and OCR comparison", async () => {
  let renderer;
  const preview = { previous: {}, proposed: {}, review_version: "v1", extraction_version: "v2" };
  const props = { review, onReprocess: async () => preview };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  const number = renderer.root.findAllByType("input")[1];
  await act(async () => { number.props.onChange({ target: { value: "manuale" } }); });
  await act(async () => { renderer.update(React.createElement(Card, { ...props, review: { ...review } })); });
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "manuale");
  await act(async () => { button(renderer, "Annulla modifiche").props.onClick(); });
  await act(async () => { await button(renderer, "Rielabora OCR").props.onClick(); });
  assert.ok(button(renderer, "Conferma rielaborazione"));
  await act(async () => { renderer.update(React.createElement(Card, { ...props, review: { ...review } })); });
  assert.ok(button(renderer, "Conferma rielaborazione"));
  await act(async () => { renderer.unmount(); });
});

test("confirmation keeps controls disabled while loading and displays saved OCR values", async () => {
  let renderer;
  const pending = deferred();
  const preview = { previous: {}, proposed: {}, review_version: "v1", extraction_version: "v2" };
  const saved = { ...review, closure_number: null, receipts_total: "303.50", updated_at: "new" };
  const props = { review, onReprocess: async (_id, selected) => selected ? pending.promise : preview };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  await act(async () => { await button(renderer, "Rielabora OCR").props.onClick(); });
  let operation;
  await act(async () => { operation = button(renderer, "Conferma rielaborazione").props.onClick(); });
  assert.equal(button(renderer, "Conferma rielaborazione").props.disabled, true);
  assert.equal(renderer.root.findByType("fieldset").props.disabled, true);
  assert.equal(button(renderer, "Approva").props.disabled, true);
  await act(async () => {
    renderer.update(React.createElement(Card, { ...props, review: saved }));
    pending.resolve(saved);
    await operation;
  });
  assert.equal(button(renderer, "Conferma rielaborazione"), undefined);
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "");
  assert.ok(renderer.root.findAllByType("p").some((node) =>
    node.children.join("").includes("Totale scontrini rilevato: 303.50")
  ));
  assert.match(JSON.stringify(renderer.toJSON()), /Rielaborazione completata/);
  assert.equal(button(renderer, "Approva").props.disabled, true);
  await act(async () => { renderer.update(React.createElement(Card, { ...props, review: { ...saved } })); });
  assert.ok(renderer.root.findAllByType("p").some((node) =>
    node.children.join("").includes("Totale scontrini rilevato: 303.50")
  ));
  await act(async () => { renderer.unmount(); });
});

test("external changes do not discard a draft and require explicit reset", async () => {
  let renderer;
  const props = { review };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  await act(async () => { renderer.root.findAllByType("input")[1].props.onChange({ target: { value: "manuale" } }); });
  const updated = { ...review, closure_number: "nuovo" };
  await act(async () => { renderer.update(React.createElement(Card, { ...props, review: updated })); });
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "manuale");
  assert.equal(button(renderer, "Salva correzioni").props.disabled, true);
  assert.match(JSON.stringify(renderer.toJSON()), /La scheda è stata aggiornata/);
  await act(async () => { button(renderer, "Annulla modifiche").props.onClick(); });
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "nuovo");
  await act(async () => { renderer.unmount(); });
});

test("external changes invalidate an open comparison until it is cancelled", async () => {
  let renderer;
  const preview = { previous: {}, proposed: {}, review_version: "v1", extraction_version: "v2" };
  const props = { review, onReprocess: async () => preview };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  await act(async () => { await button(renderer, "Rielabora OCR").props.onClick(); });
  await act(async () => {
    renderer.update(React.createElement(Card, { ...props, review: { ...review, closure_number: "nuovo" } }));
  });
  assert.equal(button(renderer, "Conferma rielaborazione"), undefined);
  assert.match(JSON.stringify(renderer.toJSON()), /La scheda è stata aggiornata/);
  await act(async () => { button(renderer, "Annulla confronto").props.onClick(); });
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "nuovo");
  await act(async () => { renderer.unmount(); });
});

test("reprocess failure remains visible and restores controls", async () => {
  let renderer;
  const props = { review, onReprocess: async () => { throw new Error("Documento originale non disponibile."); } };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  await act(async () => { await button(renderer, "Rielabora OCR").props.onClick(); });
  assert.match(JSON.stringify(renderer.toJSON()), /Documento originale non disponibile/);
  assert.equal(renderer.root.findByType("fieldset").props.disabled, false);
  assert.equal(button(renderer, "Rielabora OCR").props.disabled, false);
  await act(async () => { renderer.unmount(); });
});

test("approve is enabled only when the server grants approval", async () => {
  let renderer;
  const ready = { ...review, total_amount: "100.00", cash_amount: null, can_approve: false };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, { review: ready })); });
  assert.equal(button(renderer, "Approva").props.disabled, true);
  assert.match(JSON.stringify(renderer.toJSON()), /approvazione è riservata/);
  await act(async () => { renderer.update(React.createElement(Card, { review: { ...ready, can_approve: true } })); });
  assert.equal(button(renderer, "Approva").props.disabled, false);
  await act(async () => { renderer.unmount(); });
});

test("save keeps edits locked during the request and applies server values", async () => {
  let renderer;
  const pending = deferred();
  const saved = { ...review, closure_number: "manuale", updated_at: "new" };
  const props = { review, onCorrect: async () => pending.promise };
  await act(async () => { renderer = TestRenderer.create(React.createElement(Card, props)); });
  await act(async () => { renderer.root.findAllByType("input")[1].props.onChange({ target: { value: "manuale" } }); });
  let operation;
  await act(async () => { operation = button(renderer, "Salva correzioni").props.onClick(); });
  assert.equal(renderer.root.findByType("fieldset").props.disabled, true);
  await act(async () => {
    renderer.update(React.createElement(Card, { ...props, review: saved }));
    pending.resolve(saved);
    await operation;
  });
  assert.equal(renderer.root.findAllByType("input")[1].props.value, "manuale");
  assert.equal(button(renderer, "Salva correzioni").props.disabled, true);
  assert.match(JSON.stringify(renderer.toJSON()), /Correzioni salvate/);
  await act(async () => { renderer.unmount(); });
});

test("monthly filter preserves drafts and OCR comparison across filter and month changes", async () => {
  let renderer;
  const preview = { previous: {}, proposed: {}, review_version: "v1", extraction_version: "v2" };
  const november = {
    ...review, id: 2, date: "2026-11-03",
    document: { ...review.document, id: 10, original_filename: "novembre.png" },
  };
  const noDate = {
    ...review, id: 3, date: null,
    document: { ...review.document, id: 11, original_filename: "senza-data.png" },
  };
  const props = {
    month: "2026-11", cashClosureReviews: [review, november, noDate],
    handleReprocessCashClosure: async () => preview,
  };
  const page = (values) => React.createElement(MemoryRouter, null, React.createElement(UploadPage, values));
  const card = (id) => renderer.root.findAllByType(Card).find((item) => item.props.review.id === id);
  const filter = (index) => renderer.root.findAllByProps({ name: "cash-closure-filter" })[index];
  await act(async () => { renderer = TestRenderer.create(page(props)); });
  assert.equal(card(1).parent.props.hidden, true);
  assert.equal(card(2).parent.props.hidden, false);
  assert.equal(card(3).parent.props.hidden, true);
  await act(async () => { filter(1).props.onChange(); });
  assert.equal(card(1).parent.props.hidden, false);
  assert.equal(card(3).parent.props.hidden, false);
  await act(async () => {
    card(1).findAllByType("input")[1].props.onChange({ target: { value: "manuale" } });
    await card(2).findAllByType("button").find((item) => item.children.includes("Rielabora OCR")).props.onClick();
  });
  await act(async () => { filter(0).props.onChange(); });
  assert.equal(card(1).parent.props.hidden, true);
  assert.equal(card(1).findAllByType("input")[1].props.value, "manuale");
  assert.ok(card(2).findAllByType("button").some((item) => item.children.includes("Conferma rielaborazione")));
  await act(async () => { renderer.update(page({ ...props, month: "2025-11" })); });
  assert.equal(card(2).parent.props.hidden, true);
  await act(async () => { filter(1).props.onChange(); });
  assert.equal(card(1).findAllByType("input")[1].props.value, "manuale");
  assert.ok(card(2).findAllByType("button").some((item) => item.children.includes("Conferma rielaborazione")));
  await act(async () => { renderer.unmount(); });
});
