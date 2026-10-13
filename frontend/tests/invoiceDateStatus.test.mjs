import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  formatCivilDateDMY,
  formatDayAgeLabel,
  getCivilDateAgeInDays,
  getCalendarDate,
  getInvoiceDaysUntilDue,
  getInvoiceDateStatus,
  getReminderToneForAge,
  getTimestampAgeInLocalDays,
  isInvoiceDue,
  isInvoiceInDueMonth,
  isInvoiceOverdue,
  isInvoiceArrearsBeforeMonth,
  isInvoiceUrgent,
  isCurrentCalendarMonth,
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

test("dashboard shows today reminders only in the current calendar month", async () => {
  const october = new Date(2026, 9, 13, 18, 0);
  assert.equal(isCurrentCalendarMonth("2026-10", october), true);
  assert.equal(isCurrentCalendarMonth("2026-07", october), false);
  assert.equal(isCurrentCalendarMonth("2026-11", october), false);

  const julyInvoices = [
    { supplier: "vvvvv", invoice_number: "44", total: 50, status: "pending", due_date: "2026-07-12" },
    { supplier: "aaaaa", invoice_number: "12", total: 120, status: "pending", due_date: "2026-07-05" },
  ];
  const invoicesRequiringPayment = julyInvoices.filter(
    (item) => isInvoiceDue(item, october) || isInvoiceOverdue(item, october)
  );
  assert.deepEqual(
    invoicesRequiringPayment.map(({ supplier, invoice_number }) => `${supplier} / ${invoice_number}`),
    ["vvvvv / 44", "aaaaa / 12"]
  );
  assert.ok(invoicesRequiringPayment.every((item) => isInvoiceOverdue(item, october)));

  const dashboardSource = await readFile(
    new URL("../src/pages/DashboardPage.jsx", import.meta.url),
    "utf8"
  );
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");
  assert.match(dashboardSource, /isCurrentCalendarMonth\(month, today\)/);
  assert.match(dashboardSource, /\{showTodayReminders \? \([\s\S]*?<section className="daily-reminder-card">/);
  assert.match(dashboardSource, /const dueInvoices = currentMonthInvoices\.filter\(isInvoiceUnpaid\)/);
  assert.match(dashboardSource, /const criticalInvoices = \[\.\.\.dueInvoices\][\s\S]*?\.sort\(/);
  assert.match(dashboardSource, /overdue \? "overdue" : `due/);
  assert.match(cssSource, /\.bar\.zero-bar\s*\{\s*min-height:\s*3px;/);
  assert.match(dashboardSource, /title=\{`\$\{item\.month\}: ricavi \$\{formatEuro\(revenue\)\} · costi \$\{formatEuro\(expenses\)\}`\}/);
});

test("a paid invoice with a past due date is neither overdue nor due", () => {
  const paidInvoice = { ...invoice("2026-10-01"), status: "paid" };

  assert.equal(getInvoiceDateStatus(paidInvoice, today), "paid");
  assert.equal(isInvoiceOverdue(paidInvoice, today), false);
  assert.equal(isInvoiceDue(paidInvoice, today), false);
});

test("invoice status and urgency use civil days, including the five-day boundary", () => {
  const today = new Date(2026, 9, 13, 23, 45);
  const makeInvoice = (dueDate) => ({ status: "pending", due_date: dueDate });
  const overdueYesterday = makeInvoice("2026-10-12");
  const dueToday = makeInvoice("2026-10-13");
  const urgentFiveDays = makeInvoice("2026-10-18");
  const notUrgentSixDays = makeInvoice("2026-10-19");

  assert.equal(getInvoiceDateStatus({ ...dueToday, status: "paid" }, today), "paid");
  assert.equal(getInvoiceDateStatus(overdueYesterday, today), "overdue");
  assert.equal(getInvoiceDateStatus(dueToday, today), "due");
  assert.equal(getInvoiceDaysUntilDue(dueToday, today), 0);
  assert.equal(getInvoiceDaysUntilDue(urgentFiveDays, today), 5);
  assert.equal(getInvoiceDaysUntilDue(notUrgentSixDays, today), 6);
  assert.equal(isInvoiceUrgent(overdueYesterday, today), false);
  assert.equal(isInvoiceUrgent(dueToday, today), true);
  assert.equal(isInvoiceUrgent(urgentFiveDays, today), true);
  assert.equal(isInvoiceUrgent(notUrgentSixDays, today), false);
});

test("due-soon window includes the selected month's last day, not the next month", () => {
  assert.equal(isInvoiceInDueMonth(invoice("2026-10-31"), "2026-10"), true);
  assert.equal(isInvoiceInDueMonth(invoice("2026-11-01"), "2026-10"), false);
  assert.equal(isInvoiceDue(invoice("2026-10-31"), today), true);
});

test("arrears are overdue invoices in earlier months of the selected year only", () => {
  const julyInvoice = invoice("2026-07-12");
  const octoberInvoice = invoice("2026-10-01");
  const priorYearInvoice = invoice("2025-12-31");
  const julyFirst = new Date(2026, 6, 1, 12);

  assert.equal(isInvoiceInDueMonth(julyInvoice, "2026-07"), true);
  assert.equal(isInvoiceArrearsBeforeMonth(julyInvoice, "2026-07", today), false);
  assert.equal(isInvoiceArrearsBeforeMonth(julyInvoice, "2026-10", today), true);
  assert.equal(isInvoiceArrearsBeforeMonth(octoberInvoice, "2026-10", today), false);
  assert.equal(isInvoiceArrearsBeforeMonth(priorYearInvoice, "2026-10", today), false);
  assert.equal(isInvoiceArrearsBeforeMonth(julyInvoice, "2026-07", julyFirst), false);
});

test("arrears stay within the selected year across the December-to-January boundary", () => {
  const today = new Date(2027, 1, 10, 12);
  const decemberInvoice = invoice("2026-12-31");
  const januaryInvoice = invoice("2027-01-31");

  assert.equal(isInvoiceOverdue(decemberInvoice, today), true);
  assert.equal(isInvoiceArrearsBeforeMonth(decemberInvoice, "2027-02", today), false);
  assert.equal(isInvoiceArrearsBeforeMonth(januaryInvoice, "2027-01", today), false);
  assert.equal(isInvoiceArrearsBeforeMonth(januaryInvoice, "2027-02", today), true);
});

test("civil date formatting and reminder age stay stable across Rome, western, and UTC timezones", async () => {
  const moduleUrl = new URL("../src/invoiceDateStatus.js", import.meta.url).href;
  const script = `
    import {
      formatCivilDateDMY,
      formatDayAgeLabel,
      getCalendarDate,
      getCivilDateAgeInDays,
      getReminderToneForAge,
      getTimestampAgeInLocalDays,
      isInvoiceDue,
      isInvoiceOverdue,
    } from ${JSON.stringify(moduleUrl)};
    const dueDate = getCalendarDate("2026-10-02");
    const invoice = { status: "pending", due_date: "2026-10-02" };
    const today = new Date(2026, 9, 2, 23, 0);
    const reminderToday = new Date(2026, 9, 7, 12, 0);
    const civilTodayAge = getCivilDateAgeInDays("2026-10-07", reminderToday);
    const civilYesterdayAge = getCivilDateAgeInDays("2026-10-06", reminderToday);
    const timestampAge = getTimestampAgeInLocalDays("2026-10-07T00:30:00Z", reminderToday);
    console.log(JSON.stringify({
      calendarDate: [dueDate.getFullYear(), dueDate.getMonth() + 1, dueDate.getDate()],
      due: isInvoiceDue(invoice, today),
      overdue: isInvoiceOverdue(invoice, today),
      pdfDate: formatCivilDateDMY("2026-07-10"),
      dashboardDate: formatCivilDateDMY("2026-10-07"),
      todayLabel: formatDayAgeLabel(civilTodayAge),
      yesterdayLabel: formatDayAgeLabel(civilYesterdayAge),
      todayTone: getReminderToneForAge(civilTodayAge),
      yesterdayTone: getReminderToneForAge(civilYesterdayAge),
      timestampAge,
      missingTimestampAge: getTimestampAgeInLocalDays(null, reminderToday),
    }));
  `;
  for (const timezone of ["Europe/Rome", "America/Los_Angeles", "UTC"]) {
    const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
      encoding: "utf8",
      env: { ...process.env, TZ: timezone },
    });

    assert.equal(result.status, 0, `${timezone}: ${result.stderr}`);
    assert.deepEqual(JSON.parse(result.stdout), {
      calendarDate: [2026, 10, 2],
      due: true,
      overdue: false,
      pdfDate: "10/07/2026",
      dashboardDate: "07/10/2026",
      todayLabel: "OGGI",
      yesterdayLabel: "IERI",
      todayTone: "neutral",
      yesterdayTone: "neutral",
      timestampAge: timezone === "America/Los_Angeles" ? 1 : 0,
      missingTimestampAge: null,
    });
  }

  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const dashboardSource = await readFile(new URL("../src/pages/DashboardPage.jsx", import.meta.url), "utf8");
  assert.match(appSource, /formatCivilDateDMY\(invoice\.due_date\)/);
  assert.match(dashboardSource, /formatCivilDateDMY\(latestBankTransactionDate\)/);
  assert.match(dashboardSource, /daysAgoLabel\(latestBankTransactionDate, true\)/);
  assert.match(dashboardSource, /getReminderTone\(latestBankTransactionDate, "warning", true\)/);
  assert.match(dashboardSource, /formatCivilDateDMY\(latestPosUploadDate\)/);
  assert.match(dashboardSource, /formatCivilDateDMY\(\s*firstDueInvoice\.due_date\s*\)/);
  assert.match(dashboardSource, /formatCivilDateDMY\(invoice\.due_date\)/);
  assert.match(dashboardSource, /weekday: "long"[\s\S]*?formatCivilDateDMY\(today\)/);
  assert.doesNotMatch(dashboardSource, /formatShortDate|month: "long",\s*\n\s*day: "2-digit"/);
  assert.match(appSource, /latestPosUploadDateIsCivil = Boolean\(overview\?\.latest_cash_closure_date\)/);
});

test("dashboard reminder dates include padded day, month, and source year across calendar boundaries", () => {
  const moduleUrl = new URL("../src/invoiceDateStatus.js", import.meta.url).href;
  const script = `
    import { formatCivilDateDMY } from ${JSON.stringify(moduleUrl)};
    console.log(JSON.stringify(
      ["2025-12-31", "2026-01-05", "2026-07-15", "0026-03-04"].map(formatCivilDateDMY)
    ));
  `;
  for (const timezone of ["Europe/Rome", "America/Los_Angeles", "UTC"]) {
    const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
      encoding: "utf8",
      env: { ...process.env, TZ: timezone },
    });

    assert.equal(result.status, 0, `${timezone}: ${result.stderr}`);
    assert.deepEqual(
      JSON.parse(result.stdout),
      ["31/12/2025", "05/01/2026", "15/07/2026", "04/03/0026"],
      timezone
    );
  }
});

test("invoice list, dashboard, and PDF share calendar-date helpers", async () => {
  const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const invoicesSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const dashboardSource = await readFile(new URL("../src/pages/DashboardPage.jsx", import.meta.url), "utf8");

  assert.match(appSource, /getInvoiceDateStatus\(invoice\)/);
  assert.match(appSource, /isInvoiceArrearsBeforeMonth\(invoice, month\)/);
  assert.match(invoicesSource, /getInvoiceDateStatus\(invoice, today\)/);
  assert.match(invoicesSource, /isInvoiceArrearsBeforeMonth\(invoice, month, today\)/);
  assert.match(dashboardSource, /invoices\.filter\([\s\S]*?isInvoiceOverdue\(invoice, today\) && isInvoiceUnpaid\(invoice\)/);
  assert.doesNotMatch(
    `${appSource}\n${invoicesSource}\n${dashboardSource}`,
    /new Date\(invoice\.due_date\)\s*</
  );
});

test("invoice table separates temporal status labels from payment status", async () => {
  const invoicesSource = await readFile(new URL("../src/pages/InvoicesPage.jsx", import.meta.url), "utf8");
  const cssSource = await readFile(new URL("../src/App.css", import.meta.url), "utf8");
  const paymentCell = invoicesSource.match(
    /<div className="invoice-action-cell invoice-payment-cell">([\s\S]*?)<\/div>\s*<div className="invoice-action-cell">/
  )?.[1];

  assert.ok(paymentCell, "payment cell should be present");
  assert.match(invoicesSource, /status === "overdue"[\s\S]*?invoice-due-status overdue">Scaduta/);
  assert.match(invoicesSource, /status === "due"[\s\S]*?invoice-due-status due\$\{urgent \? " urgent" : ""\}/);
  assert.match(paymentCell, /invoice-payment-paid">✓ Pagata/);
  assert.match(paymentCell, /invoice-reconcile-btn[\s\S]*?Abbina pagamento/);
  assert.match(paymentCell, /Pagato \{formatEuro\(linkedAmount\)\} · Residuo/);
  assert.doesNotMatch(paymentCell, /Scaduta|In scadenza/);
  assert.match(cssSource, /\.invoice-clean-table-row\.overdue\s*\{/);
  assert.match(cssSource, /\.invoice-clean-table-row\.due\s*\{/);
  assert.match(cssSource, /\.invoice-clean-table-row\.paid\s*\{/);
  assert.match(cssSource, /\.invoice-due-status\.overdue\s*\{/);
  assert.match(cssSource, /\.invoice-due-status\.due\s*\{/);
  assert.match(cssSource, /\.invoice-due-status\.due\.urgent\s*\{/);
});