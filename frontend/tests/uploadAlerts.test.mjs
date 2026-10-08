import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test, { after, before } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

const FRONTEND_ROOT = new URL("..", import.meta.url).pathname;
const DUPLICATE_DETAIL =
  "Questa chiusura cassa è già stata caricata (07/10/2026 – chiusura n. 123 – 1.234,50 €).";

let server;
let AlertBanner;
let UploadPage;

before(async () => {
  server = await createServer({
    root: FRONTEND_ROOT,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  AlertBanner = (await server.ssrLoadModule("/src/components/AlertBanner.jsx")).default;
  UploadPage = (await server.ssrLoadModule("/src/pages/UploadPage.jsx")).default;
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

function findCloseButton(node) {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findCloseButton(child);
      if (found) return found;
    }
    return null;
  }
  if (node.type === "button") return node;
  return findCloseButton(node.props?.children);
}

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

test("AlertBanner close button calls onClose manually", () => {
  let closed = 0;
  const tree = AlertBanner({
    variant: "error",
    title: "Dati non validi",
    onClose: () => {
      closed += 1;
    },
    children: "dettaglio",
  });

  const button = findCloseButton(tree);

  assert.ok(button, "close button must exist");
  assert.equal(button.props["aria-label"], "Chiudi messaggio");
  button.props.onClick();
  assert.equal(closed, 1);
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
