const IGNORED_LOCATION_PARTS = new Set(["body", "query", "path", "form", "file"]);

const SERVER_ERROR_MESSAGE =
  "Si è verificato un problema sul server. Il file non è stato caricato: riprova tra qualche istante.";
const NETWORK_ERROR_MESSAGE =
  "Impossibile contattare il server. Controlla la connessione e riprova.";
const UNEXPECTED_ERROR_MESSAGE =
  "Si è verificato un errore imprevisto durante il caricamento. Riprova.";

function formatValidationItem(item) {
  if (typeof item === "string") return item.trim();
  if (!item || typeof item !== "object") return "";

  const message = typeof item.msg === "string" ? item.msg.trim() : "";
  if (!message) return "";

  const location = Array.isArray(item.loc)
    ? item.loc.filter((part) => !IGNORED_LOCATION_PARTS.has(part)).join(".")
    : "";

  return location ? `${location}: ${message}` : message;
}

function formatDetail(detail) {
  if (typeof detail === "string") return detail.trim();

  if (Array.isArray(detail)) {
    return detail.map(formatValidationItem).filter(Boolean).join("\n");
  }

  if (detail && typeof detail === "object") {
    for (const key of ["message", "msg", "detail"]) {
      const value = formatDetail(detail[key]);
      if (value) return value;
    }
  }

  return "";
}

// Accepts a raw response body (text) or an already parsed payload and returns
// the human readable backend detail, or "" when none is available.
export function extractApiErrorMessage(body) {
  if (body === null || body === undefined) return "";

  let payload = body;

  if (typeof body === "string") {
    const text = body.trim();
    if (!text) return "";

    try {
      payload = JSON.parse(text);
    } catch {
      return text.startsWith("<") ? "" : text;
    }
  }

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return formatDetail(payload.detail ?? payload.message);
  }

  return formatDetail(payload);
}

export function buildUploadError({ status, detail } = {}) {
  const message = typeof detail === "string" ? detail.trim() : "";

  if (status === 409) {
    return {
      variant: "error",
      title: "Documento già presente",
      message: message || "Questo documento risulta già caricato.",
    };
  }

  if (status === 422) {
    return {
      variant: "error",
      title: "Dati non validi",
      message:
        message ||
        "Il file caricato non è valido o non è leggibile. Controlla il documento e riprova.",
    };
  }

  if (status >= 500) {
    return {
      variant: "error",
      title: "Errore del server",
      message: SERVER_ERROR_MESSAGE,
    };
  }

  return {
    variant: "error",
    title: "Caricamento non riuscito",
    message:
      message ||
      (status
        ? `Il server ha rifiutato il file (errore ${status}).`
        : UNEXPECTED_ERROR_MESSAGE),
  };
}

export class UploadApiError extends Error {
  constructor(uploadError) {
    super(uploadError.message);
    this.name = "UploadApiError";
    this.uploadError = uploadError;
  }
}

export async function uploadErrorFromResponse(response) {
  let bodyText = "";

  try {
    bodyText = await response.text();
  } catch {
    bodyText = "";
  }

  return buildUploadError({
    status: response.status,
    detail: extractApiErrorMessage(bodyText),
  });
}

export function toUploadError(error) {
  if (error instanceof UploadApiError) return error.uploadError;

  if (error instanceof TypeError) {
    return {
      variant: "error",
      title: "Connessione non riuscita",
      message: NETWORK_ERROR_MESSAGE,
    };
  }

  return {
    variant: "error",
    title: "Caricamento non riuscito",
    message: UNEXPECTED_ERROR_MESSAGE,
  };
}
