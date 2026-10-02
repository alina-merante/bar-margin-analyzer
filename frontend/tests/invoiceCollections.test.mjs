import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  countInvoicesByCategory,
  filterInvoiceList,
  mergeUniqueInvoices,
} from "../src/invoiceCollections.js";

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
  assert.match(pageSource, /Mostrate \{filteredInvoices\.length\} di \{invoiceSearchScope\.length\} fatture/);
  assert.match(pageSource, /const invoiceSearchScope = useMemo\(\(\) => \{\s*const normalizedSupplierSearch = supplierSearch\.trim\(\);\s*return normalizedSupplierSearch \? allVisibleInvoices : invoicesForView;/);
});