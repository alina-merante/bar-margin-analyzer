import { formatCivilDateDMY, getCalendarDate } from "./invoiceDateStatus.js";

export const HISTORY_DATE_KIND_CIVIL = "civil";
export const HISTORY_DATE_KIND_TIMESTAMP = "timestamp";

const CIVIL_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function isCivilDateString(value) {
  return typeof value === "string" && CIVIL_DATE_PATTERN.test(value);
}

// Civil dates (YYYY-MM-DD) have no timezone and must never be shifted.
export function formatCivilDate(value) {
  if (!isCivilDateString(value)) return "-";
  return formatCivilDateDMY(value);
}

// Timestamps are real instants (ISO 8601 with Z/offset) shown as the user's local day.
export function formatTimestampDate(value) {
  if (value === null || value === undefined || value === "") return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function formatHistoryDate(value, kind) {
  return kind === HISTORY_DATE_KIND_TIMESTAMP
    ? formatTimestampDate(value)
    : formatCivilDate(value);
}

// Orders by the local calendar day that is displayed; the instant only breaks
// ties between entries on the same day (civil dates carry no time, so they sort last).
export function getHistorySortKey(value, kind) {
  const day = getCalendarDate(value);
  if (!day) return { day: Number.NEGATIVE_INFINITY, instant: 0 };

  const instant =
    kind === HISTORY_DATE_KIND_TIMESTAMP ? new Date(value).getTime() : 0;

  return { day: day.getTime(), instant: Number.isNaN(instant) ? 0 : instant };
}

export function compareHistoryEntriesDesc(a, b) {
  const keyA = getHistorySortKey(a.dateValue, a.dateKind);
  const keyB = getHistorySortKey(b.dateValue, b.dateKind);

  if (keyA.day !== keyB.day) return keyA.day < keyB.day ? 1 : -1;
  if (keyA.instant !== keyB.instant) return keyA.instant < keyB.instant ? 1 : -1;
  return 0;
}
