import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  getCalendarDate,
  getInvoiceDateStatus,
  isInvoiceDue,
  isInvoiceInDueMonth,
  isInvoiceOverdue,
  isInvoiceOverdueInCurrentYear,
} from "../src/invoiceDateStatus.js";

const today = new Date(2026, 9, 2, 15, 30);
const invoice = (due_date) => ({ status: "pending", due_date });

test("yesterday is overdue, while today and tomorrow are still due", () => {
  assert.equal(getInvoiceDateStatus(invoice("2026-10-01"), today), "overdue");
  assert.equal(isInvoiceOverdue(invoice("2026-10-01"), today), true);
  assert.equal(isInvoiceDue(invoice("2026-10-01"), today), false);

  assert.equal(getInvoiceDateStatus(invoice("2026-10-02"), today), "due");
  assert.equal(isInvoiceOverdue(invoice("2026-10-02"), today), false);
  assert.equal(isInvoiceDue(invoice("2026-10-02"), today), true);

  assert.equal(getInvoiceDateStatus(invoice("2026-10-03"), today), "due");
  assert.equal(isInvoiceDue(invoice("2026-10-03"), today), true);
});

test("due-soon window includes the selected month's last day, not the next month", () => {
  assert.equal(isInvoiceInDueMonth(invoice("2026-10-31"), "2026-10"), true);
  assert.equal(isInvoiceInDueMonth(invoice("2026-11-01"), "2026-10"), false);
  assert.equal(isInvoiceDue(invoice("2026-10-31"), today), true);
});

test("an overdue invoice in the current month is also a current-year arrear", () => {
  const overdueThisMonth = invoice("2026-10-01");

  assert.equal(isInvoiceInDueMonth(overdueThisMonth, "2026-10"), true);
  assert.equal(isInvoiceOverdue(overdueThisMonth, today), true);
  assert.equal(isInvoiceOverdueInCurrentYear(overdueThisMonth, today), true);
  assert.equal(isInvoiceOverdueInCurrentYear(invoice("2025-12-31"), today), false);
});

test("date-only API values keep their calendar day in a western timezone", () => {
  const moduleUrl = new URL("../src/invoiceDateStatus.js", import.meta.url).href;
  const script = `
    import { getCalendarDate, isInvoiceDue, isInvoiceOverdue } from ${JSON.stringify(moduleUrl)};
    const dueDate = getCalendarDate("2026-10-02");
    const invoice = { status: "pending", due_date: "2026-10-02" };
    const today = new Date(2026, 9, 2, 23, 0);
    console.log(JSON.stringify({
      calendarDate: [dueDate.getFullYear(), dueDate.getMonth() + 1, dueDate.getDate()],
      due: isInvoiceDue(invoice, today),
      overdue: isInvoiceOverdue(invoice, today),
    }));
  `;
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    env: { ...process.env, TZ: "America/Los_Angeles" },
  });

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    calendarDate: [2026, 10, 2],
    due: true,
    overdue: false,
  });
});

test("invoice list, dashboard, and PDF share calendar-date helpers", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const invoicesSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const dashboardSource = await readFile(new URL("../src/pages/DashboardPage.jsx", import.meta.url), "utf8");

  assert.match(appSource, /isInvoiceOverdue\(invoice\)/);
  assert.match(appSource, /isInvoiceOverdueInCurrentYear/);
  assert.match(invoicesSource, /getInvoiceDateStatus\(invoice\)/);
  assert.match(invoicesSource, /isInvoiceOverdueInCurrentYear/);
  assert.match(dashboardSource, /currentMonthInvoices\.filter\(isInvoiceOverdue\)/);
  assert.doesNotMatch(
    `${appSource}\n${invoicesSource}\n${dashboardSource}`,
    /new Date\(invoice\.due_date\)\s*</
  );
});