import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

const TIMEZONES = ["UTC", "Europe/Rome", "America/Los_Angeles"];
const moduleUrl = new URL("../src/historyDates.js", import.meta.url).href;

function runInTimezone(timezone, script) {
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    env: { ...process.env, TZ: timezone },
  });

  assert.equal(result.status, 0, `${timezone}: ${result.stderr}`);
  return JSON.parse(result.stdout);
}

test("UTC timestamps show the user's local day, with Z and +00:00 equivalent", () => {
  const script = `
    import { formatTimestampDate, formatHistoryDate } from ${JSON.stringify(moduleUrl)};
    console.log(JSON.stringify({
      z: formatTimestampDate("2026-09-30T23:30:00Z"),
      offset: formatTimestampDate("2026-09-30T23:30:00+00:00"),
      viaKind: formatHistoryDate("2026-09-30T23:30:00+00:00", "timestamp"),
      sameInstant:
        new Date("2026-09-30T23:30:00Z").getTime() ===
        new Date("2026-09-30T23:30:00+00:00").getTime(),
      invalid: formatTimestampDate("not-a-date"),
      missing: formatTimestampDate(null),
    }));
  `;
  const expectedDay = {
    UTC: "30/09/2026",
    "Europe/Rome": "01/10/2026",
    "America/Los_Angeles": "30/09/2026",
  };

  for (const timezone of TIMEZONES) {
    const out = runInTimezone(timezone, script);
    assert.equal(out.z, expectedDay[timezone], timezone);
    assert.equal(out.offset, expectedDay[timezone], timezone);
    assert.equal(out.viaKind, expectedDay[timezone], timezone);
    assert.equal(out.sameInstant, true);
    assert.equal(out.invalid, "-");
    assert.equal(out.missing, "-");
  }
});

test("civil dates never change day across timezones and reject datetime prefixes", () => {
  const script = `
    import { formatCivilDate, isCivilDateString } from ${JSON.stringify(moduleUrl)};
    console.log(JSON.stringify({
      civil: formatCivilDate("2026-10-01"),
      datetimePrefix: formatCivilDate("2026-09-30T23:30:00Z"),
      isCivil: isCivilDateString("2026-10-01"),
      isCivilDatetime: isCivilDateString("2026-10-01T00:00:00Z"),
    }));
  `;

  for (const timezone of TIMEZONES) {
    assert.deepEqual(runInTimezone(timezone, script), {
      civil: "01/10/2026",
      datetimePrefix: "-",
      isCivil: true,
      isCivilDatetime: false,
    }, timezone);
  }
});

test("mixed history ordering is consistent across timezones", () => {
  const script = `
    import { compareHistoryEntriesDesc } from ${JSON.stringify(moduleUrl)};
    const entries = [
      { id: "invoice-issued-oct-01", dateValue: "2026-10-01", dateKind: "civil" },
      { id: "upload-sep-30-late", dateValue: "2026-09-30T23:30:00+00:00", dateKind: "timestamp" },
      { id: "bank-effective-sep-30", dateValue: "2026-09-30", dateKind: "civil" },
      { id: "upload-sep-29", dateValue: "2026-09-29T08:00:00+00:00", dateKind: "timestamp" },
      { id: "invoice-issued-sep-15", dateValue: "2026-09-15", dateKind: "civil" },
      { id: "no-date", dateValue: null, dateKind: "civil" },
    ];
    console.log(JSON.stringify([...entries].sort(compareHistoryEntriesDesc).map((entry) => entry.id)));
  `;
  const expected = {
    UTC: [
      "invoice-issued-oct-01",
      "upload-sep-30-late",
      "bank-effective-sep-30",
      "upload-sep-29",
      "invoice-issued-sep-15",
      "no-date",
    ],
    // 23:30Z on 30/09 is already 01/10 in Rome, so it ties with the civil 01/10
    // invoice and wins on its instant, matching the day it is displayed under.
    "Europe/Rome": [
      "upload-sep-30-late",
      "invoice-issued-oct-01",
      "bank-effective-sep-30",
      "upload-sep-29",
      "invoice-issued-sep-15",
      "no-date",
    ],
    "America/Los_Angeles": [
      "invoice-issued-oct-01",
      "upload-sep-30-late",
      "bank-effective-sep-30",
      "upload-sep-29",
      "invoice-issued-sep-15",
      "no-date",
    ],
  };

  for (const timezone of TIMEZONES) {
    assert.deepEqual(runInTimezone(timezone, script), expected[timezone], timezone);
  }
});

test("ordering follows the displayed day in every timezone", () => {
  const script = `
    import { compareHistoryEntriesDesc, formatHistoryDate } from ${JSON.stringify(moduleUrl)};
    const entries = [
      { dateValue: "2026-10-01", dateKind: "civil" },
      { dateValue: "2026-09-30T23:30:00+00:00", dateKind: "timestamp" },
      { dateValue: "2026-09-30", dateKind: "civil" },
      { dateValue: "2026-09-29T08:00:00+00:00", dateKind: "timestamp" },
    ];
    const toKey = (label) => label.split("/").reverse().join("-");
    const labels = [...entries]
      .sort(compareHistoryEntriesDesc)
      .map((entry) => toKey(formatHistoryDate(entry.dateValue, entry.dateKind)));
    console.log(JSON.stringify({ labels, sorted: [...labels].sort().reverse() }));
  `;

  for (const timezone of TIMEZONES) {
    const { labels, sorted } = runInTimezone(timezone, script);
    assert.deepEqual(labels, sorted, timezone);
  }
});

test("UploadPage history uses issue_date for invoices and explicit date kinds", async () => {
  const source = await readFile(new URL("../src/pages/UploadPage.jsx", import.meta.url), "utf8");
  const invoiceEntry = source.slice(source.indexOf("const invoiceEntries"));

  assert.match(invoiceEntry, /dateValue: invoice\.issue_date/);
  assert.match(invoiceEntry, /formatHistoryEntryDate\(invoice\.issue_date, HISTORY_DATE_KIND_CIVIL\)/);
  assert.doesNotMatch(invoiceEntry, /dateValue: invoice\.due_date/);
  assert.match(source, /\.sort\(compareHistoryEntriesDesc\)/);
  assert.doesNotMatch(source, /new Date\(b\.dateValue/);
  assert.doesNotMatch(source, /\^\(\\d\{4\}\)-\(\\d\{2\}\)-\(\\d\{2\}\)\//);
});
