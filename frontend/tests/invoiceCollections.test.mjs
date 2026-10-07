import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  countInvoicesByCategory,
  filterInvoiceList,
  mergeUniqueInvoices,
} from "../src/invoiceCollections.js";
import {
  isInvoiceOverdue,
  isInvoiceOverdueInCurrentYear,
} from "../src/invoiceDateStatus.js";

const today = new Date(2026, 9, 2, 15, 30);

test("month and arrears union keeps one copy of the same invoice id", () => {
  const monthlyInvoice = {
    id: 7,
    supplier: "Fornitore Alfa",
    category: "Bevande",
    status: "pending",
    due_date: "2026-10-01",
  };
  const arrearsCopy = { ...monthlyInvoice };

  const invoices = mergeUniqueInvoices([monthlyInvoice], [arrearsCopy]);

  assert.equal(invoices.length, 1);
  assert.strictEqual(invoices[0], monthlyInvoice);
  assert.equal(
    filterInvoiceList(invoices, {
      supplierSearch: "alfa",
      statusFilter: "all",
    }).length,
    1
  );
});

test("category counts count an overlapping invoice id once", () => {
  const monthlyInvoice = { id: 7, category: "Bevande" };
  const arrearsCopy = { ...monthlyInvoice };
  const counts = countInvoicesByCategory(
    [monthlyInvoice, arrearsCopy],
    (invoice) => invoice.category
  );

  assert.equal(counts.get("Bevande"), 1);
});

test("overlapping month and arrears invoice stays unique across list, search, footer, and categories while KPIs stay independent", async () => {
  const monthlyOverdueInvoice = {
    id: 7,
    supplier: "Fornitore Alfa",
    invoice_number: "FA-7",
    category: "Bevande",
    status: "pending",
    due_date: "2026-10-01",
    total: 150,
    linked_amount: 50,
  };
  const monthlyDueInvoice = {
    id: 8,
    supplier: "Fornitore Beta",
    category: "Caffe",
    status: "pending",
    due_date: "2026-10-03",
    total: 80,
    linked_amount: 0,
  };
  const arrearsCopy = { ...monthlyOverdueInvoice };
  const annualOnlyOverdueInvoice = {
    id: 9,
    supplier: "Fornitore Gamma",
    category: "Servizi",
    status: "pending",
    due_date: "2026-04-01",
    total: 70,
    linked_amount: 0,
  };
  const monthlyInvoices = [monthlyOverdueInvoice, monthlyDueInvoice];
  const yearOverdueInvoices = [arrearsCopy, annualOnlyOverdueInvoice];
  const allVisibleInvoices = mergeUniqueInvoices(monthlyInvoices, yearOverdueInvoices);

  assert.deepEqual(allVisibleInvoices.map((invoice) => invoice.id), [7, 8, 9]);

  const supplierSearch = "alfa";
  const invoiceSearchScope = supplierSearch.trim()
    ? allVisibleInvoices
    : monthlyInvoices;
  const filteredInvoices = filterInvoiceList(invoiceSearchScope, {
    supplierSearch,
    statusFilter: "all",
    today,
  });

  assert.deepEqual(filteredInvoices.map((invoice) => invoice.id), [7]);
  assert.equal(
    `Mostrate ${filteredInvoices.length} di ${invoiceSearchScope.length} fatture`,
    "Mostrate 1 di 3 fatture"
  );

  const categoryCounts = countInvoicesByCategory(
    allVisibleInvoices,
    (invoice) => invoice.category
  );
  assert.equal(categoryCounts.get("Bevande"), 1);

  const monthlyOverdueInvoices = monthlyInvoices.filter((invoice) =>
    isInvoiceOverdue(invoice, today)
  );
  const currentYearArrears = yearOverdueInvoices.filter((invoice) =>
    isInvoiceOverdueInCurrentYear(invoice, today)
  );
  const remainingTotal = (invoices) =>
    invoices.reduce(
      (sum, invoice) => sum + Number(invoice.total) - Number(invoice.linked_amount),
      0
    );
  const monthlyOverdueKpi = remainingTotal(monthlyOverdueInvoices);
  const annualArrearsKpi = remainingTotal(currentYearArrears);

  assert.deepEqual(monthlyOverdueInvoices.map((invoice) => invoice.id), [7]);
  assert.deepEqual(currentYearArrears.map((invoice) => invoice.id), [7, 9]);
  assert.equal(monthlyOverdueKpi, 100);
  assert.equal(annualArrearsKpi, 170);

  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  assert.match(pageSource, /const monthOverdueInvoices = currentMonthInvoices\.filter\(isInvoiceOverdue\)/);
  assert.match(pageSource, /const yearOverdueInvoices = useMemo\(\s*\(\) => invoices\.filter\(isInvoiceOverdueInCurrentYear\)/);
});

test("supplier search and active status filter are both applied", () => {
  const invoices = [
    { id: 1, supplier: "Fornitore Alfa", status: "pending", due_date: "2026-10-01" },
    { id: 2, supplier: "Fornitore Alfa", status: "pending", due_date: "2026-10-03" },
    { id: 3, supplier: "Fornitore Beta", status: "pending", due_date: "2026-10-01" },
  ];

  const results = filterInvoiceList(invoices, {
    supplierSearch: "alfa",
    statusFilter: "overdue",
    today,
  });

  assert.deepEqual(results.map((invoice) => invoice.id), [1]);
});

test("monthly and arrears KPI sources stay independent from the deduplicated union", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");

  assert.match(pageSource, /const monthOverdueAmount = monthOverdueInvoices\.reduce/);
  assert.match(pageSource, /const yearOverdueTotal = yearOverdueInvoices\.reduce/);
  assert.match(pageSource, /const allVisibleInvoices = useMemo\(\s*\(\) => mergeUniqueInvoices\(currentMonthInvoices, yearOverdueInvoices\)/);
  assert.match(pageSource, /Mostrate \{filteredInvoices\.length\} di \{invoiceSearchScope\.length\} fatture/);
  assert.match(pageSource, /const invoiceSearchScope = useMemo\(\(\) => \{\s*const normalizedSupplierSearch = supplierSearch\.trim\(\);\s*return normalizedSupplierSearch \? allVisibleInvoices : invoicesForView;/);
});