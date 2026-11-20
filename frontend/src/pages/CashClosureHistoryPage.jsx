import { useEffect, useState } from "react";
import { useTenantApi } from "../ApiContext";

function formatAmount(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(number);
}

function formatDate(value) {
  if (!value) return "Data non disponibile";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export default function CashClosureHistoryPage({
  month,
  activeBarId,
  onHistoryChanged,
}) {
  const api = useTenantApi();
  const [state, setState] = useState({
    key: "",
    items: [],
    loading: true,
    error: "",
  });

  const [annulment, setAnnulment] = useState({
    id: null,
    contextKey: null,
    reason: "",
    busy: false,
    error: "",
  });

  const [refresh, setRefresh] = useState(0);
  const [refreshWarning, setRefreshWarning] = useState("");
  const key = `${activeBarId}:${month}`;

  async function confirmAnnulment() {
    const reason = annulment.reason.trim();

    if (
      !annulment.id ||
      annulment.contextKey !== key ||
      !reason ||
      annulment.busy
    ) return;

    setAnnulment((previous) => ({
      ...previous,
      busy: true,
      error: "",
    }));

    try {
      const response = await api.fetch(
        `/api/cash-closures/review/${annulment.id}/annul`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason }),
        }
      );

      if (!response.ok) {
        throw new Error(`Annullamento non riuscito (${response.status}).`);
      }

      setAnnulment({ id: null, contextKey: null, reason: "", busy: false, error: "" });
      setRefreshWarning("");
      setRefresh((value) => value + 1);

      try {
        await onHistoryChanged?.();
      } catch (refreshError) {
        console.error("Aggiornamento dopo annullamento:", refreshError);
        setRefreshWarning(
          "Chiusura annullata correttamente, ma non è stato possibile aggiornare tutti i dati. Ricarica la pagina."
        );
      }
    } catch (error) {
      setAnnulment((previous) => ({
        ...previous,
        busy: false,
        error: error.message || "Impossibile annullare la chiusura.",
      }));
    }
  }

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const response = await api.fetch(
          `/api/cash-closures/history?month=${encodeURIComponent(month)}`
        );

        if (!response.ok) {
          throw new Error(`Impossibile caricare lo storico (${response.status}).`);
        }

        const data = await response.json();

        if (active) {
          setState({
            key,
            items: Array.isArray(data) ? data : [],
            loading: false,
            error: "",
          });
        }
      } catch (error) {
        if (active) {
          setState({
            key,
            items: [],
            loading: false,
            error: error.message || "Errore nel caricamento dello storico.",
          });
        }
      }
    }

    load();

    return () => {
      active = false;
    };
  }, [api, month, activeBarId, key, refresh]);

  const current = state.key === key
    ? state
    : { key, items: [], loading: true, error: "" };

  return (
    <main className="main cash-closure-history-page">
      <section className="upload-section">
        <div className="upload-history-card">
          <h1>Storico chiusure di cassa</h1>
          <p>Consulta le chiusure approvate e annullate del mese selezionato.</p>

          {refreshWarning && (
            <p role="alert">{refreshWarning}</p>
          )}

          {current.loading && (
            <p role="status">Caricamento dello storico...</p>
          )}

          {current.error && (
            <div className="cash-history-error">
              <p role="alert">{current.error}</p>
              <button
                type="button"
                onClick={() => {
                  setState({
                    key,
                    items: [],
                    loading: true,
                    error: "",
                  });
                  setRefresh((value) => value + 1);
                }}
              >
                Riprova caricamento
              </button>
            </div>
          )}

          {!current.loading && !current.error && current.items.length === 0 && (
            <p>Nessuna chiusura presente nel mese selezionato.</p>
          )}

          {!current.loading && !current.error && current.items.length > 0 && (
            <div className="cash-history-list">
              {current.items.map((item) => (
                <article className="cash-history-item" key={item.id}>
                  <div>
                    <h2>
                      {formatDate(item.date)}
                      {item.closure_number
                        ? ` · Chiusura n. ${item.closure_number}`
                        : ""}
                    </h2>
                    <p>
                      {item.status === "annulled"
                        ? "Annullata"
                        : "Approvata"}
                    </p>
                    <p>
                      Documento: {item.document?.original_filename || "Non disponibile"}
                    </p>
                  </div>

                  <div>
                    <p><strong>Totale:</strong> {formatAmount(item.total_amount)}</p>
                    <p><strong>Contanti:</strong> {formatAmount(item.cash_amount)}</p>
                    <p><strong>Carte:</strong> {formatAmount(item.card_amount)}</p>
                  </div>

                  {item.status === "annulled" && item.annulment_reason && (
                    <p><strong>Motivo annullamento:</strong> {item.annulment_reason}</p>
                  )}

                  {item.status === "approved" && item.can_annul === true && (
                    <div>
                      {annulment.id !== item.id ||
                      annulment.contextKey !== key ? (
                        <button
                          type="button"
                          onClick={() => setAnnulment({
                            id: item.id,
                            contextKey: key,
                            reason: "",
                            busy: false,
                            error: "",
                          })}
                        >
                          Annulla chiusura
                        </button>
                      ) : (
                        <div>
                          <p>
                            Stai per annullare una chiusura approvata.
                            Conferma soltanto se necessario.
                          </p>
                          <label>
                            Motivo dell'annullamento
                            <textarea
                              value={annulment.reason}
                              maxLength={1000}
                              disabled={annulment.busy}
                              onChange={(event) => setAnnulment((previous) => ({
                                ...previous,
                                reason: event.target.value,
                              }))}
                            />
                          </label>
                          {annulment.error && (
                            <p role="alert">{annulment.error}</p>
                          )}
                          <button
                            type="button"
                            disabled={!annulment.reason.trim() || annulment.busy}
                            onClick={confirmAnnulment}
                          >
                            {annulment.busy
                              ? "Annullamento in corso..."
                              : "Conferma annullamento"}
                          </button>
                          <button
                            type="button"
                            disabled={annulment.busy}
                            onClick={() => setAnnulment({
                              id: null,
                              contextKey: null,
                              reason: "",
                              busy: false,
                              error: "",
                            })}
                          >
                            Indietro
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
