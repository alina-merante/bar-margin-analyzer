const CATEGORY_LABELS = new Map([
  ["uncategorized", "Senza categoria"],
  ["unclassified", "Senza categoria"],
  ["other", "Altro"],
  ["utilities", "Utenze"],
  ["beverage", "Bevande"],
  ["beverages", "Bevande"],
  ["services", "Servizi"],
  ["service", "Servizi"],
  ["coffee", "Caffè"],
  ["caffe", "Caffè"],
  ["dairy", "Latticini"],
  ["bakery", "Pasticceria"],
  ["food", "Alimentari"],
]);

function formatPercentage(value) {
  return Math.abs(Number(value)).toFixed(1).replace(".", ",");
}

export function calculatePdfMarginPercent(profit, revenue) {
  const revenueAmount = Number(revenue) || 0;
  if (revenueAmount === 0) return 0;
  return ((Number(profit) || 0) / revenueAmount) * 100;
}

export function getPdfMarginBarWidth(marginPercent) {
  return Math.min(100, Math.abs(Number(marginPercent) || 0));
}

export function getPdfMarginBarTone(marginPercent) {
  const value = Number(marginPercent);
  if (value < 0) return "negative";
  if (value > 0) return "positive";
  return "neutral";
}

const MONTHLY_METRICS = [
  {
    key: "revenue",
    title: "Ricavi",
    subject: "I ricavi",
    increase: "sono aumentati",
    decrease: "sono diminuiti",
    unchanged: "sono rimasti invariati",
    inverse: false,
  },
  {
    key: "expenses",
    title: "Costi",
    subject: "I costi",
    increase: "sono aumentati",
    decrease: "sono diminuiti",
    unchanged: "sono rimasti invariati",
    inverse: true,
  },
  {
    key: "profit",
    title: "Margine netto",
    subject: "Il margine netto",
    increase: "è aumentato",
    decrease: "è diminuito",
    unchanged: "è rimasto invariato",
    inverse: false,
  },
];

export function calculatePdfMetricChanges(current = {}, previous = {}) {
  return Object.fromEntries(MONTHLY_METRICS.map(({ key }) => {
    const previousValue = Number(previous?.[key]) || 0;
    const currentValue = Number(current?.[key]) || 0;
    const change = previousValue === 0
      ? null
      : ((currentValue - previousValue) / Math.abs(previousValue)) * 100;

    return [key, change];
  }));
}

export function formatPdfMetricTag(change, { hasMonthlyData = true, inverse = false } = {}) {
  if (!hasMonthlyData || change === null || !Number.isFinite(change)) {
    return { tone: "neutral", text: "Confronto col mese precedente non disponibile" };
  }

  const tone = inverse ? (change <= 0 ? "up" : "down") : (change >= 0 ? "up" : "down");
  const arrow = change > 0 ? "↑" : change < 0 ? "↓" : "→";
  return {
    tone,
    text: `${arrow} ${Math.abs(change).toFixed(1).replace(".", ",")}%`,
  };
}

export function localizePdfCategoryLabel(value) {
  const label = String(value ?? "").trim();
  const key = label
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  return CATEGORY_LABELS.get(key) || label;
}

export function translateInsightToItalian(text) {
  const insight = String(text ?? "").trim();
  const categoryMatch = insight.match(
    /^Top\s+expense\s+category\s+'(.+)'\s+(increased|decreased)\s+by\s+(-?[0-9.]+)%\s+vs\s+previous\s+month\.?$/i
  );
  if (categoryMatch) {
    const category = localizePdfCategoryLabel(categoryMatch[1]);
    const increased = categoryMatch[2].toLowerCase() === "increased";
    return `La categoria di costo principale "${category}" è ${increased ? "aumentata" : "diminuita"} del ${formatPercentage(categoryMatch[3])}% rispetto al mese precedente.`;
  }

  const supplierMatch = insight.match(
    /^Top\s+supplier\s+'(.+)'\s+represents\s+(-?[0-9.]+)%\s+of\s+total\s+expenses\.?$/i
  );
  if (supplierMatch) {
    return `Il fornitore principale "${supplierMatch[1]}" rappresenta l'${formatPercentage(supplierMatch[2])}% dei costi totali.`;
  }

  return "Approfondimento non disponibile.";
}

export function hasPdfMonthData(pnl = {}, invoiceCount = 0) {
  return Boolean(
    Number(pnl.revenue) || Number(pnl.expenses) || Number(invoiceCount)
  );
}

export function buildPdfInsightItems({ apiInsights = [], metricChanges = {}, hasMonthlyData }) {
  if (!hasMonthlyData) {
    return [{
      tone: "info",
      icon: "ℹ️",
      title: "Informazione",
      text: "Nessun dato registrato per il mese selezionato.",
    }];
  }

  const unavailableMetrics = MONTHLY_METRICS.filter(
    ({ key }) => metricChanges[key] === null || !Number.isFinite(metricChanges[key])
  );
  const insightItems = MONTHLY_METRICS
    .filter(({ key }) => metricChanges[key] !== null && Number.isFinite(metricChanges[key]))
    .map(({ key, title, subject, increase, decrease, unchanged, inverse }) => {
      const change = metricChanges[key];
      const increased = change > 0;
      const text = change === 0
        ? `${subject} ${unchanged} rispetto al mese precedente.`
        : `${subject} ${increased ? increase : decrease} del ${formatPercentage(change)}% rispetto al mese precedente.`;
      const tone = inverse
        ? (change <= 0 ? "pos" : "neg")
        : (change >= 0 ? "pos" : "neg");

      return { tone, icon: tone === "pos" ? "📈" : "⚠️", title, text };
    });

  if (!insightItems.length) {
    return [{
      tone: "info",
      icon: "ℹ️",
      title: "Confronto",
      text: "Confronto non disponibile: il mese precedente non presenta valori registrati.",
    }];
  }

  if (unavailableMetrics.length) {
    const labels = unavailableMetrics.map(({ title }) => title.toLowerCase());
    const metricList = labels.length === 1
      ? labels[0]
      : `${labels.slice(0, -1).join(", ")} e ${labels.at(-1)}`;
    insightItems.push({
      tone: "info",
      icon: "ℹ️",
      title: "Confronto",
      text: `Confronto non disponibile per ${metricList}: il mese precedente non presenta valori registrati.`,
    });
  }

  const supplierInsights = apiInsights
    .filter((text) => /^Top\s+supplier\b/i.test(String(text).trim()))
    .map((text) => ({
      tone: "neu",
      icon: "💡",
      title: "Fornitore principale",
      text: translateInsightToItalian(text),
    }));

  return [...insightItems, ...supplierInsights].slice(0, 3);
}

export function formatPendingInvoicesLabel(count) {
  const invoiceCount = Math.max(0, Math.trunc(Number(count) || 0));
  if (!invoiceCount) return "✓ Nessuna fattura da pagare";
  const noun = invoiceCount === 1 ? "fattura" : "fatture";
  return `⚠ ${invoiceCount} ${noun} in sospeso`;
}