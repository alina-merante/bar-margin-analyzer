import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import UploadPage from "./pages/UploadPage";
import InvoicesPage from "./pages/InvoicesPage";
import DashboardPage from "./pages/DashboardPage";

function getCurrentMonth() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

async function fetchJsonOrThrow(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Errore API (${response.status})`);
  }

  return response.json();
}

export default function App() {
  const [month, setMonth] = useState(getCurrentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [overview, setOverview] = useState({
    pnl_summary: { revenue: 0, expenses: 0, profit: 0 },
  });

  const [invoices, setInvoices] = useState([]);
  const [trend, setTrend] = useState([]);
  const [topProducts, setTopProducts] = useState({ by_quantity: [] });
  const [expensesByCategory, setExpensesByCategory] = useState({ items: [] });
  const [expensesBySupplier, setExpensesBySupplier] = useState({ items: [] });
  const [insights, setInsights] = useState({ insights: [] });

  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);

  const [invoiceUploadMessage, setInvoiceUploadMessage] = useState("");
  const [invoiceUploadError, setInvoiceUploadError] = useState("");
  const [invoiceUploading, setInvoiceUploading] = useState(false);
  const [invoiceDeleteError, setInvoiceDeleteError] = useState("");

  async function loadDashboardData(selectedMonth) {
    const [
      overviewData,
      invoicesData,
      trendData,
      topProductsData,
      expensesByCategoryData,
      expensesBySupplierData,
      insightsData,
    ] = await Promise.all([
      fetchJsonOrThrow(`/api/analytics/overview?month=${selectedMonth}`),
      fetchJsonOrThrow("/api/invoices"),
      fetchJsonOrThrow(`/api/analytics/pnl/trend?months=6`),
      fetchJsonOrThrow(`/api/analytics/top-products?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/expenses-by-category?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/expenses-by-supplier?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/insights?month=${selectedMonth}`),
    ]);

    setOverview(
      overviewData ?? {
        pnl_summary: { revenue: 0, expenses: 0, profit: 0 },
      }
    );

    setInvoices(safeArray(invoicesData));
    setTrend(safeArray(trendData));
    setTopProducts(topProductsData ?? { by_quantity: [] });

    setExpensesByCategory(
      expensesByCategoryData?.items
        ? expensesByCategoryData
        : { items: safeArray(expensesByCategoryData?.top_expense_categories) }
    );

    setExpensesBySupplier(
      expensesBySupplierData?.items
        ? expensesBySupplierData
        : { items: safeArray(expensesBySupplierData?.top_suppliers) }
    );

    setInsights(insightsData ?? { insights: [] });
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError("");
        await loadDashboardData(month);
      } catch (err) {
        console.error(err);

        if (!cancelled) {
          setError("Impossibile caricare i dati.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [month]);

  async function handleUpload(file, type) {
    if (!file) return;

    try {
      setUploading(true);
      setUploadError("");
      setUploadMessage("");

      const formData = new FormData();
      formData.append("file", file);

      const endpoint =
        type === "pos" ? "/api/imports/pos-csv" : "/api/imports/bank-csv";

      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Upload fallito (${response.status})`);
      }

      const result = await response.json();

      setUploadMessage(
        `Import ${type.toUpperCase()} completato: ${
          result.imported_rows ?? 0
        } righe importate.`
      );

      await loadDashboardData(month);
    } catch (err) {
      console.error(err);
      setUploadError("Errore durante l'import del file.");
    } finally {
      setUploading(false);
    }
  }

  async function handleInvoiceDocumentUpload(file) {
    if (!file) return;

    try {
      setInvoiceUploading(true);
      setInvoiceUploadError("");
      setInvoiceUploadMessage("");

      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("/api/invoices/extract", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Upload fattura fallito (${response.status})`);
      }

      const result = await response.json();
      const extractedMonth = result.issue_date?.slice(0, 7) || month;

      setInvoiceUploadMessage(
        `Fattura acquisita: ${result.supplier || "fornitore rilevato"} · ${
          result.invoice_number || "numero non disponibile"
        }`
      );

      if (result.issue_date) {
        setMonth(extractedMonth);
      }

      await loadDashboardData(extractedMonth);
    } catch (err) {
      console.error(err);
      setInvoiceUploadError(
        "Errore durante il caricamento della fattura o nell'estrazione dati."
      );
    } finally {
      setInvoiceUploading(false);
    }
  }

  async function handleCreateManualInvoice(invoiceData) {
    const response = await fetch("/api/invoices", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(invoiceData),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(errorBody || `Creazione fattura fallita (${response.status})`);
    }

    await loadDashboardData(month);
  }

  async function handleDeleteInvoice(invoiceId) {
    if (!invoiceId) return;

    try {
      setInvoiceDeleteError("");

      const response = await fetch(`/api/invoices/delete/${invoiceId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Delete fattura fallito (${response.status})`);
      }

      await loadDashboardData(month);
    } catch (err) {
      console.error(err);
      setInvoiceDeleteError("Errore durante l'eliminazione della fattura.");
    }
  }

  const pendingInvoices = useMemo(
    () => invoices.filter((invoice) => invoice.status === "pending"),
    [invoices]
  );

  const pendingInvoicesAmount = useMemo(
    () =>
      pendingInvoices.reduce(
        (sum, invoice) => sum + (Number(invoice.total) || 0),
        0
      ),
    [pendingInvoices]
  );

  const pnl = overview?.pnl_summary ?? {
    revenue: 0,
    expenses: 0,
    profit: 0,
  };

  const topProductsList = safeArray(topProducts.by_quantity).slice(0, 5);

  const currentMonthInvoices = invoices.filter(
    (invoice) => invoice.issue_date?.slice(0, 7) === month
  );

  const latestInvoiceDate = currentMonthInvoices.length
    ? currentMonthInvoices.map((invoice) => invoice.issue_date).sort().at(-1)
    : null;

  const latestBankUploadDate = expensesBySupplier.items?.length
    ? `${month}-01`
    : null;

  const latestPosUploadDate = topProducts.by_quantity?.length
    ? `${month}-01`
    : null;

  return (
    <BrowserRouter>
      <div className="dashboard-shell">
        <Sidebar
          month={month}
          setMonth={setMonth}
          pendingInvoices={pendingInvoices.length}
        />

        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route
            path="/dashboard"
            element={
              <DashboardPage
                month={month}
                loading={loading}
                error={error}
                pnl={pnl}
                trend={trend}
                topProductsList={topProductsList}
                pendingInvoices={pendingInvoices}
                pendingInvoicesAmount={pendingInvoicesAmount}
                invoices={invoices}
                latestPosUploadDate={latestPosUploadDate}
                latestBankUploadDate={latestBankUploadDate}
              />
            }
          />

          <Route
            path="/invoices"
            element={
              <InvoicesPage
                month={month}
                setMonth={setMonth}
                invoices={invoices}
                invoiceUploadMessage={invoiceUploadMessage}
                invoiceUploadError={invoiceUploadError}
                invoiceUploading={invoiceUploading}
                handleInvoiceDocumentUpload={handleInvoiceDocumentUpload}
                handleDeleteInvoice={handleDeleteInvoice}
                invoiceDeleteError={invoiceDeleteError}
                handleCreateManualInvoice={handleCreateManualInvoice}
              />
            }
          />

          <Route
            path="/upload"
            element={
              <UploadPage
                month={month}
                handleUpload={handleUpload}
                uploading={uploading}
                uploadMessage={uploadMessage}
                uploadError={uploadError}
                latestPosUploadDate={latestPosUploadDate}
                latestBankUploadDate={latestBankUploadDate}
                invoiceCountThisMonth={currentMonthInvoices.length}
                latestInvoiceDate={latestInvoiceDate}
                handleInvoiceDocumentUpload={handleInvoiceDocumentUpload}
              />
            }
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}