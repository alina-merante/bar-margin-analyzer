export function validateInvoiceAmounts(totalValue, vatValue) {
  const total = Number(totalValue);
  const vat = Number(vatValue);

  if (!Number.isFinite(total) || !Number.isFinite(vat)) {
    return "Inserisci importi validi e finiti per totale e IVA.";
  }

  if (total <= 0) {
    return "Il totale della fattura deve essere maggiore di zero.";
  }

  if (vat < 0) {
    return "L'IVA non può essere negativa.";
  }

  if (vat > total) {
    return "L'IVA non può essere superiore al totale della fattura.";
  }

  return "";
}

function isValidIsoDate(value) {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return false;

  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [
    31,
    leapYear ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];

  return day >= 1 && day <= daysInMonth[month - 1];
}

export function validateInvoiceDates(issueDate, dueDate) {
  if (!issueDate) return "Inserisci una data fattura valida con anno a quattro cifre.";
  if (!dueDate) return "Inserisci una data di scadenza valida con anno a quattro cifre.";
  if (!isValidIsoDate(issueDate)) {
    return "La data fattura non è valida: usa un anno a quattro cifre.";
  }
  if (!isValidIsoDate(dueDate)) {
    return "La data di scadenza non è valida: usa un anno a quattro cifre.";
  }
  if (dueDate < issueDate) {
    return "La data di scadenza non può precedere la data fattura.";
  }

  return "";
}
