import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import UploadPage from "./pages/UploadPage";
import InvoicesPage from "./pages/InvoicesPage";
import DashboardPage from "./pages/DashboardPage";
import imageCompression from "browser-image-compression";
import { PDFDocument } from "pdf-lib";

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

  const [documents, setDocuments] = useState([]);

  const [documentUploadMessage, setDocumentUploadMessage] = useState("");
  const [documentUploadError, setDocumentUploadError] = useState("");
  const [documentUploading, setDocumentUploading] = useState(false);
  const [documentDeleteError, setDocumentDeleteError] = useState("");

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
      fetchJsonOrThrow(`/api/analytics/pnl/trend?months=6&month=${selectedMonth}`),
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
        await Promise.all([
  loadDashboardData(month),
  loadDocuments(month),
]);
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

  async function compressPdf(file) {
  const bytes = await file.arrayBuffer();

  const pdf = await PDFDocument.load(bytes);

  const compressedBytes = await pdf.save({
    useObjectStreams: true,
    addDefaultPage: false,
  });

  return new File(
    [compressedBytes],
    file.name,
    { type: "application/pdf" }
  );
}

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

      await Promise.all([
  loadDashboardData(month),
  loadDocuments(),
]);
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

    await Promise.all([
  loadDashboardData(month),
  loadDocuments(),
]);
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

      await Promise.all([
  loadDashboardData(month),
  loadDocuments(),
]);
    } catch (err) {
      console.error(err);
      setInvoiceDeleteError("Errore durante l'eliminazione della fattura.");
    }
  }

  async function loadDocuments(selectedMonth = month) {
  const documentsData = await fetchJsonOrThrow(
    `/api/documents?month=${selectedMonth}`
  );

  setDocuments(safeArray(documentsData));
}

async function handleGenericDocumentUpload(file, section = "other") {
  if (!file) return;

  try {
    setDocumentUploading(true);
    setDocumentUploadError("");
    setDocumentUploadMessage("");

    let fileToUpload = file;

    const maxSizeMB = 20;
    const maxSizeBytes = maxSizeMB * 1024 * 1024;

    if (file.size > maxSizeBytes) {
      if (file.type.startsWith("image/")) {
        fileToUpload = await imageCompression(file, {
          maxSizeMB: 5,
          maxWidthOrHeight: 2000,
          useWebWorker: true,
        });
      } else {
        setDocumentUploadError(
          `Il PDF è troppo grande (${(file.size / 1024 / 1024).toFixed(
            1
          )} MB). Va compresso prima di caricarlo.`
        );
        return;
      }
    }

    const formData = new FormData();
    formData.append("file", fileToUpload);
    formData.append("month", month);
    formData.append("section", section);

    const response = await fetch("/api/documents/upload", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(
        errorBody || `Upload documento fallito (${response.status})`
      );
    }

    const result = await response.json();

    setDocumentUploadMessage(
      `Documento acquisito: ${result.original_filename}`
    );

    await loadDocuments(month);
    await loadDashboardData(month);
  } catch (err) {
    console.error(err);
    setDocumentUploadError("Errore durante il caricamento del documento.");
  } finally {
    setDocumentUploading(false);
  }
}

function clearDocumentMessages() {
  setDocumentUploadMessage("");
  setDocumentUploadError("");
  setDocumentDeleteError("");
}

async function handleDeleteDocument(documentId) {
  if (!documentId) return;

  try {
    setDocumentDeleteError("");

    const response = await fetch(`/api/documents/${documentId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(
        errorBody || `Delete documento fallito (${response.status})`
      );
    }

    await loadDocuments();
  } catch (err) {
    console.error(err);
    setDocumentDeleteError(
      "Errore durante l'eliminazione del documento."
    );
  }
}

  const pendingInvoices = useMemo(
  () =>
    invoices.filter(
      (invoice) =>
        invoice.status === "pending" &&
        invoice.issue_date?.slice(0, 7) === month
    ),
  [invoices, month]
);

const overdueInvoices = useMemo(
  () =>
    invoices.filter(
      (invoice) =>
        invoice.status === "pending" &&
        invoice.issue_date?.slice(0, 7) < month
    ),
  [invoices, month]
);

const overdueInvoicesAmount = useMemo(
  () =>
    overdueInvoices.reduce(
      (sum, invoice) => sum + (Number(invoice.total) || 0),
      0
    ),
  [overdueInvoices]
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

  const latestCashDocument = documents
  .filter((document) => document.section === "cash")
  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];

const latestPosUploadDate = latestCashDocument?.created_at ?? null;

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
                previousOverdueInvoices={overdueInvoices}
previousOverdueInvoicesAmount={overdueInvoicesAmount}
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
                documents={documents}
                handleGenericDocumentUpload={handleGenericDocumentUpload}
                handleDeleteDocument={handleDeleteDocument}
                clearDocumentMessages={clearDocumentMessages}

                documentUploading={documentUploading}
                documentUploadMessage={documentUploadMessage}
                documentUploadError={documentUploadError}
                documentDeleteError={documentDeleteError}
              />
            }
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}