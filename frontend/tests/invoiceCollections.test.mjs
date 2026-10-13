import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  countInvoicesByCategory,
  filterInvoiceList,
  mergeUniqueInvoices,
} from "../src/invoiceCollections.js";
import {
  getInvoiceRemainingAmount,
  isInvoiceOverdue,
  isInvoiceArrearsBeforeMonth,
  isInvoiceUnpaid,
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

test("October and July counts, amounts, and arrears use the selected due month", () => {
  const octoberToday = new Date(2026, 9, 13, 18, 0);
  const invoices = [
    { id: 1, supplier: "vvvvv", status: "pending", due_date: "2026-07-12", total: 50, linked_amount: 0 },
    { id: 2, supplier: "aaaaa", status: "pending", due_date: "2026-07-05", total: 120, linked_amount: 0 },
    { id: 3, supplier: "tttt", status: "pending", due_date: "2026-10-16", total: 50, linked_amount: 0 },
    { id: 4, supplier: "gggg", status: "pending", due_date: "2026-10-25", total: 44, linked_amount: 0 },
    { id: 5, supplier: "Paid A", status: "paid", due_date: "2026-07-01", total: 700, linked_amount: 700 },
    { id: 6, supplier: "Paid B", status: "paid", due_date: "2026-07-02", total: 220, linked_amount: 220 },
  ];
  const julyInvoices = invoices.filter((invoice) =>
    invoice.due_date.startsWith("2026-07")
  );
  const octoberInvoices = invoices.filter((invoice) =>
    invoice.due_date.startsWith("2026-10")
  );
  const arrears = invoices.filter((invoice) =>
    isInvoiceArrearsBeforeMonth(invoice, "2026-10", octoberToday)
  );
  const monthlyDue = octoberInvoices.filter((invoice) =>
    filterInvoiceList([invoice], {
      statusFilter: "due",
      today: octoberToday,
    }).length
  );
  const monthlyOverdueJuly = julyInvoices.filter((invoice) =>
    isInvoiceOverdue(invoice, octoberToday)
  );
  const overdueTabJuly = filterInvoiceList(julyInvoices, {
    statusFilter: "overdue",
    month: "2026-07",
    today: octoberToday,
  });
  const dueTabJuly = filterInvoiceList(julyInvoices, {
    statusFilter: "due",
    month: "2026-07",
    today: octoberToday,
  });
  const amount = (items) => items.reduce((sum, item) => sum + item.total, 0);
  const arrearsFilter = filterInvoiceList(invoices, {
    statusFilter: "year-overdue",
    month: "2026-10",
    today: octoberToday,
  });
  const supplierSearchInOctober = filterInvoiceList(octoberInvoices, {
    supplierSearch: "tttt",
    statusFilter: "all",
    today: octoberToday,
  });

  assert.equal(julyInvoices.length, 4);
  assert.equal(amount(julyInvoices), 1090);
  assert.equal(julyInvoices.filter((invoice) => invoice.status === "paid").length, 2);
  assert.equal(amount(julyInvoices.filter((invoice) => invoice.status === "paid")), 920);
  assert.equal(monthlyOverdueJuly.length, 2);
  assert.equal(amount(monthlyOverdueJuly), 170);
  assert.equal(overdueTabJuly.length, 2);
  assert.equal(amount(overdueTabJuly), 170);
  assert.equal(dueTabJuly.length, 2);
  assert.equal(amount(dueTabJuly), 170);

  assert.equal(octoberInvoices.length, 2);
  assert.equal(amount(octoberInvoices), 94);
  assert.equal(monthlyDue.length, 2);
  assert.equal(amount(monthlyDue), 94);
  assert.equal(monthlyOverdueJuly.length, 2);
  assert.equal(arrears.length, 2);
  assert.equal(amount(arrears), 170);
  assert.deepEqual(arrearsFilter.map((invoice) => invoice.id), [1, 2]);
  assert.deepEqual(supplierSearchInOctober.map((invoice) => invoice.id), [3]);
});

test("July payable filter includes overdue outstanding balance without double-counting", () => {
  const julyInvoices = [
    { id: 1, supplier: "aaaaa", invoice_number: "12", status: "pending", due_date: "2026-07-05", total: 120, linked_amount: 0 },
    { id: 2, status: "paid", due_date: "2026-07-01", total: 700, linked_amount: 700 },
    { id: 3, status: "paid", due_date: "2026-07-02", total: 220, linked_amount: 220 },
  ];
  const octoberToday = new Date(2026, 9, 13, 12);
  const payable = filterInvoiceList(julyInvoices, {
    statusFilter: "due",
    month: "2026-07",
    today: octoberToday,
  });
  const overdue = filterInvoiceList(julyInvoices, {
    statusFilter: "overdue",
    month: "2026-07",
    today: octoberToday,
  });
  const paid = julyInvoices.filter((invoice) => invoice.status === "paid");
  const remaining = payable.reduce((sum, invoice) => sum + getInvoiceRemainingAmount(invoice), 0);

  assert.deepEqual(payable.map((invoice) => invoice.id), [1]);
  assert.deepEqual(overdue.map((invoice) => invoice.id), [1]);
  assert.equal(paid.length + payable.length, julyInvoices.length);
  assert.equal(remaining, 120);
  assert.equal(paid.reduce((sum, invoice) => sum + invoice.total, 0), 920);
  assert.equal(julyInvoices.reduce((sum, invoice) => sum + invoice.total, 0), 1040);
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

test("category and supplier search combine with every invoice status tab", () => {
  const invoices = [
    {
      id: 1,
      supplier: "Fornitore Alfa",
      category: "Bevande",
      status: "paid",
      due_date: "2026-10-01",
    },
    {
      id: 2,
      supplier: "Fornitore Alfa",
      category: "Bevande",
      status: "pending",
      due_date: "2026-10-01",
    },
    {
      id: 3,
      supplier: "Fornitore Alfa",
      category: "Bevande",
      status: "pending",
      due_date: "2026-10-03",
    },
    {
      id: 4,
      supplier: "Fornitore Alfa",
      category: "Caffe",
      status: "paid",
      due_date: "2026-10-01",
    },
    {
      id: 5,
      supplier: "Fornitore Beta",
      category: "Bevande",
      status: "paid",
      due_date: "2026-10-01",
    },
  ];

  const cases = [
    ["all", [1, 2, 3]],
    ["paid", [1]],
    ["due", [2, 3]],
    ["overdue", [2]],
  ];

  for (const [statusFilter, expectedIds] of cases) {
    const results = filterInvoiceList(invoices, {
      supplierSearch: "alfa",
      statusFilter,
      categoryFilter: "Bevande",
      month: "2026-10",
      categoryForInvoice: (invoice) => invoice.category,
      today,
    });

    assert.deepEqual(results.map((invoice) => invoice.id), expectedIds, statusFilter);
  }
});

test("changing or resetting the category leaves the active status tab unchanged", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const applyAction = pageSource.match(
    /className="invoice-category-apply-btn"[\s\S]*?onClick=\{\(\) => \{([\s\S]*?)\}\}/
  )?.[1];
  const resetAction = pageSource.match(
    /className="invoice-category-reset-btn"[\s\S]*?onClick=\{\(\) => \{([\s\S]*?)\}\}/
  )?.[1];

  assert.ok(applyAction, "category apply handler should be present");
  assert.ok(resetAction, "category reset handler should be present");
  assert.match(applyAction, /setCategoryFilter\(draftCategoryFilter\)/);
  assert.doesNotMatch(applyAction, /setStatusFilter/);
  assert.match(resetAction, /setCategoryFilter\(""\)/);
  assert.doesNotMatch(resetAction, /setStatusFilter/);
});

test("selected category has a clear visual and accessible state", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");

  assert.match(pageSource, /aria-pressed=\{draftCategoryFilter === category\.label\}/);
  assert.match(cssSource, /\.invoice-category-card\.active\s*\{[^}]*border:\s*2px solid #[0-9a-f]{6}/i);
  assert.match(cssSource, /\.invoice-category-card\.active::after\s*\{[^}]*content:\s*"✓"/);
});

test("monthly and arrears KPI sources stay independent from the deduplicated union", async () => {
  const pageSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");

  assert.match(pageSource, /const monthOverdueAmount = monthOverdueInvoices\.reduce/);
  assert.match(pageSource, /const arrearsTotal = arrearsInvoices\.reduce/);
  assert.match(pageSource, /const allVisibleInvoices = mergeUniqueInvoices\(currentMonthInvoices, arrearsInvoices\)/);
  assert.match(pageSource, /Mostrate \{filteredInvoices\.length\} di \{invoiceSearchScope\.length\} fatture/);
  assert.match(pageSource, /const invoiceSearchScope = invoicesForView/);
  assert.match(pageSource, /setStatusFilter\("all"\)[\s\S]*setSupplierSearch\(""\)/);
});

test("dashboard reminder, monthly counters, and chart bars use shared status and real amounts", async () => {
  const dashboardSource = await readFile(new URL("../src/pages/DashboardPage.jsx", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");

  assert.match(dashboardSource, /const allOverdueInvoices = invoices\.filter/);
  assert.match(dashboardSource, /const dueInvoices = currentMonthInvoices\.filter\(isInvoiceUnpaid\)/);
  assert.match(dashboardSource, /const dueSoonInvoices = invoices[\s\S]*?\.filter\(\(invoice\) => isInvoiceUrgent\(invoice, today\)\)/);
  assert.match(dashboardSource, /<span>Di cui scadute<\/span>/);
  assert.match(dashboardSource, /const criticalInvoices = \[\.\.\.dueInvoices\]/);
  assert.match(dashboardSource, /overdue \? "overdue" : `due/);
  assert.match(dashboardSource, /height: `\$\{\(revenue \/ trendMax\) \* 100\}%`/);
  assert.match(dashboardSource, /height: `\$\{\(expenses \/ trendMax\) \* 100\}%`/);
  assert.match(dashboardSource, /title=\{`\$\{item\.month\}: ricavi \$\{formatEuro\(revenue\)\} · costi \$\{formatEuro\(expenses\)\}`\}/);
  assert.match(appSource, /const revH = \(revenue \/ trendMax\) \* 100/);
  assert.match(appSource, /const costH = \(expenses \/ trendMax\) \* 100/);
  assert.match(cssSource, /\.invoice-critical-item\.due\.urgent\s*\{[^}]*background:\s*#fff0dc/);
  assert.match(cssSource, /\.invoice-critical-item\.due\s*\{[^}]*background:\s*#fbf6ef/);
});

test("due includes overdue balances once and uses the remaining balance for partial payments", () => {
  const octoberToday = new Date(2026, 9, 13, 12);
  const invoices = [
    { id: 1, status: "pending", due_date: "2026-07-05", total: 120, linked_amount: 0 },
    { id: 2, status: "pending", due_date: "2026-10-16", total: 100, linked_amount: 40 },
    { id: 3, status: "paid", due_date: "2026-10-10", total: 80, linked_amount: 80 },
    { id: 4, status: "pending", due_date: "2026-10-25", total: 44, linked_amount: 0 },
  ];
  const due = filterInvoiceList(invoices, {
    statusFilter: "due",
    month: "2026-10",
    today: octoberToday,
  });
  const octoberInvoices = invoices.filter((invoice) => invoice.due_date.startsWith("2026-10"));
  const overdue = filterInvoiceList(octoberInvoices, {
    statusFilter: "overdue",
    month: "2026-10",
    today: octoberToday,
  });
  const octoberPayable = invoices.filter(
    (invoice) => invoice.due_date.startsWith("2026-10") && isInvoiceUnpaid(invoice)
  );
  const octoberDueTab = filterInvoiceList(octoberPayable, {
    statusFilter: "due",
    month: "2026-10",
    today: octoberToday,
  });

  assert.deepEqual(due.map((invoice) => invoice.id), [1, 2, 4]);
  assert.deepEqual(overdue, []);
  assert.deepEqual(octoberDueTab.map((invoice) => invoice.id), [2, 4]);
  assert.equal(octoberPayable.length, 2);
  assert.equal(octoberPayable.reduce((sum, item) => sum + getInvoiceRemainingAmount(item), 0), 104);
  assert.equal(invoices.filter((invoice) => invoice.status === "paid").length + octoberPayable.length, 3);
  assert.equal(
    filterInvoiceList(invoices, {
      statusFilter: "year-overdue",
      month: "2026-10",
      today: octoberToday,
    }).length,
    1
  );
});

test("Dashboard and PDF use the same unpaid invoice classification and remaining balances", async () => {
  const dashboardSource = await readFile(new URL("../src/pages/DashboardPage.jsx", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const invoicesSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");

  assert.match(dashboardSource, /const dueInvoices = currentMonthInvoices\.filter\(isInvoiceUnpaid\)/);
  assert.match(dashboardSource, /const criticalInvoices = \[\.\.\.dueInvoices\]/);
  assert.match(appSource, /const unpaidInvoices = currentMonthInvoices\.filter\(isInvoiceUnpaid\)/);
  assert.match(appSource, /unpaidTotal = unpaidInvoices\.reduce\([\s\S]*?getInvoiceRemainingAmount\(invoice\)/);
  assert.match(appSource, /const overdueInvoices = unpaidInvoices\.filter\([\s\S]*?isInvoiceOverdue\(invoice\)/);
  assert.match(appSource, /Di cui scadute: \$\{overdueInvoices\.length\}/);
  assert.match(appSource, /isInvoiceInDueMonth\(invoice, month\) && isInvoiceUnpaid\(invoice\)/);
  assert.match(invoicesSource, /const monthDueInvoices = currentMonthInvoices\.filter\(isInvoiceUnpaid\)/);
  assert.match(invoicesSource, /const monthOverdueInvoices = currentMonthInvoices\.filter\([\s\S]*?isInvoiceOverdue\(invoice, today\) && isInvoiceUnpaid\(invoice\)/);
});