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
    error.retryAfter = response.headers.get("Retry-After");
    throw error;
  }
  return response.json();
}

export function createTenantClient(barId, getCsrf, onContextError, setCsrf, getSessionId) {
  const controller = new AbortController();
  const expectedSessionId =
    typeof getSessionId === "function"
      ? String(getSessionId())
      : null;

  let refreshPromise = null;

  async function refreshCsrf(failedToken) {
    if (controller.signal.aborted) {
      throw new DOMException("Contesto chiuso", "AbortError");
    }

    if (refreshPromise) return refreshPromise;

    if (getCsrf() !== failedToken) return getCsrf();

    refreshPromise = (async () => {
      const options = {
        signal: controller.signal,
        headers: expectedSessionId === null
          ? {}
          : { "X-Expected-Session-ID": expectedSessionId },
      };

      if (expectedSessionId !== null) {
        const current = await authRequest("/session", options);

        if (String(current.session_id) !== expectedSessionId) {
          const error = new Error("authenticated session changed");
          error.status = 409;
          throw error;
        }
      }

      const refreshed = await authRequest("/csrf", options);

      if (controller.signal.aborted) {
        throw new DOMException("Contesto chiuso", "AbortError");
      }

      setCsrf(refreshed.csrf_token);
      return refreshed.csrf_token;
    })();

    try {
      return await refreshPromise;
    } finally {
      refreshPromise = null;
    }
  }

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
      if (expectedSessionId !== null) {
        headers.set("X-Expected-Session-ID", expectedSessionId);
      }

      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        headers.set("X-CSRF-Token", getCsrf());
      }
      const requestOptions = {
        ...options,
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      };

      let response = await fetch(path, requestOptions);

      if (
        !response.ok &&
        response.status === 403 &&
        !["GET", "HEAD", "OPTIONS"].includes(method) &&
        typeof setCsrf === "function"
      ) {
        const body = await response.clone().json().catch(() => null);

        if (body?.detail === "invalid CSRF token") {
          try {
            const token = await refreshCsrf(
              headers.get("X-CSRF-Token")
            );

            if (controller.signal.aborted) {
              throw new DOMException("Contesto chiuso", "AbortError");
            }

            headers.set("X-CSRF-Token", token);

            response = await fetch(path, requestOptions);
          } catch (error) {
            if (controller.signal.aborted) {
              throw new DOMException("Contesto chiuso", "AbortError");
            }
            if (
              error.status === 401 ||
              (error.status === 409 &&
               error.message === "authenticated session changed")
            ) {
              onContextError(error.status, error.message);
              throw new DOMException("Contesto chiuso", "AbortError");
            }

            // Mantiene il 403 originale se il recupero non riesce.
          }
        }
      }

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
          detail === "invalid CSRF token" ||
          detail === "authenticated session changed"
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
