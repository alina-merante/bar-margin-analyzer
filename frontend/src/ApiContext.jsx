import { createContext, useContext, useEffect, useState } from "react";
import { protectedUploadPath } from "./apiClient";

export const ApiContext = createContext(null);

export function useTenantApi() {
  return useContext(ApiContext);
}

export function useProtectedFiles(rawUrls) {
  const api = useTenantApi();
  const [result, setResult] = useState({ key: "", urls: [], error: "", loading: false });
  const key = rawUrls.filter(Boolean).join(",");

  useEffect(() => {
    let active = true;
    const created = [];
    if (!key) return undefined;
    // Hide any previous document immediately while fetching its replacement.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setResult({ key, urls: [], error: "", loading: true });
    async function load() {
      try {
        const urls = await Promise.all(key.split(",").map(async (raw) => {
          const response = await api.fetch(protectedUploadPath(raw.trim()));
          if (!response.ok) throw new Error(`Documento non disponibile (${response.status})`);
          const blob = await response.blob();
          const safeType = ["image/jpeg", "image/png", "image/webp", "application/pdf"].includes(blob.type)
            ? blob.type
            : "application/octet-stream";
          if (!active) return "";
          const url = URL.createObjectURL(new Blob([blob], { type: safeType }));
          created.push(url);
          return url;
        }));
        if (active) setResult({ key, urls, error: "", loading: false });
      } catch (error) {
        if (active) setResult({ key, urls: [], error: error.message, loading: false });
      }
    }
    load();
    return () => {
      active = false;
      created.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [api, key]);
  if (!key) return { urls: [], error: "", loading: false };
  return result.key === key ? result : { urls: [], error: "", loading: true };
}
