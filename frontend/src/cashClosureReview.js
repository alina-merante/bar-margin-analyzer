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
