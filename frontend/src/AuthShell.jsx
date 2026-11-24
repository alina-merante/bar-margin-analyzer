import { useCallback, useEffect, useRef, useState } from "react";
import App from "./App";
import { ApiContext } from "./ApiContext";
import { authRequest, createTenantClient } from "./apiClient";

const jsonHeaders = { "Content-Type": "application/json" };
const loginLockKey = "barmanager.loginBlockedUntil";

function readLoginLock() {
  try {
    const value = Number(sessionStorage.getItem(loginLockKey));
    return Number.isFinite(value) && value > Date.now() ? value : 0;
  } catch {
    return 0;
  }
}

function saveLoginLock(until) {
  try {
    if (until > 0) {
      sessionStorage.setItem(loginLockKey, String(until));
    } else {
      sessionStorage.removeItem(loginLockKey);
    }
  } catch {
    // Il controllo di sicurezza rimane attivo sul server.
  }
}

function retryDelay(value) {
  if (value && /^\d+$/.test(value)) {
    const seconds = Number(value);
    if (Number.isSafeInteger(seconds) && seconds > 0) return seconds;
  }
  return 900;
}

function authErrorMessage(err) {
  if (err.message === "authenticated session changed") {
    return "La sessione è cambiata. Accedi nuovamente.";
  }
  if (err.message === "invalid CSRF token") {
    return "Verifica di sicurezza non riuscita. Ripristina la sessione.";
  }
  if (err.status === 401) return "Sessione scaduta o credenziali non valide.";
  if (err.status === 403) return "Operazione non autorizzata.";
  if (err.status === 409) return "La sessione o il contesto sono cambiati.";
  if (err.status === 429) return "Troppi tentativi. Riprova più tardi.";
  if (err.status >= 500) return "Servizio temporaneamente non disponibile.";
  return "Impossibile completare la richiesta. Riprova.";
}

async function restoreSession(expectedSessionId = null) {
  const options = expectedSessionId === null
    ? {}
    : {
        headers: {
          "X-Expected-Session-ID": String(expectedSessionId)
        }
      };

  const session = await authRequest("/session", options);

  const boundOptions = {
    headers: {
      "X-Expected-Session-ID": String(session.session_id)
    }
  };

  const { csrf_token } = await authRequest("/csrf", boundOptions);
  const bars = await authRequest("/bars", boundOptions);

  return { session, csrf_token, bars };
}

export default function AuthShell() {
  const [user, setUser] = useState(null);
  const [bars, setBars] = useState([]);
  const [bar, setBar] = useState(null);
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [blockedUntil, setBlockedUntil] = useState(readLoginLock);
  const [now, setNow] = useState(Date.now);
  const remaining = Math.max(0, Math.ceil((blockedUntil - now) / 1000));
  const countdown = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;

  useEffect(() => {
    if (!blockedUntil) return;
    const tick = () => {
      const current = Date.now();
      setNow(current);
      if (current >= blockedUntil) {
        setBlockedUntil(0);
        saveLoginLock(0);
      }
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [blockedUntil]);
  const csrf = useRef("");
  const sessionId = useRef(null);
  const clientRef = useRef(null);
  const initialRestore = useRef(null);

  const closeContext = useCallback(() => {
    clientRef.current?.close();
    clientRef.current = null;
    setClient(null);
    setBar(null);
  }, []);

  const clearSession = useCallback(() => {
    closeContext();
    csrf.current = "";
    sessionId.current = null;
    setUser(null);
    setBars([]);
    setPassword("");
    window.history.replaceState(null, "", "/");
  }, [closeContext]);

  const openContext = useCallback((selected) => {
    if (!selected) return;
    const next = createTenantClient(selected.id, () => csrf.current, (status, detail) => {
      if (clientRef.current !== next) return;
      closeContext();
      if (
        status === 401 ||
        detail === "authenticated session changed"
      ) {
        clearSession();
        setError(
          detail === "authenticated session changed"
            ? "La sessione è cambiata in un'altra scheda. Accedi nuovamente."
            : "Sessione scaduta o revocata. Accedi nuovamente."
        );
      } else {
        setError(
          detail === "invalid CSRF token"
            ? "La sessione è cambiata in un'altra scheda. Ripristina la sessione prima di riprovare."
            : "Il contesto del bar è cambiato o non è più accessibile. Ripristina la sessione."
        );
      }
    }, (token) => {
      csrf.current = token;
    }, () => sessionId.current);
    clientRef.current = next;
    setClient(next);
    setBar(selected);
  }, [closeContext, clearSession]);

  const applySession = useCallback((data) => {
    csrf.current = data.csrf_token;
    sessionId.current = data.session.session_id;
    setUser(data.session.user);
    setBars(data.bars);
    openContext(data.bars.find((item) => item.selected));
  }, [openContext]);

  useEffect(() => {
    let active = true;
    if (!initialRestore.current) initialRestore.current = restoreSession();
    initialRestore.current.then(
      (data) => { if (active) applySession(data); },
      (err) => {
        if (active && err.status !== 401) setError(`Impossibile ripristinare la sessione: ${authErrorMessage(err)}`);
      }
    ).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [applySession]);

  async function restore() {
    closeContext();
    setBusy(true);
    setError("");
    try {
      applySession(await restoreSession(sessionId.current));
    } catch (err) {
      if (
        err.status === 401 ||
        err.message === "authenticated session changed"
      ) {
        clearSession();
        setError(
          err.message === "authenticated session changed"
            ? "La sessione è cambiata in un'altra scheda. Accedi nuovamente."
            : "Sessione scaduta o revocata. Accedi nuovamente."
        );
      } else {
        setError(`Impossibile ripristinare la sessione: ${authErrorMessage(err)}`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function login(event) {
    event.preventDefault();
    if (busy || blockedUntil > Date.now()) return;
    setBusy(true);
    setError("");
    try {
      const preAuth = await authRequest("/login-csrf");
      const session = await authRequest("/login", {
        method: "POST",
        headers: { ...jsonHeaders, "X-CSRF-Token": preAuth.csrf_token },
        body: JSON.stringify({ email, password }),
      });
      setPassword("");

      const accessibleBars = await authRequest("/bars", {
        headers: {
          "X-Expected-Session-ID": String(session.session_id)
        }
      });

      csrf.current = session.csrf_token;
      sessionId.current = session.session_id;
      setUser(session.user);
      setBars(accessibleBars);
      // A new login starts a new navigation session.
      // App redirects "/" to the first page permitted for this user.
      window.history.replaceState(null, "", "/");
      openContext(accessibleBars.find((item) => item.selected));
    } catch (err) {
      setPassword("");
      if (err.status === 429) {
        const current = Date.now();
        const until = current + retryDelay(err.retryAfter) * 1000;
        setNow(current);
        setBlockedUntil(until);
        saveLoginLock(until);
        setError("");
      } else {
        setError(err.status === 401
          ? "Email o password non valide."
          : `Accesso non riuscito: ${authErrorMessage(err)}`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function selectBar(id) {
    closeContext();
    setBusy(true);
    setError("");
    try {
      const expectedSessionId = String(sessionId.current);

      const requestSelection = (token) =>
        authRequest("/active-bar", {
          method: "PUT",
          headers: {
            ...jsonHeaders,
            "X-CSRF-Token": token,
            "X-Expected-Session-ID": expectedSessionId,
          },
          body: JSON.stringify({ bar_id: Number(id) }),
        });

      let selected;

      try {
        selected = await requestSelection(csrf.current);
      } catch (err) {
        if (
          err.status !== 403 ||
          err.message !== "invalid CSRF token"
        ) {
          throw err;
        }

        const currentSession = await authRequest("/session", {
          headers: {
            "X-Expected-Session-ID": expectedSessionId
          }
        });

        if (
          String(currentSession.session_id) !== expectedSessionId ||
          String(sessionId.current) !== expectedSessionId
        ) {
          const error = new Error("authenticated session changed");
          error.status = 409;
          throw error;
        }

        const refreshed = await authRequest("/csrf", {
          headers: {
            "X-Expected-Session-ID": expectedSessionId
          }
        });
        const verifiedSession = await authRequest("/session", {
          headers: {
            "X-Expected-Session-ID": expectedSessionId
          }
        });

        if (
          String(verifiedSession.session_id) !== expectedSessionId ||
          String(sessionId.current) !== expectedSessionId
        ) {
          const error = new Error("authenticated session changed");
          error.status = 409;
          throw error;
        }

        csrf.current = refreshed.csrf_token;
        selected = await requestSelection(csrf.current);
      }
      setBars((current) => current.map((item) => ({ ...item, selected: item.id === selected.id })));
      openContext(selected);
    } catch (err) {
      if (
        err.status === 401 ||
        err.message === "authenticated session changed"
      ) {
        clearSession();
      }
      setError(`Selezione non riuscita: ${authErrorMessage(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");

    try {
      const expectedSessionId = String(sessionId.current);

      const headers = {
        "X-Expected-Session-ID": expectedSessionId
      };

      const refreshed = await authRequest("/csrf", {
        headers
      });

      await authRequest("/logout", {
        method: "POST",
        headers: {
          ...headers,
          "X-CSRF-Token": refreshed.csrf_token
        },
      });

      clearSession();

    } catch (err) {
      if (
        err.status === 401 ||
        err.message === "authenticated session changed"
      ) {
        clearSession();

        setError(
          err.message === "authenticated session changed"
            ? "La sessione è cambiata in un'altra scheda. Accedi nuovamente."
            : "Sessione scaduta o revocata. Accedi nuovamente."
        );
      } else {
        setError(
          `Logout non completato: ${authErrorMessage(err)}. Ripristina la sessione e riprova.`
        );
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="auth-page">Caricamento sessione...</main>;
  if (!user) {
    return (
      <main className="auth-page">
        <form className="auth-card" onSubmit={login}>
          <h1>BarManager</h1>
          <h2>Accedi</h2>
          {remaining > 0 && (
            <div className="auth-lock-warning">
              <div role="alert">
                <strong>Accesso temporaneamente bloccato</strong>
                <p>Hai effettuato troppi tentativi di accesso. Per motivi di sicurezza, attendi prima di riprovare.</p>
              </div>
              <p className="auth-lock-countdown" role="timer">
                Tempo di attesa: {countdown}
              </p>
            </div>
          )}
          {error && <p role="alert">{error}</p>}
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <button type="submit" disabled={busy || remaining > 0}>Accedi</button>
        </form>
      </main>
    );
  }
  if (!client || !bar) {
    return (
      <main className="auth-page">
        <div className="auth-card">
          <h1>Seleziona un bar</h1>
          {error && <p role="alert">{error}</p>}
          {error ? <button type="button" onClick={restore} disabled={busy}>Ripristina sessione</button> : (
            bars.length ? bars.map((item) => (
              <button type="button" key={item.id} onClick={() => selectBar(item.id)} disabled={busy}>{item.name}</button>
            )) : <p>Nessun bar attivo assegnato a questo account.</p>
          )}
          <button type="button" onClick={logout} disabled={busy}>Esci</button>
        </div>
      </main>
    );
  }
  return (
    <ApiContext.Provider value={client}>
      {error && <p role="alert" className="auth-session-error">{error}</p>}
      <App key={bar.id} bars={bars} activeBar={bar} onSelectBar={selectBar} onLogout={logout} />
    </ApiContext.Provider>
  );
}
