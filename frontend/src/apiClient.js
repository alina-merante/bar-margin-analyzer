export async function authRequest(path, options = {}) {
  const response = await fetch(`/api/auth${path}`, {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = new Error(
      typeof body?.detail === "string" ? body.detail : `Errore API (${response.status})`
    );
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export function createTenantClient(barId, getCsrf, onContextError) {
  const controller = new AbortController();
  return {
    close() {
      controller.abort();
    },
    async fetch(path, options = {}) {
      if (typeof path !== "string" || !path.startsWith("/api/") || path.startsWith("/api//")) {
        throw new Error("Indirizzo API non valido");
      }
      if (controller.signal.aborted) throw new DOMException("Contesto chiuso", "AbortError");
      const method = (options.method || "GET").toUpperCase();
      const headers = new Headers(options.headers);
      headers.set("X-Expected-Bar-ID", String(barId));
      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        headers.set("X-CSRF-Token", getCsrf());
      }
      const response = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok && [400, 401, 403, 409, 428].includes(response.status)) {
        const body = await response.clone().json().catch(() => null);
        const detail = body?.detail;
        if (
          response.status === 401 ||
          response.status === 428 ||
          detail === "invalid expected bar id" ||
          detail === "no active bar selected" ||
          detail === "active bar does not match request" ||
          detail === "active bar changed during operation" ||
          detail === "active bar access denied" ||
          detail === "invalid CSRF token"
        ) {
          onContextError(response.status, detail);
        }
      }
      if (controller.signal.aborted) throw new DOMException("Contesto chiuso", "AbortError");
      return response;
    },
  };
}

export function protectedUploadPath(rawUrl) {
  if (typeof rawUrl !== "string" || !/^\/uploads\/(documents|previews|invoices)\/[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(rawUrl)) {
    throw new Error("Indirizzo documento non valido");
  }
  return `/api${rawUrl}`;
}
