import { useCallback, useEffect, useRef, useState } from "react";
import App from "./App";
import { ApiContext } from "./ApiContext";
import { authRequest, createTenantClient } from "./apiClient";

const jsonHeaders = { "Content-Type": "application/json" };

async function restoreSession() {
  const session = await authRequest("/session");
  const { csrf_token } = await authRequest("/csrf");
  const bars = await authRequest("/bars");
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
  const csrf = useRef("");
  const clientRef = useRef(null);
  const initialRestore = useRef(null);

  const closeContext = useCallback(() => {
    clientRef.current?.close();
    clientRef.current = null;
    setClient(null);
    setBar(null);
  }, []);

  const openContext = useCallback((selected) => {
    if (!selected) return;
    const next = createTenantClient(selected.id, () => csrf.current, (status, detail) => {
      if (clientRef.current !== next) return;
      closeContext();
      if (status === 401) {
        csrf.current = "";
        setUser(null);
        setError("Sessione scaduta o revocata. Accedi nuovamente.");
      } else {
        setError(
          detail === "invalid CSRF token"
            ? "La sessione è cambiata in un'altra scheda. Ripristina la sessione prima di riprovare."
            : "Il contesto del bar è cambiato o non è più accessibile. Ripristina la sessione."
        );
      }
    });
    clientRef.current = next;
    setClient(next);
    setBar(selected);
  }, [closeContext]);

  const applySession = useCallback((data) => {
    csrf.current = data.csrf_token;
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
        if (active && err.status !== 401) setError(`Impossibile ripristinare la sessione: ${err.message}`);
      }
    ).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [applySession]);

  async function restore() {
    closeContext();
    setBusy(true);
    setError("");
    try {
      applySession(await restoreSession());
    } catch (err) {
      if (err.status === 401) {
        csrf.current = "";
        setUser(null);
        setError("Sessione scaduta o revocata. Accedi nuovamente.");
      } else {
        setError(`Impossibile ripristinare la sessione: ${err.message}`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function login(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const preAuth = await authRequest("/csrf");
      const session = await authRequest("/login", {
        method: "POST",
        headers: { ...jsonHeaders, "X-CSRF-Token": preAuth.csrf_token },
        body: JSON.stringify({ email, password }),
      });
      setPassword("");
      csrf.current = session.csrf_token;
      setUser(session.user);
      const accessibleBars = await authRequest("/bars");
      setBars(accessibleBars);
      openContext(accessibleBars.find((item) => item.selected));
    } catch (err) {
      setError(err.status === 401 ? "Email o password non valide." : `Accesso non riuscito: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function selectBar(id) {
    closeContext();
    setBusy(true);
    setError("");
    try {
      const selected = await authRequest("/active-bar", {
        method: "PUT",
        headers: { ...jsonHeaders, "X-CSRF-Token": csrf.current },
        body: JSON.stringify({ bar_id: Number(id) }),
      });
      setBars((current) => current.map((item) => ({ ...item, selected: item.id === selected.id })));
      openContext(selected);
    } catch (err) {
      if (err.status === 401) {
        csrf.current = "";
        setUser(null);
      }
      setError(`Selezione non riuscita: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    closeContext();
    setBusy(true);
    setError("");
    try {
      await authRequest("/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf.current },
      });
      csrf.current = "";
      setUser(null);
      setBars([]);
    } catch (err) {
      setError(`Logout non completato: ${err.message}. Ripristina la sessione e riprova.`);
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
          {error && <p role="alert">{error}</p>}
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <button type="submit" disabled={busy}>Accedi</button>
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
      <App key={bar.id} bars={bars} activeBar={bar} onSelectBar={selectBar} onLogout={logout} />
    </ApiContext.Provider>
  );
}
