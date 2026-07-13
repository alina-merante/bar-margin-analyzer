import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import UploadPage from "./pages/UploadPage";
import InvoicesPage from "./pages/InvoicesPage";
import DashboardPage from "./pages/DashboardPage";
import imageCompression from "browser-image-compression";
import { PDFDocument, StandardFonts, rgb } from "pdf-lib";

function getCurrentMonth() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function formatMonthLabel(month) {
  if (!month) return "-";

  const [year, monthNum] = month.split("-").map(Number);

  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function formatShortDate(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
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
  const [invoiceCategories, setInvoiceCategories] = useState([]);
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
      categoriesData,
      trendData,
      topProductsData,
      expensesByCategoryData,
      expensesBySupplierData,
      insightsData,
    ] = await Promise.all([
      fetchJsonOrThrow(`/api/analytics/overview?month=${selectedMonth}`),
      fetchJsonOrThrow("/api/invoices"),
      fetchJsonOrThrow("/api/categories"),
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
    setInvoiceCategories(safeArray(categoriesData));
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

  async function handleExportDashboardPdf() {
    const pdf = await PDFDocument.create();
    const page = pdf.addPage([595, 842]);
    const fontRegular = await pdf.embedFont(StandardFonts.Helvetica);
    const fontBold = await pdf.embedFont(StandardFonts.HelveticaBold);

    const left = 40;
    const right = 555;
    let cursorY = 800;

    function drawLine(text, options = {}) {
      const size = options.size ?? 11;
      const font = options.font ?? fontRegular;
      const color = options.color ?? rgb(0.15, 0.15, 0.15);
      const gap = options.gap ?? 18;

      page.drawText(text, {
        x: left,
        y: cursorY,
        size,
        font,
        color,
      });

      cursorY -= gap;
    }

    function drawSectionTitle(text) {
      cursorY -= 8;
      drawLine(text, {
        font: fontBold,
        size: 13,
        color: rgb(0.08, 0.08, 0.08),
        gap: 20,
      });
    }

    function drawKpiLabel(label, value) {
      drawLine(`${label}: ${value}`, { gap: 16 });
    }

    page.drawText(`Dashboard ${formatMonthLabel(month)}`, {
      x: left,
      y: cursorY,
      size: 22,
      font: fontBold,
      color: rgb(0.1, 0.1, 0.1),
    });

    cursorY -= 30;
    drawLine(`Esportato il ${formatShortDate(new Date())}`, {
      size: 10,
      color: rgb(0.35, 0.35, 0.35),
      gap: 22,
    });

    drawSectionTitle("Sintesi economica");
    drawKpiLabel("Ricavi totali", formatEuro(pnl.revenue));
    drawKpiLabel("Costi totali", formatEuro(pnl.expenses));
    drawKpiLabel("Margine netto", formatEuro(pnl.profit));
    drawKpiLabel("Da pagare", formatEuro(pendingInvoicesAmount));

    drawSectionTitle("Andamento ultimi mesi");
    const trendRows = trend.slice(-6);
    if (trendRows.length) {
      trendRows.forEach((item) => {
        drawLine(
          `${item.month}: ricavi ${formatEuro(item.revenue)} · costi ${formatEuro(item.expenses)} · margine ${formatEuro(item.profit)}`,
          { gap: 15 }
        );
      });
    } else {
      drawLine("Nessun dato disponibile.");
    }

    drawSectionTitle("Prodotti top");
    if (topProductsList.length) {
      topProductsList.slice(0, 5).forEach((product, index) => {
        drawLine(
          `${index + 1}. ${product.product} · ${Number(product.quantity) || 0} pezzi · ${formatEuro(product.revenue)}`,
          { gap: 15 }
        );
      });
    } else {
      drawLine("Nessun prodotto disponibile.");
    }

    drawSectionTitle("Fatture rilevanti");
    const invoiceRows = [...pendingInvoices]
      .slice(0, 5)
      .map(
        (invoice) =>
          `${invoice.supplier || "Fornitore"} · ${formatEuro(invoice.total)} · scade ${formatShortDate(invoice.due_date)}`
      );

    if (invoiceRows.length) {
      invoiceRows.forEach((row) => drawLine(row, { gap: 15 }));
    } else {
      drawLine("Nessuna fattura in sospeso per il mese selezionato.");
    }

    page.drawLine({
      start: { x: left, y: 70 },
      end: { x: right, y: 70 },
      thickness: 1,
      color: rgb(0.85, 0.85, 0.85),
    });

    page.drawText("Bar Margin Analyzer", {
      x: left,
      y: 48,
      size: 9,
      font: fontRegular,
      color: rgb(0.5, 0.5, 0.5),
    });

    const pdfBytes = await pdf.save();
    const blob = new Blob([pdfBytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `dashboard-${month}.pdf`;
    link.click();

    URL.revokeObjectURL(url);
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
      const extractedMonth = result.due_date?.slice(0, 7) || month;

      setInvoiceUploadMessage(
        `Fattura acquisita: ${result.supplier || "fornitore rilevato"} · ${
          result.invoice_number || "numero non disponibile"
        }`
      );

      if (result.due_date) {
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
    await loadDashboardData(month);
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
        invoice.due_date?.slice(0, 7) === month
    ),
  [invoices, month]
);

const overdueInvoices = useMemo(() => {
  const currentYear = new Date().getFullYear();

  return invoices.filter((invoice) => {
    if (invoice.status !== "pending") return false;
    if (!invoice.due_date) return false;

    const dueDate = new Date(invoice.due_date);
    if (Number.isNaN(dueDate.getTime())) return false;
    if (dueDate.getFullYear() !== currentYear) return false;

    return dueDate < new Date();
  });
}, [invoices]);

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
    (invoice) => invoice.due_date?.slice(0, 7) === month
  );

  const latestInvoiceDate = currentMonthInvoices.length
    ? currentMonthInvoices.map((invoice) => invoice.due_date).sort().at(-1)
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
                onExportPdf={handleExportDashboardPdf}
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
                invoiceCategories={invoiceCategories}
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
                key={month}
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
                invoices={invoices}
                documents={documents}
                handleGenericDocumentUpload={handleGenericDocumentUpload}
                handleDeleteDocument={handleDeleteDocument}
                handleDeleteInvoice={handleDeleteInvoice}
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