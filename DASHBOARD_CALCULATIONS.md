# Dashboard calculations

This document describes how each dashboard section is computed.

## 1. Revenue

Revenue is the sum of all daily cash closure totals in the selected period.

- Source: DailyCashClosure.total_amount
- Period filter: closure date is included when it is within the selected month
- Formula:
  - Revenue = sum(DailyCashClosure.total_amount)

## 2. Costs

Costs are counted only when an invoice is actually reconciled with a payment and the invoice status is paid.

Rules:
- A standalone bank transaction does not create a cost by itself.
- A standalone invoice does not create a cost until it is paid.
- If both an invoice and a reconciled bank movement exist, the cost is counted once.

Calculation:
- For each invoice with status = paid and at least one linked payment in the period:
  - cost contribution = invoice.total + invoice.vat
- Total costs = sum of those contributions for the selected period

## 3. Operating margin

Operating margin is the difference between revenue and costs.

- Formula:
  - Operating margin = Revenue - Costs

## 4. P&L trend

The trend endpoint returns monthly values for the last N months, including the selected month.

Each month uses the same logic:
- Revenue = sum of cash closure totals for that month
- Costs = sum of paid and reconciled invoices for that month
- Profit = Revenue - Costs

## 5. Insights

Insights compare the selected month with the previous month.

They include:
- Revenue change percentage
- Expenses change percentage
- Profit change percentage
- Top expense category change percentage
- Share of the top supplier expense

## 6. Expenses by category

This section shows the distribution of costs by expense category.

Current implementation uses the invoice-based cost model, so categories are derived from the reconciled paid invoice flow.

## 7. Expenses by supplier

This section shows the distribution of costs by supplier.

Current implementation uses the invoice-based cost model, so suppliers come from reconciled paid invoices.

## 8. Invoice summary

This section is not part of the P&L formula; it is a summary of invoice records.

Displayed values:
- Total invoices
- Pending invoices
- Paid invoices
- Total pending amount
- Total paid amount

## 9. Payments by method

This section groups payments by payment method for the selected month.

- Source: Payment records
- Aggregation: sum of Payment.amount grouped by Payment.method
