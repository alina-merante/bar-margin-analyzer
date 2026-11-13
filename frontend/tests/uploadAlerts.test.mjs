import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test, { after, before } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";
import { uploadErrorFromResponse } from "../src/apiErrors.js";

const FRONTEND_ROOT = new URL("..", import.meta.url).pathname;
const DUPLICATE_DETAIL =
  "Questa chiusura cassa è già stata caricata (07/10/2026 – chiusura n. 123 – 1.234,50 €).";

let server;
let AlertBanner;
let attachAlertDismissalHandlers;
let UploadPage;
let CashClosureReprocessComparison;
let InvoicesPage;

before(async () => {
  server = await createServer({
    root: FRONTEND_ROOT,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  const alertModule = await server.ssrLoadModule("/src/components/AlertBanner.jsx");
  AlertBanner = alertModule.default;
  attachAlertDismissalHandlers = alertModule.attachAlertDismissalHandlers;
  const uploadPageModule = await server.ssrLoadModule("/src/pages/UploadPage.jsx");
  UploadPage = uploadPageModule.default;
  CashClosureReprocessComparison = uploadPageModule.CashClosureReprocessComparison;
  InvoicesPage = (await server.ssrLoadModule("/src/pages/InvoicesPage.jsx")).default;
});

after(async () => {
  await server?.close();
});

function renderBanner(props) {
  return renderToStaticMarkup(createElement(AlertBanner, props));
}

function renderUploadPage(props) {
  return renderToStaticMarkup(
    createElement(MemoryRouter, null, createElement(UploadPage, { month: "2026-10", ...props }))
  );
}

test("cash and invoice camera controls remain separate from file upload", () => {
  const upload = renderUploadPage({});
  assert.match(upload, /aria-label="Scatta foto chiusura di cassa"/);
  assert.match(upload, /aria-label="Scatta foto fattura"/);
  assert.equal((upload.match(/accept="image\/\*" capture="environment"/g) || []).length, 2);
  assert.match(upload, /id="daily-cash-upload-input"/);
  assert.match(upload, /id="invoice-upload-input"/);

  const invoices = renderToStaticMarkup(createElement(
    MemoryRouter, null, createElement(InvoicesPage, {
      month: "2026-10", handleInvoiceDocumentUpload: () => {},
    })
  ));
  assert.match(invoices, /aria-label="Scatta foto fattura"/);
  assert.match(invoices, /accept="image\/\*" capture="environment"/);
  assert.match(invoices, /accept="\.pdf,\.jpg,\.jpeg,\.png,\.xml"/);
});

test("AlertBanner uses role alert for errors and warnings, status for success", () => {
  assert.match(renderBanner({ variant: "error", children: "x" }), /role="alert"/);
  assert.match(renderBanner({ variant: "warning", children: "x" }), /role="alert"/);
  assert.match(renderBanner({ variant: "success", children: "x" }), /role="status"/);
});

test("AlertBanner renders title, message and an accessible close button", () => {
  const html = renderBanner({
    variant: "warning",
    title: "Documento già presente",
    onClose: () => {},
    children: DUPLICATE_DETAIL,
  });

  assert.match(html, /alert-banner--warning/);
  assert.match(html, /Documento già presente/);
  assert.match(html, /aria-label="Chiudi messaggio"/);
  assert.ok(html.includes(DUPLICATE_DETAIL.replace("–", "–")));
});

test("AlertBanner without onClose renders no close button", () => {
  assert.doesNotMatch(renderBanner({ variant: "error", children: "x" }), /<button/);
});

test("AlertBanner dismisses on outside pointer and Escape without cancelling app actions", () => {
  const listeners = new Map();
  const eventTarget = {
    addEventListener: (type, listener) => listeners.set(type, listener),
    removeEventListener: (type) => listeners.delete(type),
  };
  const element = { contains: (target) => target === "inside-alert" };
  let closeCount = 0;
  let appActionCount = 0;
  const cleanup = attachAlertDismissalHandlers(element, eventTarget, () => {
    closeCount += 1;
  });
  let prevented = false;
  let propagationStopped = false;

  listeners.get("pointerdown")({
    target: "app-button",
    preventDefault: () => {
      prevented = true;
    },
    stopPropagation: () => {
      propagationStopped = true;
    },
  });
  appActionCount += 1;

  assert.equal(closeCount, 1);
  assert.equal(appActionCount, 1);
  assert.equal(prevented, false);
  assert.equal(propagationStopped, false);

  listeners.get("pointerdown")({ target: "inside-alert" });
  assert.equal(closeCount, 1);
  listeners.get("keydown")({ key: "Escape" });
  assert.equal(closeCount, 2);

  cleanup();
  assert.equal(listeners.size, 0);
});

test("AlertBanner close button remains available", async () => {
  const source = await readFile(
    new URL("../src/components/AlertBanner.jsx", import.meta.url),
    "utf8"
  );

  assert.match(source, /aria-label="Chiudi messaggio"/);
  assert.match(source, /onClick=\{onClose\}/);
});

test("UploadPage shows the 409 backend detail with the duplicate title", () => {
  const html = renderUploadPage({
    documentUploadError: {
      variant: "error",
      title: "Documento già presente",
      message: DUPLICATE_DETAIL,
    },
  });

  assert.match(html, /alert-banner--error/);
  assert.doesNotMatch(html, /alert-banner--warning/);
  assert.match(html, /Documento già presente/);
  assert.ok(html.includes("già stata caricata"));
  assert.match(html, /role="alert"/);
  assert.match(html, /aria-label="Chiudi messaggio"/);
  assert.doesNotMatch(html, /upload-feedback error/);
});

test("UploadPage shows 422 and 500 errors through the same banner", () => {
  const html422 = renderUploadPage({
    documentUploadError: {
      variant: "error",
      title: "Dati non validi",
      message: "Numero di chiusura non rilevato. Carica un'immagine o un PDF più leggibile.",
    },
  });

  const html500 = renderUploadPage({
    uploadError: {
      variant: "error",
      title: "Errore del server",
      message: "Si è verificato un problema sul server.",
    },
  });

  assert.match(html422, /Dati non validi/);
  assert.match(html422, /Numero di chiusura non rilevato/);
  assert.match(html500, /Errore del server/);
  assert.match(html500, /alert-banner--error/);
});

test("UploadPage keeps the error visible on every render until it is dismissed", () => {
  const props = {
    documentUploadError: { variant: "error", title: "Documento già presente", message: DUPLICATE_DETAIL },
  };

  assert.match(renderUploadPage(props), /Documento già presente/);
  assert.match(renderUploadPage(props), /Documento già presente/);
  assert.doesNotMatch(
    renderUploadPage({ ...props, documentUploadError: null }),
    /Documento già presente/
  );
});

test("cash upload displays the actual 422 closure recognition error", async () => {
  const detail = "Il documento non contiene evidenze sufficienti per riconoscere una chiusura di cassa.";
  const documentUploadError = await uploadErrorFromResponse({
    status: 422,
    text: async () => JSON.stringify({ detail }),
  });
  const html = renderUploadPage({ documentUploadError });
  assert.match(html, /role="alert"/);
  assert.ok(html.includes(detail));
});

test("review displays the receipt subtotal and count without presenting it as the overall total", () => {
  const html = renderUploadPage({
    cashClosureReviews: [{
      id: 1,
      date: "2023-09-26",
      closure_number: null,
      total_amount: null,
      cash_amount: "255.50",
      card_amount: null,
      receipts_count: 25,
      receipts_total: "303.50",
      anomalies: [],
      ocr_values: {},
      document: { original_filename: "report.png", file_url: "" },
    }],
  });
  assert.match(html, /Totale scontrini rilevato: 303\.50/);
  assert.match(html, /non è il totale complessivo/);
  assert.match(html, /Numero scontrini/);
  assert.match(html, /value="25"/);
  assert.match(html, /Numero chiusura/);
  assert.match(html, /Rielabora OCR/);
});

test("reprocess comparison shows previous manual values and new OCR values before confirmation", () => {
  const html = renderToStaticMarkup(createElement(CashClosureReprocessComparison, {
    preview: {
      previous: { closure_number: "MANUALE", total_amount: "400.00", receipts_count: 24 },
      proposed: { closure_number: null, total_amount: null, receipts_count: 25, receipts_total: "303.50" },
    },
    busy: false,
  }));
  assert.match(html, /correzioni manuali/);
  assert.match(html, /MANUALE/);
  assert.match(html, /400\.00/);
  assert.match(html, /303\.50/);
  assert.match(html, /Non rilevato/);
  assert.match(html, /Conferma rielaborazione/);
  assert.match(html, /Annulla/);
});

test("review displays translated warnings rather than OCR codes", () => {
  const html = renderUploadPage({
    cashClosureReviews: [{
      id: 1, anomalies: ["total_amount:missing", "closure_number:missing"],
      ocr_values: {}, document: { original_filename: "report.png", file_url: "" },
    }],
  });
  assert.match(html, /Totale complessivo: non rilevato/);
  assert.match(html, /Numero chiusura: non rilevato/);
  assert.doesNotMatch(html, /total_amount:missing|closure_number:missing/);
});

test("failed or pending review loading does not falsely report an empty list", () => {
  const loading = renderUploadPage({ cashClosureLoading: true });
  assert.match(loading, /Caricamento delle chiusure/);
  assert.doesNotMatch(loading, /Nessuna chiusura in attesa/);
  const failed = renderUploadPage({ cashClosureLoadError: "Impossibile aggiornare le chiusure." });
  assert.match(failed, /Impossibile aggiornare le chiusure/);
  assert.match(failed, /Riprova/);
  assert.doesNotMatch(failed, /Nessuna chiusura in attesa/);
});

test("upload error handling is not cleared by generic clicks or timers", async () => {
  const [uploadPage, app, banner] = await Promise.all(
    ["src/pages/UploadPage.jsx", "src/App.jsx", "src/components/AlertBanner.jsx"].map((path) =>
      readFile(new URL(`../${path}`, import.meta.url), "utf8")
    )
  );

  assert.doesNotMatch(uploadPage, /clearLocalUploadErrors/);
  assert.doesNotMatch(uploadPage, /<main[^>]*onClick/);
  assert.match(uploadPage, /<main className="main upload-page">/);
  for (const source of [uploadPage, banner]) {
    assert.doesNotMatch(source, /setTimeout|setInterval/);
  }
  assert.doesNotMatch(app, /setTimeout/);
});

test("a new upload in the same area clears the previous error", async () => {
  const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const uploadPage = await readFile(new URL("../src/pages/UploadPage.jsx", import.meta.url), "utf8");

  assert.match(app, /setUploadError\(null\);\s*setUploadMessage\(""\);/);
  assert.match(app, /setInvoiceUploadError\(null\);/);
  assert.match(app, /setDocumentUploadError\(null\);\s*setDocumentUploadMessage\(""\);/);
  assert.match(uploadPage, /async function handleCashDocument\(file\) \{\s*if \(!file\) return;\s*setCashUploadError\(""\);[\s\S]*?clearDocumentMessages\?\.\(\);/);
  assert.match(uploadPage, /async function handleOtherDocument\(file\) \{\s*if \(!file\) return;\s*setCashUploadError\(""\);[\s\S]*?clearDocumentMessages\?\.\(\);/);
});

const CASH_WARNING = "Contanti non rilevati: verifica l'importo sul documento originale.";
const CARD_WARNING =
  "Pagamenti elettronici non rilevati: verifica l'importo sul documento originale.";

test("UploadPage shows OCR warnings next to the success message", () => {
  const html = renderUploadPage({
    documentUploadMessage: "Documento acquisito: chiusura.png",
    documentUploadWarnings: [CASH_WARNING, CARD_WARNING],
  });

  assert.match(html, /Documento acquisito: chiusura\.png/);
  assert.match(html, /alert-banner--success/);
  assert.match(html, /alert-banner--warning/);
  assert.match(html, /Controlla i dati letti/);
  assert.ok(html.includes("Contanti non rilevati"));
  assert.ok(html.includes("Pagamenti elettronici non rilevati"));
  assert.match(html, /aria-label="Chiudi messaggio"/);
  assert.doesNotMatch(html, /alert-banner--error/);
});

test("UploadPage warning stays visible on every render until dismissed", () => {
  const props = { documentUploadWarnings: [CASH_WARNING] };
  assert.match(renderUploadPage(props), /Controlla i dati letti/);
  assert.match(renderUploadPage(props), /Controlla i dati letti/);
  assert.doesNotMatch(
    renderUploadPage({ documentUploadWarnings: [] }),
    /Controlla i dati letti/
  );
});

test("UploadPage ignores missing or invalid warnings safely", () => {
  for (const documentUploadWarnings of [undefined, null, "testo", {}, 42, [null, 1, "", "  "]]) {
    const html = renderUploadPage({ documentUploadWarnings });
    assert.doesNotMatch(html, /Controlla i dati letti/);
  }
});

test("OCR warning banner keeps 409 and 422 banners unchanged", () => {
  const html = renderUploadPage({
    documentUploadError: { variant: "error", title: "Dati non validi", message: "Totale mancante" },
    documentUploadWarnings: [],
  });
  assert.match(html, /alert-banner--error/);
  assert.match(html, /Dati non validi/);
  assert.doesNotMatch(html, /alert-banner--warning/);
});

test("OCR warnings are closed manually, reset on new upload, and use no timers", async () => {
  const [app, uploadPage] = await Promise.all(
    ["src/App.jsx", "src/pages/UploadPage.jsx"].map((path) =>
      readFile(new URL(`../${path}`, import.meta.url), "utf8")
    )
  );

  assert.match(app, /setDocumentUploadMessage\(""\);\s*setDocumentUploadWarnings\(\[\]\);/);
  assert.match(app, /function clearDocumentMessages\(\) \{[\s\S]*?setDocumentUploadWarnings\(\[\]\);/);
  assert.match(app, /kind === "documentWarnings"\) setDocumentUploadWarnings\(\[\]\)/);
  assert.match(app, /Array\.isArray\(result\.warnings\)/);
  assert.match(uploadPage, /dismiss\("documentWarnings"\)/);
  assert.doesNotMatch(uploadPage, /setTimeout|setInterval/);
  assert.doesNotMatch(uploadPage, /<main[^>]*onClick/);
});
