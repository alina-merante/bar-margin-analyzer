import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";

const MONTHS = [
  "Gennaio",
  "Febbraio",
  "Marzo",
  "Aprile",
  "Maggio",
  "Giugno",
  "Luglio",
  "Agosto",
  "Settembre",
  "Ottobre",
  "Novembre",
  "Dicembre",
];

function formatMonthLabel(month) {
  if (!month) return "-";

  const [year, monthNum] = month.split("-").map(Number);

  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function shiftMonth(month, delta) {
  const [year, monthNum] = month.split("-").map(Number);
  const date = new Date(year, monthNum - 1 + delta, 1);

  const nextMonth = String(date.getMonth() + 1).padStart(2, "0");

  return `${date.getFullYear()}-${nextMonth}`;
}

export default function Sidebar({ user, month, setMonth, pendingInvoices = 0, bars, activeBar, onSelectBar, onLogout, canViewDashboard = false, canViewInvoices = false, canAccessUpload = false, canViewCashClosures = false, cashClosureNavigationEnabled = false }) {
  const [monthPickerOpen, setMonthPickerOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [barPickerOpen, setBarPickerOpen] = useState(false);
  const barPickerRef = useRef(null);
  const barButtonRef = useRef(null);

  useEffect(() => {
    if (!barPickerOpen) return;

    function closeOutside(event) {
      if (!barPickerRef.current?.contains(event.target)) {
        setBarPickerOpen(false);
      }
    }

    function closeOnEscape(event) {
      if (event.key === "Escape") {
        setBarPickerOpen(false);
        barButtonRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [barPickerOpen]);

  const roleLabels = {
    owner: "Proprietario",
    manager: "Responsabile",
    staff: "Dipendente",
  };

  const accountRole =
    user?.is_global_admin === true ||
    activeBar?.is_global_admin === true
      ? "Amministratore globale"
      : roleLabels[activeBar?.role] ?? "Ruolo non disponibile";

  const [selectedYear, selectedMonth] = month.split("-").map(Number);

  const years = Array.from({ length: 9 }, (_, index) => selectedYear - 4 + index);

  function selectMonth(year, monthIndex) {
    const nextMonth = String(monthIndex + 1).padStart(2, "0");
    setMonth(`${year}-${nextMonth}`);
    setMonthPickerOpen(false);
  }

  return (
    <aside className={`sidebar ${mobileMenuOpen ? "mobile-menu-open" : ""}`}>
      <div className="sidebar-logo">
        <button
          type="button"
          className="mobile-menu-toggle"
          aria-label={mobileMenuOpen ? "Chiudi menu" : "Apri menu"}
          aria-expanded={mobileMenuOpen}
          aria-controls="sidebar-navigation"
          onClick={() => setMobileMenuOpen(open => !open)}
        >
          {mobileMenuOpen ? "✕" : "☰"}
        </button>
        <div className="logo-icon">☕</div>
        <div className="logo-text">BarManager</div>
        <div className="logo-sub">Gestione margini</div>
      </div>

      <nav
        id="sidebar-navigation"
        className="sidebar-nav"
        onClick={(event) => {
          if (event.target.closest("a")) {
            setMobileMenuOpen(false);
          }
        }}
      >
        {(canViewDashboard || canViewInvoices) && (
          <div className="nav-label">Principale</div>
        )}

        {canViewDashboard && (
        <NavLink
          to="/dashboard"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">📊</span>
          Dashboard
        </NavLink>
        )}

        {canViewInvoices && <NavLink
          to="/invoices"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">🧾</span>
          Fatture

          {pendingInvoices > 0 && (
            <span className="nav-badge">{pendingInvoices}</span>
          )}
        </NavLink>}

        {canAccessUpload && <div className="nav-label">Documenti</div>}

        {canAccessUpload && <NavLink
          to="/upload"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">⬆️</span>
          Caricamenti
        </NavLink>}

        {canViewCashClosures && cashClosureNavigationEnabled && (
          <>
            <div className="nav-label">Chiusure di cassa</div>
            <NavLink
              to="/cash-closures/review"
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            >
              <span className="nav-icon">📋</span>
              Da verificare
            </NavLink>
            {<NavLink
              to="/cash-closures/history"
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            >
              <span className="nav-icon">🕘</span>
              Storico
            </NavLink>}
          </>
        )}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-account">
          <div className="sidebar-user">
            <span className="sidebar-user-label">
              Utente collegato
            </span>
            <div className="sidebar-user-email">
              {user?.email ?? "Email non disponibile"}
            </div>
            <div className="sidebar-user-role">
              {accountRole}
            </div>
          </div>
          <span id="active-bar-label">Bar attivo</span>

          <div className="bar-picker" ref={barPickerRef}>
            <button
              id="active-bar"
              ref={barButtonRef}
              type="button"
              className="bar-picker-trigger"
              aria-labelledby="active-bar-label active-bar-name"
              aria-expanded={barPickerOpen}
              aria-controls="active-bar-options"
              onClick={() => setBarPickerOpen((open) => !open)}
            >
              <span id="active-bar-name">{activeBar.name}</span>
              <span aria-hidden="true">
                {barPickerOpen ? "▴" : "▾"}
              </span>
            </button>

            <div
              id="active-bar-options"
              className="bar-picker-options"
              role="group"
              aria-label="Bar disponibili"
              hidden={!barPickerOpen}
            >
              {bars.map((bar) => (
                <button
                  key={bar.id}
                  type="button"
                  className="bar-picker-option"
                  aria-pressed={bar.id === activeBar.id}
                  data-bar-id={bar.id}
                  onClick={() => {
                    setBarPickerOpen(false);
                    barButtonRef.current?.focus();
                    if (bar.id !== activeBar.id) {
                      onSelectBar(String(bar.id));
                    }
                  }}
                >
                  <span>{bar.name}</span>
                  {bar.id === activeBar.id && (
                    <span aria-hidden="true">✓</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="sidebar-logout"
            onClick={onLogout}
          >
            <span aria-hidden="true">↪</span>
            Esci
          </button>
        </div>
        <div className="month-selector">
          <button
            type="button"
            className="month-nav-btn"
            onClick={() => setMonth(shiftMonth(month, -1))}
          >
            ◀
          </button>

          <div className="month-picker-wrapper">
           <button
  type="button"
  className="month-label month-label-button"
  onClick={() => setMonthPickerOpen((value) => !value)}
>
  {formatMonthLabel(month)}
</button>

            {monthPickerOpen ? (
              <div className="month-picker-popover">
                <div className="month-picker-years">
                  {years.map((year) => (
                    <button
                      key={year}
                      type="button"
                      className={`month-picker-year ${
                        year === selectedYear ? "active" : ""
                      }`}
                      onClick={() => setMonth(`${year}-${String(selectedMonth).padStart(2, "0")}`)}
                    >
                      {year}
                    </button>
                  ))}
                </div>

                <div className="month-picker-grid">
                  {MONTHS.map((monthName, index) => (
                    <button
                      key={monthName}
                      type="button"
                      className={`month-picker-month ${
                        index + 1 === selectedMonth ? "active" : ""
                      }`}
                      onClick={() => selectMonth(selectedYear, index)}
                    >
                      {monthName.slice(0, 3)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <button
            type="button"
            className="month-nav-btn"
            onClick={() => setMonth(shiftMonth(month, 1))}
          >
            ▶
          </button>
        </div>
      </div>
    </aside>
  );
}