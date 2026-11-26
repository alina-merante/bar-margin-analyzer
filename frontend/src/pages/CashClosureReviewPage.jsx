import { useState } from "react";
import { CashClosureReviewCard } from "./UploadPage.jsx";

export default function CashClosureReviewPage({
  month,
  cashClosureReviews = [],
  cashClosureLoading = false,
  cashClosureLoadError = "",
  cashClosureRefreshWarning = "",
  retryCashClosureLoad,
  handleCorrectCashClosure,
  handleVerifyCashClosure,
  handleApproveCashClosure,
  handleRejectCashClosure,
  handleReprocessCashClosure,
}) {
  const [filter, setFilter] = useState("month");

  const visibleReviews = filter === "all"
    ? cashClosureReviews
    : cashClosureReviews.filter(
        (review) => review.date?.slice(0, 7) === month
      );

  return (
    <main className="main-content">
      <section className="upload-section">
        <div className="upload-history-card">
          <h2>Chiusure da verificare</h2>
          <p>Controlla i dati delle chiusure prima dell'approvazione.</p>

          <fieldset className="cash-review-filter">
            <legend>Mostra chiusure</legend>
            <label>
              <input
                type="radio"
                name="cash-review-page-filter"
                checked={filter === "month"}
                onChange={() => setFilter("month")}
              />
              Mese selezionato ({month})
            </label>
            <label>
              <input
                type="radio"
                name="cash-review-page-filter"
                checked={filter === "all"}
                onChange={() => setFilter("all")}
              />
              Tutte le chiusure in attesa
            </label>
          </fieldset>

          {filter === "all" && (
            <p>Questa vista include anche le chiusure senza data.</p>
          )}

          {cashClosureRefreshWarning && (
            <p role="alert">{cashClosureRefreshWarning}</p>
          )}

          {cashClosureLoadError && (
            <div role="alert">
              <p>{cashClosureLoadError}</p>
              <button type="button" onClick={retryCashClosureLoad}>
                Riprova
              </button>
            </div>
          )}

          {cashClosureLoading && (
            <p role="status">Caricamento delle chiusure...</p>
          )}

          {!cashClosureLoading && !cashClosureLoadError && (
            cashClosureReviews.length > 0 ? (
              <div className="cash-review-list">
                {cashClosureReviews.map((review) => (
                  <div
                    key={review.id}
                    hidden={filter === "month" && review.date?.slice(0, 7) !== month}
                  >
                    <CashClosureReviewCard
                      review={review}
                      onCorrect={handleCorrectCashClosure}
                      onVerify={handleVerifyCashClosure}
                      onApprove={handleApproveCashClosure}
                      onReject={handleRejectCashClosure}
                      onReprocess={handleReprocessCashClosure}
                    />
                  </div>
                ))}
                {visibleReviews.length === 0 && (
                  <p>Nessuna chiusura da verificare nel mese selezionato.</p>
                )}
              </div>
            ) : (
              <p>
                {filter === "month"
                  ? "Nessuna chiusura da verificare nel mese selezionato."
                  : "Nessuna chiusura in attesa di verifica."}
              </p>
            )
          )}
        </div>
      </section>
    </main>
  );
}
