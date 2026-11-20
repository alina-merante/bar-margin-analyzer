import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { authRequest } from "../src/apiClient.js";

const authShell = readFileSync(
  new URL("../src/AuthShell.jsx", import.meta.url), "utf8"
);
const app = readFileSync(
  new URL("../src/App.jsx", import.meta.url), "utf8"
);

function functionBody(source, name, nextName) {
  const start = source.indexOf(`async function ${name}(`);
  const end = source.indexOf(`async function ${nextName}(`, start);
  assert.ok(start >= 0, `${name} non trovata`);
  assert.ok(end > start, `${nextName} non trovata`);
  return source.slice(start, end);
}

test("AT-007: new login resets navigation to the default route", () => {
  const login = functionBody(authShell, "login", "selectBar");
  assert.match(login, /window\.history\.replaceState\(null,\s*["']["']?,?\s*["']\/["']\)/);
  assert.match(login, /openContext\(/);
  assert.ok(
    login.indexOf('window.history.replaceState') <
    login.indexOf('openContext('),
    "Il reset della navigazione deve precedere l'apertura del bar"
  );
});

test("AT-007: root route redirects to the first authorized page", () => {
  assert.match(app, /const defaultPage\s*=/);
  assert.match(app, /path=["']\/["']/);
  assert.match(app, /<Navigate to=\{defaultPage\} replace/);
});

test("AT-007: session restoration does not reset navigation", () => {
  const restore = functionBody(authShell, "restore", "login");
  assert.doesNotMatch(restore, /history\.replaceState/);
});

test("AT-007: logout refreshes CSRF before sending the request", () => {
  const logout = authShell.slice(
    authShell.indexOf("async function logout("),
    authShell.indexOf("if (loading) return", authShell.indexOf("async function logout("))
  );

  const csrfIndex = logout.indexOf('authRequest("/csrf")');
  const logoutIndex = logout.indexOf('authRequest("/logout"');

  assert.ok(csrfIndex >= 0, "Manca il rinnovo CSRF");
  assert.ok(logoutIndex > csrfIndex, "Logout eseguito prima del rinnovo CSRF");
  assert.match(logout, /csrf\.current\s*=\s*refreshed\.csrf_token/);
  assert.match(logout, /"X-CSRF-Token": csrf\.current/);
});

test("AT-007: successful logout clears session and resets navigation", () => {
  const logout = authShell.slice(
    authShell.indexOf("async function logout("),
    authShell.indexOf("if (loading) return", authShell.indexOf("async function logout("))
  );
  assert.match(logout, /setUser\(null\)/);
  assert.match(logout, /setBars\(\[\]\)/);
  assert.match(logout, /window\.history\.replaceState\(null,\s*["']["']?,?\s*["']\/["']\)/);
});

test("AT-007: failed logout remains visible to the user", () => {
  const logout = authShell.slice(
    authShell.indexOf("async function logout("),
    authShell.indexOf("if (loading) return", authShell.indexOf("async function logout("))
  );
  assert.match(logout, /catch\s*\(err\)/);
  assert.match(logout, /Logout non completato/);
});

test("AT-007: authentication requests use same-origin credentials", async () => {
  const originalFetch = globalThis.fetch;
  try {
    const calls = [];
    globalThis.fetch = async (path, options) => {
      calls.push({ path, options });
      return Response.json({ csrf_token: "test-token" });
    };

    await authRequest("/csrf");
    await authRequest("/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": "test-token" },
    });

    assert.equal(calls[0].path, "/api/auth/csrf");
    assert.equal(calls[1].path, "/api/auth/logout");
    assert.equal(calls[0].options.credentials, "same-origin");
    assert.equal(calls[1].options.credentials, "same-origin");
    assert.equal(calls[1].options.headers["X-CSRF-Token"], "test-token");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
