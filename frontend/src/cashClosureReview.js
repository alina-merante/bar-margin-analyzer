const REVIEW_FIELDS = [
  "date",
  "closure_number",
  "total_amount",
  "cash_amount",
  "card_amount",
];

export function createCashClosureReviewForm(review) {
  return {
    date: review.date || "",
    closure_number: review.closure_number || "",
    total_amount: review.total_amount ?? "",
    cash_amount: review.cash_amount ?? "",
    card_amount: review.card_amount ?? "",
  };
}

export function buildCashClosureCorrections(review, form) {
  const original = createCashClosureReviewForm(review);
  return Object.fromEntries(
    REVIEW_FIELDS.filter((field) => form[field] !== original[field]).map((field) => [
      field,
      form[field] === "" ? null : form[field],
    ])
  );
}

function amountToCents(value) {
  if (value === null || value === undefined || value === "") return null;
  const match = String(value).trim().match(/^(\d*)(?:\.(\d{0,2}))?$/);
  if (!match || (!match[1] && !match[2])) return null;
  const cents = Number(match[1] || 0) * 100 + Number((match[2] || "").padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

export function validateCashClosurePayments(total, cash, card) {
  const totalCents = amountToCents(total);
  const cashCents = amountToCents(cash);
  const cardCents = amountToCents(card);

  if (totalCents === null || cashCents === null || cardCents === null) {
    return {
      exceedsTotal: false,
      incomplete: true,
      unallocatedCents: null,
    };
  }

  const unallocatedCents = totalCents - cashCents - cardCents;
  return {
    exceedsTotal: unallocatedCents < 0,
    incomplete: false,
    unallocatedCents: unallocatedCents > 0 ? unallocatedCents : null,
  };
}
