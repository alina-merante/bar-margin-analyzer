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

function formatDateDMY(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatMonthShort(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  const short = new Intl.DateTimeFormat("it-IT", {
    month: "short",
  }).format(new Date(year, monthNum - 1, 1));
  return short.replace(".", "").slice(0, 3);
}

function resolveInvoiceCategoryLabel(invoice, knownCategories = []) {
  const category = String(invoice?.category || "").trim();
  if (category) return category;

  const supplier = String(invoice?.supplier || "").toLowerCase();

  const matchedKnownCategory = knownCategories.find((item) => {
    const normalizedName = String(item)
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
    return supplier.includes(normalizedName);
  });

  if (matchedKnownCategory) return matchedKnownCategory;

  if (supplier.includes("caff")) return "Caffe";
  if (supplier.includes("latte") || supplier.includes("lattiero")) return "Latticini";
  if (supplier.includes("dolci") || supplier.includes("pane") || supplier.includes("pastic")) {
    return "Pasticceria";
  }
  if (supplier.includes("bevande")) return "Bevande";
  if (supplier.includes("serviz") || supplier.includes("copywriter") || supplier.includes("consul")) {
    return "Servizi";
  }
  if (
    supplier.includes("utenz") ||
    supplier.includes("energia") ||
    supplier.includes("luce") ||
    supplier.includes("gas")
  ) {
    return "Utenze";
  }

  return "Altro";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function translateInsightToItalian(text) {
  if (!text) return "";
  const trimmed = String(text).trim();

  const metricMatch = trimmed.match(
    /^(Revenue|Expenses|Profit)\s+(increased|decreased)\s+by\s+([0-9.]+)%\s+vs\s+previous\s+month\.?$/i
  );
  if (metricMatch) {
    const metric = metricMatch[1].toLowerCase();
    const direction = metricMatch[2].toLowerCase();
    const pct = metricMatch[3].replace(".", ",");
    const metricLabel =
      metric === "revenue" ? "I ricavi" : metric === "expenses" ? "I costi" : "Il profitto";
    const directionLabel = direction === "increased" ? "sono aumentati" : "sono diminuiti";
    return `${metricLabel} ${directionLabel} del ${pct}% rispetto al mese precedente.`;
  }

  const categoryMatch = trimmed.match(
    /^Top\s+expense\s+category\s+'(.+)'\s+(increased|decreased)\s+by\s+([0-9.]+)%\s+vs\s+previous\s+month\.?$/i
  );
  if (categoryMatch) {
    const category = categoryMatch[1];
    const direction = categoryMatch[2].toLowerCase();
    const pct = categoryMatch[3].replace(".", ",");
    const directionLabel = direction === "increased" ? "è aumentata" : "è diminuita";
    return `La categoria di spesa principale "${category}" ${directionLabel} del ${pct}% rispetto al mese precedente.`;
  }

  const supplierMatch = trimmed.match(
    /^Top\s+supplier\s+'(.+)'\s+represents\s+([0-9.]+)%\s+of\s+total\s+expenses\.?$/i
  );
  if (supplierMatch) {
    const supplier = supplierMatch[1];
    const pct = supplierMatch[2].replace(".", ",");
    return `Il fornitore principale "${supplier}" rappresenta il ${pct}% delle spese totali.`;
  }

  return trimmed
    .replace(/vs previous month/gi, "rispetto al mese precedente")
    .replace(/increased/gi, "aumentato")
    .replace(/decreased/gi, "diminuito")
    .replace(/Top supplier/gi, "Fornitore principale")
    .replace(/Top expense category/gi, "Categoria di spesa principale");
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

  function handleExportDashboardPdf() {
    const monthLabel = formatMonthLabel(month);
    const capMonthLabel = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
    const now = new Date();
    const reportId = `RPT-${month}-${now.getTime()}`;

    const currentMonthInvoices = safeArray(invoices)
      .filter(
        (invoice) =>
          invoice.due_date?.slice(0, 7) === month || invoice.issue_date?.slice(0, 7) === month
      )
      .sort((a, b) => {
        const aDate = new Date(a.due_date || a.issue_date || 0).getTime();
        const bDate = new Date(b.due_date || b.issue_date || 0).getTime();
        return aDate - bDate;
      });

    const knownCategoryNames = safeArray(invoiceCategories)
      .map((item) => {
        if (typeof item === "string") return item;
        return item?.name || item?.category || "";
      })
      .map((value) => String(value).trim())
      .filter(Boolean);

    const paidInvoices = currentMonthInvoices.filter((invoice) => invoice.status === "paid");
    const unpaidInvoices = currentMonthInvoices.filter((invoice) => invoice.status !== "paid");
    const paidTotal = paidInvoices.reduce((sum, invoice) => sum + (Number(invoice.total) || 0), 0);
    const unpaidTotal = unpaidInvoices.reduce((sum, invoice) => sum + (Number(invoice.total) || 0), 0);
    const monthInvoiceTotal = currentMonthInvoices.reduce(
      (sum, invoice) => sum + (Number(invoice.total) || 0),
      0
    );

    const trendRows = safeArray(trend).slice(-6);
    const trendMax = Math.max(
      ...trendRows.flatMap((item) => [Number(item.revenue) || 0, Number(item.expenses) || 0]),
      1
    );

    const currentTrendIndex = trendRows.findIndex((item) => item.month === month);
    const currentTrend = currentTrendIndex >= 0 ? trendRows[currentTrendIndex] : trendRows.at(-1);
    const prevTrend =
      currentTrendIndex > 0
        ? trendRows[currentTrendIndex - 1]
        : trendRows.length > 1
        ? trendRows[trendRows.length - 2]
        : null;

    const calcDelta = (curr, prev) => {
      if (!prev) return 0;
      if (prev === 0) return curr === 0 ? 0 : 100;
      return ((curr - prev) / Math.abs(prev)) * 100;
    };

    const revenueDelta = calcDelta(
      Number(currentTrend?.revenue || pnl.revenue || 0),
      Number(prevTrend?.revenue || 0)
    );
    const expensesDelta = calcDelta(
      Number(currentTrend?.expenses || pnl.expenses || 0),
      Number(prevTrend?.expenses || 0)
    );
    const profitDelta = calcDelta(
      Number(currentTrend?.profit || pnl.profit || 0),
      Number(prevTrend?.profit || 0)
    );

    const marginPercent =
      Number(pnl.revenue) > 0
        ? Math.max(0, (Number(pnl.profit) / Number(pnl.revenue)) * 100)
        : 0;

    const expenseItems = safeArray(expensesByCategory.items)
      .map((item) => ({
        category: item.category || "Altro",
        amount: Math.abs(Number(item.total_amount || item.expenses || 0)),
      }))
      .filter((item) => item.amount > 0)
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 5);

    const colorPalette = ["#c8813a", "#ddd0bc", "#2a7a50", "#5a3e28", "#e8d8c4"];
    const iconByCategory = {
      caffe: "☕",
      latte: "🥛",
      lattiero: "🥛",
      dolci: "🥐",
      pasticceria: "🥐",
      bevande: "🍹",
      altro: "📦",
    };

    const totalCategoryExpenses = expenseItems.reduce((sum, item) => sum + item.amount, 0);
    const radius = 35;
    const circumference = 2 * Math.PI * radius;
    let donutOffset = 0;

    const donutCircles = expenseItems
      .map((item, index) => {
        const pct = totalCategoryExpenses > 0 ? (item.amount / totalCategoryExpenses) * 100 : 0;
        const dash = (pct / 100) * circumference;
        const html = `<circle cx="50" cy="50" r="35" fill="none" stroke="${colorPalette[index]}" stroke-width="16" stroke-dasharray="${dash.toFixed(1)} ${(circumference - dash).toFixed(1)}" stroke-dashoffset="-${donutOffset.toFixed(1)}" transform="rotate(-90 50 50)"/>`;
        donutOffset += dash;
        return html;
      })
      .join("");

    const donutLegend = expenseItems
      .map((item, index) => {
        const pct = totalCategoryExpenses > 0 ? (item.amount / totalCategoryExpenses) * 100 : 0;
        const key = item.category.toLowerCase();
        const icon = Object.keys(iconByCategory).find((k) => key.includes(k));
        return `<div class="dl-mini"><div class="dl-dot-mini" style="background:${colorPalette[index]}"></div><span class="dl-name-mini">${icon ? iconByCategory[icon] : "📦"} ${escapeHtml(item.category)}</span><span class="dl-val-mini">${escapeHtml(
          new Intl.NumberFormat("it-IT", {
            style: "currency",
            currency: "EUR",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
          }).format(item.amount)
        )}</span><span class="dl-pct-mini">${pct.toFixed(0)}%</span></div>`;
      })
      .join("");

    const trendBars = trendRows
      .map((item) => {
        const revH = Math.max(4, ((Number(item.revenue) || 0) / trendMax) * 100);
        const costH = Math.max(4, ((Number(item.expenses) || 0) / trendMax) * 100);
        const currentClass = item.month === month ? " cur" : "";
        const labelClass = item.month === month ? "bm-label cur" : "bm-label";
        return `<div class="bm-group"><div class="bm-pair"><div class="bm-bar r${currentClass}" style="height:${revH.toFixed(1)}%"></div><div class="bm-bar c${currentClass}" style="height:${costH.toFixed(1)}%"></div></div><div class="${labelClass}">${escapeHtml(
          formatMonthShort(item.month)
        )}</div></div>`;
      })
      .join("");

    const invoiceRows = currentMonthInvoices
      .slice(0, 6)
      .map((invoice) => {
        const dueDate = invoice.due_date ? new Date(invoice.due_date) : null;
        const isPaid = invoice.status === "paid";
        const isOver = !isPaid && dueDate && dueDate < new Date();
        const tone = isPaid ? "paid" : isOver ? "over" : "due";
        const trClass = isOver ? "urgente" : !isPaid ? "scadenza" : "";
        const amountColor = isOver ? "var(--red)" : !isPaid ? "var(--yellow)" : "var(--text-dark)";
        const dueColor = isOver ? "var(--red)" : !isPaid ? "var(--yellow)" : "var(--text-soft)";
        const categoryLabel = resolveInvoiceCategoryLabel(invoice, knownCategoryNames);
        return `<tr class="${trClass}"><td><strong>${escapeHtml(
          invoice.supplier || "Fornitore"
        )}</strong></td><td style="color:var(--text-soft)">${escapeHtml(
          invoice.invoice_number || "-"
        )}</td><td style="color:${dueColor};font-weight:600">${escapeHtml(
          formatDateDMY(invoice.due_date)
        )}</td><td>${escapeHtml(categoryLabel)}</td><td style="text-align:right;font-weight:700;color:${amountColor}">${escapeHtml(
          new Intl.NumberFormat("it-IT", {
            style: "currency",
            currency: "EUR",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
          }).format(Number(invoice.total) || 0)
        )}</td><td style="text-align:center"><span class="fbadge ${tone}">${
          tone === "paid" ? "Pagata" : tone === "over" ? "Scaduta" : "In scadenza"
        }</span></td></tr>`;
      })
      .join("");

    const apiInsights = safeArray(insights.insights).slice(0, 3);
    const fallbackInsights = [
      {
        tone: profitDelta >= 0 ? "pos" : "neg",
        icon: profitDelta >= 0 ? "📈" : "📉",
        title: profitDelta >= 0 ? "Margine in crescita" : "Margine in calo",
        text: `Il margine netto di ${monthLabel} è al ${marginPercent.toFixed(0)}% (${Math.abs(
          profitDelta
        ).toFixed(1)}% vs mese precedente).`,
      },
      {
        tone: unpaidTotal > 0 ? "neg" : "pos",
        icon: unpaidTotal > 0 ? "⚠️" : "✅",
        title: unpaidTotal > 0 ? "Fatture da saldare" : "Nessuna fattura aperta",
        text:
          unpaidTotal > 0
            ? `Ci sono ${unpaidInvoices.length} fatture non pagate per ${new Intl.NumberFormat("it-IT", {
                style: "currency",
                currency: "EUR",
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
              }).format(unpaidTotal)}.`
            : "Tutte le fatture del mese risultano pagate.",
      },
      {
        tone: "neu",
        icon: "🏷️",
        title: "Focus costi",
        text: expenseItems.length
          ? `${escapeHtml(expenseItems[0].category)} è la categoria con impatto maggiore sui costi del mese.`
          : "Nessuna categoria di costo disponibile per il mese selezionato.",
      },
    ];

    const insightsRows = (apiInsights.length
      ? apiInsights.map((text, index) => ({
          tone: index === 0 ? "pos" : index === 1 ? "neg" : "neu",
          icon: index === 0 ? "📈" : index === 1 ? "⚠️" : "💡",
          title: index === 0 ? "Andamento" : index === 1 ? "Attenzione" : "Suggerimento",
          text: translateInsightToItalian(text),
        }))
      : fallbackInsights
    )
      .slice(0, 3)
      .map(
        (item) => `<div class="insight-row ${item.tone}"><span class="ir-icon">${item.icon}</span><div><div class="ir-title">${escapeHtml(
          item.title
        )}</div><div class="ir-text">${escapeHtml(item.text)}</div></div></div>`
      )
      .join("");

    const euro0 = (value) =>
      new Intl.NumberFormat("it-IT", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(Number(value) || 0);

    const euro2 = (value) =>
      new Intl.NumberFormat("it-IT", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(Number(value) || 0);

    const kpiTag = (delta) => `${delta >= 0 ? "↑" : "↓"} ${Math.abs(delta).toFixed(1)}%`;

    const totalK = Number(pnl.expenses) > 0 ? `€${(Number(pnl.expenses) / 1000).toFixed(1).replace(".", ",")}k` : "€0";

    const html = `<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BarManager - Report ${escapeHtml(capMonthLabel)}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --espresso: #1a0a00;
    --crema: #c8813a;
    --crema-light: #e8a85a;
    --crema-pale: #f5e6d3;
    --milk: #f5ede0;
    --border: #e8d8c4;
    --text-dark: #1a0a00;
    --text-mid: #5a3e28;
    --text-soft: #8a6a4a;
    --green: #2a7a50;
    --green-bg: #eaf5f0;
    --red: #b83030;
    --red-bg: #fdecea;
    --yellow: #c47a10;
    --yellow-bg: #fef3e2;
  }

  * { margin:0; padding:0; box-sizing:border-box; }

  body {
    font-family: 'DM Sans', sans-serif;
    background: #cbd5e1;
    padding: 40px 24px;
    min-height: 100vh;
    color: var(--text-dark);
  }

  .screen-header {
    max-width: 794px;
    margin: 0 auto 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .screen-title {
    font-family: 'Playfair Display', serif;
    font-size: 18px;
    color: #334155;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .screen-badge {
    background: #334155;
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
    letter-spacing: .4px;
  }

  .btn-download {
    background: var(--crema);
    color: #fff;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 2px 10px rgba(200,129,58,.35);
  }

  .a4 {
    width: 794px;
    background: #fff;
    margin: 0 auto;
    box-shadow: 0 8px 40px rgba(0,0,0,.18);
    border-radius: 4px;
    overflow: hidden;
  }

  .doc-header {
    background: var(--espresso);
    padding: 32px 40px 28px;
    position: relative;
    overflow: hidden;
  }

  .doc-header::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 180px; height: 180px;
    border-radius: 50%;
    background: var(--crema);
    opacity: .08;
  }

  .doc-header::after {
    content: '';
    position: absolute;
    bottom: -20px; left: 200px;
    width: 100px; height: 100px;
    border-radius: 50%;
    background: var(--crema);
    opacity: .05;
  }

  .header-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 20px;
  }

  .header-logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo-icon {
    width: 42px; height: 42px;
    background: var(--crema);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
  }

  .logo-name {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    font-weight: 700;
    color: #fff;
  }

  .logo-sub {
    font-size: 10px;
    color: rgba(255,255,255,.4);
    letter-spacing: .8px;
    text-transform: uppercase;
    margin-top: 2px;
  }

  .header-meta { text-align: right; }

  .meta-date {
    font-size: 11px;
    color: rgba(255,255,255,.4);
    text-transform: uppercase;
    letter-spacing: .8px;
    margin-bottom: 4px;
  }

  .meta-ref {
    font-size: 11.5px;
    color: rgba(255,255,255,.35);
  }

  .header-title-row {
    border-top: 1px solid rgba(255,255,255,.1);
    padding-top: 18px;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
  }

  .doc-title {
    font-family: 'Playfair Display', serif;
    font-size: 26px;
    font-weight: 700;
    color: #fff;
    line-height: 1.1;
  }

  .doc-subtitle {
    font-size: 13px;
    color: rgba(255,255,255,.5);
    margin-top: 4px;
  }

  .header-period { text-align: right; }

  .period-label {
    font-size: 10px;
    color: rgba(255,255,255,.35);
    text-transform: uppercase;
    letter-spacing: .8px;
  }

  .period-value {
    font-family: 'Playfair Display', serif;
    font-size: 18px;
    font-weight: 700;
    color: var(--crema-light);
    margin-top: 3px;
  }

  .doc-body { padding: 32px 40px 36px; }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 28px;
  }

  .kpi-box {
    border-radius: 12px;
    padding: 14px 16px;
    border: 1px solid var(--border);
  }

  .kpi-box.dark {
    background: var(--espresso);
    border-color: transparent;
  }

  .kpi-box-label {
    font-size: 9.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: var(--text-soft);
    margin-bottom: 6px;
  }

  .kpi-box.dark .kpi-box-label { color: rgba(255,255,255,.4); }

  .kpi-box-value {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--espresso);
    line-height: 1;
  }

  .kpi-box.dark .kpi-box-value { color: var(--crema-light); }

  .kpi-box-sub {
    font-size: 10.5px;
    color: var(--text-soft);
    margin-top: 5px;
  }

  .kpi-box.dark .kpi-box-sub { color: rgba(255,255,255,.35); }

  .kpi-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-top: 6px;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 10px;
  }

  .up { background: var(--green-bg); color: var(--green); }
  .down { background: var(--red-bg); color: var(--red); }

  .m-wrap {
    height: 5px;
    background: rgba(255,255,255,.12);
    border-radius: 10px;
    overflow: hidden;
    margin: 8px 0 4px;
  }
  .m-fill {
    height: 100%;
    border-radius: 10px;
    background: linear-gradient(90deg, var(--crema), var(--crema-light));
  }
  .m-labels {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    color: rgba(255,255,255,.3);
  }
  .m-labels .hi { color: var(--crema-light); font-weight: 600; }

  .section-title {
    font-family: 'Playfair Display', serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--espresso);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .bar-chart-mini {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    height: 80px;
    margin-bottom: 6px;
  }

  .bm-group {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    gap: 3px;
  }

  .bm-pair {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 65px;
    width: 100%;
    justify-content: center;
  }

  .bm-bar {
    border-radius: 4px 4px 0 0;
    min-width: 12px;
    flex: 1;
    max-width: 18px;
  }

  .bm-bar.r { background: var(--crema); }
  .bm-bar.c { background: var(--border); }
  .bm-bar.r.cur { background: var(--crema-light); }
  .bm-bar.c.cur { background: #b08a64; }
  .bm-label { font-size: 9px; color: var(--text-soft); text-transform: capitalize; }
  .bm-label.cur { color: var(--text-mid); font-weight: 700; }

  .chart-legend-mini {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 6px;
  }

  .cl-mini { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--text-soft); }
  .cl-dot-mini { width: 8px; height: 8px; border-radius: 2px; }

  .donut-section {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 16px;
    align-items: center;
    margin-bottom: 26px;
  }

  .donut-wrap-mini { position: relative; width: 110px; height: 110px; }
  .donut-center-mini {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
  }
  .dcv { font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 700; color: var(--espresso); }
  .dcl { font-size: 9px; color: var(--text-soft); }

  .donut-legend-mini { display: flex; flex-direction: column; gap: 6px; }
  .dl-mini { display: flex; align-items: center; gap: 7px; font-size: 11px; }
  .dl-dot-mini { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dl-name-mini { flex: 1; color: var(--text-mid); }
  .dl-val-mini { font-weight: 600; color: var(--text-dark); }
  .dl-pct-mini { color: var(--text-soft); font-size: 10px; width: 28px; text-align: right; }

  .ftbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
  .ftbl th {
    font-size: 9.5px; font-weight: 700; letter-spacing: .7px;
    text-transform: uppercase; color: var(--text-soft);
    padding: 0 10px 8px; text-align: left;
    border-bottom: 1.5px solid var(--espresso);
  }
  .ftbl td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  .ftbl tr:last-child td { border-bottom: none; }
  .ftbl tr.urgente td { background: #fff8f7; }
  .ftbl tr.scadenza td { background: #fffbf4; }

  .fbadge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 9px; font-weight: 700; padding: 2px 7px;
    border-radius: 10px; text-transform: uppercase; letter-spacing: .3px;
  }
  .fbadge.paid { background: var(--green-bg); color: var(--green); }
  .fbadge.due  { background: var(--yellow-bg); color: var(--yellow); }
  .fbadge.over { background: var(--red-bg); color: var(--red); }

  .insight-section { margin-top: 22px; }
  .insight-list-pdf { display: flex; flex-direction: column; gap: 7px; }
  .insight-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 12px; border-radius: 9px; border: 1px solid;
    font-size: 11.5px;
  }
  .insight-row.pos { background: var(--green-bg); border-color: #c0e4d4; }
  .insight-row.neg { background: var(--red-bg); border-color: #f5c0bc; }
  .insight-row.neu { background: var(--yellow-bg); border-color: #f0d090; }
  .ir-icon { font-size: 16px; flex-shrink: 0; }
  .ir-title { font-weight: 600; color: var(--text-dark); margin-bottom: 2px; font-size: 12px; }
  .ir-text { color: var(--text-mid); line-height: 1.4; }

  .doc-footer {
    border-top: 1px solid var(--border);
    margin: 0 40px;
    padding: 14px 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .footer-left { display: flex; align-items: center; gap: 8px; }
  .footer-logo { font-size: 14px; }
  .footer-name { font-family: 'Playfair Display', serif; font-size: 12px; color: var(--text-soft); }
  .footer-right { font-size: 10.5px; color: var(--text-soft); text-align: right; }
  .footer-conf {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 9.5px; color: var(--text-soft); margin-top: 3px;
  }

  @media print {
    body { background: #fff; padding: 0; }
    .screen-header { display: none; }
    .a4 { box-shadow: none; border-radius: 0; width: 100%; }
  }
</style>
</head>
<body>
<div class="screen-header">
  <div class="screen-title">
    📄 Anteprima PDF
    <span class="screen-badge">${escapeHtml(capMonthLabel)}</span>
  </div>
  <button class="btn-download" onclick="window.print()">
    ⬇ Scarica PDF
  </button>
</div>

<div class="a4">
  <div class="doc-header">
    <div class="header-top">
      <div class="header-logo">
        <div class="logo-icon">☕</div>
        <div>
          <div class="logo-name">BarManager</div>
          <div class="logo-sub">Report mensile</div>
        </div>
      </div>
      <div class="header-meta">
        <div class="meta-date">Generato il ${escapeHtml(formatShortDate(now))}</div>
        <div class="meta-ref">Rif. ${escapeHtml(reportId)}</div>
      </div>
    </div>
    <div class="header-title-row">
      <div>
        <div class="doc-title">Riepilogo mensile</div>
        <div class="doc-subtitle">Ricavi · Costi · Margine · Fatture</div>
      </div>
      <div class="header-period">
        <div class="period-label">Periodo</div>
        <div class="period-value">${escapeHtml(capMonthLabel)}</div>
      </div>
    </div>
  </div>

  <div class="doc-body">
    <div class="kpi-strip">
      <div class="kpi-box dark">
        <div class="kpi-box-label">Margine netto</div>
        <div class="kpi-box-value">${escapeHtml(euro0(pnl.profit))}</div>
        <div class="m-wrap"><div class="m-fill" style="width:${Math.min(100, marginPercent).toFixed(0)}%"></div></div>
        <div class="m-labels"><span>0%</span><span class="hi">${marginPercent.toFixed(0)}%</span><span>100%</span></div>
        <div class="kpi-box-sub">${kpiTag(profitDelta)} vs mese precedente</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-box-label">Ricavi totali</div>
        <div class="kpi-box-value">${escapeHtml(euro0(pnl.revenue))}</div>
        <div class="kpi-tag ${revenueDelta >= 0 ? "up" : "down"}">${kpiTag(revenueDelta)}</div>
        <div class="kpi-box-sub">${safeArray(topProducts.by_quantity).length} prodotti top</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-box-label">Costi totali</div>
        <div class="kpi-box-value">${escapeHtml(euro0(pnl.expenses))}</div>
        <div class="kpi-tag ${expensesDelta <= 0 ? "up" : "down"}">${kpiTag(expensesDelta)}</div>
        <div class="kpi-box-sub">${currentMonthInvoices.length} fatture</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-box-label">Da pagare</div>
        <div class="kpi-box-value">${escapeHtml(euro0(pendingInvoicesAmount))}</div>
        <div class="kpi-tag ${pendingInvoices.length > 0 ? "down" : "up"}">${pendingInvoices.length > 0 ? "⚠" : "✓"} ${pendingInvoices.length}</div>
        <div class="kpi-box-sub">fatture in sospeso</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:26px;">
      <div>
        <div class="section-title">📊 Ricavi vs Costi</div>
        <div class="bar-chart-mini">
          ${trendBars}
        </div>
        <div class="chart-legend-mini">
          <div class="cl-mini"><div class="cl-dot-mini" style="background:var(--crema)"></div>Ricavi</div>
          <div class="cl-mini"><div class="cl-dot-mini" style="background:var(--border)"></div>Costi</div>
        </div>
      </div>

      <div>
        <div class="section-title">🏷️ Spese per categoria</div>
        <div class="donut-section">
          <div class="donut-wrap-mini">
            <svg viewBox="0 0 100 100" width="110" height="110">
              ${donutCircles || `<circle cx="50" cy="50" r="35" fill="none" stroke="#e8d8c4" stroke-width="16"/>`}
            </svg>
            <div class="donut-center-mini">
              <div class="dcv">${escapeHtml(totalK)}</div>
              <div class="dcl">totale</div>
            </div>
          </div>
          <div class="donut-legend-mini">
            ${donutLegend || `<div class="dl-mini"><span class="dl-name-mini">Nessun dato</span></div>`}
          </div>
        </div>
      </div>
    </div>

    <div style="margin-bottom:22px;">
      <div class="section-title">🧾 Riepilogo fatture ${escapeHtml(capMonthLabel.toLowerCase())}</div>
      <table class="ftbl">
        <thead>
          <tr>
            <th>Fornitore</th>
            <th>N° Fattura</th>
            <th>Scadenza</th>
            <th>Categoria</th>
            <th style="text-align:right;">Importo</th>
            <th style="text-align:center;">Stato</th>
          </tr>
        </thead>
        <tbody>
          ${invoiceRows || `<tr><td colspan="6" style="text-align:center;color:var(--text-soft);padding:14px;">Nessuna fattura nel mese selezionato.</td></tr>`}
        </tbody>
      </table>
      <div style="display:flex;justify-content:flex-end;margin-top:10px;padding-top:10px;border-top:1.5px solid var(--espresso);">
        <div style="display:flex;gap:32px;font-size:12px;">
          <div style="text-align:right;"><div style="color:var(--text-soft);margin-bottom:2px;">Totale pagate</div><div style="font-weight:700;color:var(--green);">${escapeHtml(
            euro0(paidTotal)
          )}</div></div>
          <div style="text-align:right;"><div style="color:var(--text-soft);margin-bottom:2px;">Da saldare</div><div style="font-weight:700;color:var(--red);">${escapeHtml(
            euro0(unpaidTotal)
          )}</div></div>
          <div style="text-align:right;"><div style="color:var(--text-soft);margin-bottom:2px;">Totale mese</div><div style="font-weight:700;color:var(--espresso);font-size:14px;">${escapeHtml(
            euro0(monthInvoiceTotal)
          )}</div></div>
        </div>
      </div>
    </div>

    <div class="insight-section">
      <div class="section-title">💡 Insight automatici</div>
      <div class="insight-list-pdf">
        ${insightsRows}
      </div>
    </div>
  </div>

  <div class="doc-footer">
    <div class="footer-left">
      <span class="footer-logo">☕</span>
      <span class="footer-name">BarManager · ${escapeHtml(capMonthLabel)}</span>
    </div>
    <div class="footer-right">
      <div>Pagina 1 di 1 · ${escapeHtml(reportId)}</div>
      <div class="footer-conf">🔒 Documento riservato · uso interno</div>
    </div>
  </div>
</div>

</body>
</html>`;

    const printWindow = window.open("", "_blank", "width=1100,height=900");
    if (!printWindow) return;

    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
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