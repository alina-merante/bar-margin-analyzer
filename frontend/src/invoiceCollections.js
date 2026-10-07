import {
  getInvoiceDateStatus,
  isInvoiceOverdueInCurrentYear,
} from "./invoiceDateStatus.js";

export function mergeUniqueInvoices(...collections) {
  const seenIds = new Set();
  const uniqueInvoices = [];

  for (const collection of collections) {
    for (const invoice of collection) {
      if (invoice?.id != null) {
        if (seenIds.has(invoice.id)) continue;
        seenIds.add(invoice.id);
      }
      uniqueInvoices.push(invoice);
    }
  }

  return uniqueInvoices;
}

export function countInvoicesByCategory(invoices, categoryForInvoice) {
  const counts = new Map();

  for (const invoice of mergeUniqueInvoices(invoices)) {
    const category = categoryForInvoice(invoice);
    if (category) counts.set(category, (counts.get(category) || 0) + 1);
  }

  return counts;
}

export function filterInvoiceList(
  invoices,
  {
    supplierSearch = "",
    statusFilter = "all",
    categoryFilter = "",
    categoryForInvoice,
    today,
  }
) {
  const normalizedSupplierSearch = supplierSearch.trim().toLowerCase();

  return invoices.filter((invoice) => {
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "year-overdue"
        ? isInvoiceOverdueInCurrentYear(invoice, today)
        : getInvoiceDateStatus(invoice, today) === statusFilter);
    const matchesSupplier =
      !normalizedSupplierSearch ||
      invoice.supplier?.toLowerCase().includes(normalizedSupplierSearch);
    const matchesCategory =
      !categoryFilter || categoryForInvoice(invoice) === categoryFilter;

    return matchesStatus && matchesSupplier && matchesCategory;
  });
}