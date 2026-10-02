function createCalendarDate(year, month, day) {
  const date = new Date(0);
  date.setFullYear(year, month - 1, day);
  date.setHours(12, 0, 0, 0);

  if (
    date.getFullYear() !== year ||
    date.getMonth() + 1 !== month ||
    date.getDate() !== day
  ) {
    return null;
  }

  return date;
}

export function getCalendarDate(value) {
  if (value === null || value === undefined || value === "") return null;

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null;
    return createCalendarDate(value.getFullYear(), value.getMonth() + 1, value.getDate());
  }

  if (typeof value === "string") {
    const dateOnlyMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnlyMatch) {
      return createCalendarDate(
        Number(dateOnlyMatch[1]),
        Number(dateOnlyMatch[2]),
        Number(dateOnlyMatch[3])
      );
    }
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return createCalendarDate(parsed.getFullYear(), parsed.getMonth() + 1, parsed.getDate());
}

function getCalendarDateKey(value) {
  const date = getCalendarDate(value);
  if (!date) return "";

  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function getInvoiceDueMonthKey(dueDate) {
  return getCalendarDateKey(dueDate).slice(0, 7);
}

export function isInvoiceInDueMonth(invoice, month) {
  return getInvoiceDueMonthKey(invoice?.due_date) === month;
}

export function isInvoiceOverdue(invoice, today = new Date()) {
  if (invoice?.status === "paid" || !invoice?.due_date) return false;

  const dueDate = getCalendarDateKey(invoice.due_date);
  const todayDate = getCalendarDateKey(today);
  return Boolean(dueDate && todayDate && dueDate < todayDate);
}

export function isInvoiceDue(invoice, today = new Date()) {
  if (invoice?.status === "paid") return false;
  if (!invoice?.due_date) return true;

  const dueDate = getCalendarDateKey(invoice.due_date);
  const todayDate = getCalendarDateKey(today);
  return Boolean(dueDate && todayDate && dueDate >= todayDate);
}

export function getInvoiceDateStatus(invoice, today = new Date()) {
  if (invoice?.status === "paid") return "paid";
  return isInvoiceOverdue(invoice, today) ? "overdue" : "due";
}

export function isInvoiceOverdueInCurrentYear(invoice, today = new Date()) {
  if (invoice?.status === "paid" || !invoice?.due_date) return false;

  const dueDate = getCalendarDate(invoice.due_date);
  const todayCalendarDate = getCalendarDate(today);
  if (!dueDate || !todayCalendarDate) return false;

  const dueDateKey = getCalendarDateKey(dueDate);
  const todayDateKey = getCalendarDateKey(todayCalendarDate);
  return dueDate.getFullYear() === todayCalendarDate.getFullYear() && dueDateKey < todayDateKey;
}