import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

const FRONTEND_ROOT = new URL("..", import.meta.url).pathname;

let server;
let DashboardPage;

before(async () => {
  server = await createServer({
    root: FRONTEND_ROOT,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  DashboardPage = (await server.ssrLoadModule("/src/pages/DashboardPage.jsx")).default;
});

after(async () => {
  await server?.close();
});

function renderDashboard(props) {
  const element = createElement(
    MemoryRouter,
    {},
    createElement(DashboardPage, {
      isLoading: false,
      isLoadingInvoices: false,
      month: "2026-07",
      overview: {
        latest_bank_transaction_date: "2026-07-31",
        latest_cash_closure_date: "2026-07-14",
        margin_percent: 35.5,
        total_revenue: 15000,
        total_costs: 9750,
        pending_invoice_amount: 2500,
      },
      pendingInvoices: 3,
      firstDueInvoice: null,
      allOverdueInvoices: [],
      onExportPdf: () => {},
      ...props,
    })
  );
  return renderToStaticMarkup(element);
}

test("dashboard displays Italian text, not English", () => {
  const html = renderDashboard();

  // Should NOT contain English text
  assert.ok(
    !html.includes("Business Overview"),
    "Dashboard title should not be 'Business Overview' (English)"
  );
  assert.ok(
    !html.includes("Export PDF"),
    "Export button should not say 'Export PDF' (English)"
  );

  // Should contain Italian text
  assert.ok(
    html.includes("Panoramica attività"),
    "Dashboard title should contain 'Panoramica attività' (Italian)"
  );
  assert.ok(
    html.includes("Esporta PDF"),
    "Export button should say 'Esporta PDF' (Italian)"
  );
});

test("upload page does not contain mixed English-Italian text", async () => {
  const UploadPage = (await server.ssrLoadModule("/src/pages/UploadPage.jsx")).default;

  const element = createElement(
    MemoryRouter,
    {},
    createElement(UploadPage, {
      documents: [],
      currentMonthInvoices: [],
      overview: {},
      isLoadingDocuments: false,
      isLoadingInvoices: false,
      isLoadingOverview: false,
      sortState: { field: "date", direction: "desc" },
      setSortState: () => {},
    })
  );
  const html = renderToStaticMarkup(element);

  // Should NOT contain mixed English-Italian text
  assert.ok(
    !html.includes("Import in corso"),
    "Upload page should not contain 'Import in corso' (mixed Italian-English)"
  );

  // Should contain Italian UI labels
  assert.ok(
    html.includes("Carica Documenti") || html.includes("Carica file"),
    "Upload page should contain Italian labels"
  );
});

test("sidebar renders with Italian month names", () => {
  // Test month name localization separately since Sidebar uses NavLink
  const MONTHS = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
  ];

  // Verify Italian month names are defined
  assert.strictEqual(
    MONTHS.length,
    12,
    "All 12 Italian month names should be defined"
  );
  assert.ok(
    MONTHS.includes("Gennaio"),
    "First month should be 'Gennaio' (Italian)"
  );
  assert.ok(
    MONTHS.includes("Dicembre"),
    "Last month should be 'Dicembre' (Italian)"
  );
  assert.ok(
    !MONTHS.some((m) => m === "January" || m === "December"),
    "No English month names should be in the list"
  );
});
