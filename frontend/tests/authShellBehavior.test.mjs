import assert from "node:assert/strict";
import { test, before, after, afterEach } from "node:test";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let server;
let AuthShell;
const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;

before(async () => {
  server = await createServer({
    root: new URL("..", import.meta.url).pathname,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
    plugins: [{
      name: "at007-app-stub",
      enforce: "pre",
      transform(code, id) {
        if (!id.split("?")[0].endsWith("/src/AuthShell.jsx")) return;
        const original = 'import App from "./App";';
        if (!code.includes(original)) {
          throw new Error("Import App inatteso");
        }
        return code.replace(
          original,
          'import App from "virtual:at007-app";'
        );
      },
      resolveId(id) {
        if (id === "virtual:at007-app") return "\0virtual:at007-app";
      },
      load(id) {
        if (id !== "\0virtual:at007-app") return;
        return `
          import React from "react";
          export default function App({ activeBar, onLogout }) {
            return React.createElement("main", null,
              React.createElement("h1", null, activeBar.name),
              React.createElement("button", {
                type: "button",
                onClick: onLogout
              }, "Esci")
            );
          }
        `;
      }
    }],
  });

  AuthShell = (
    await server.ssrLoadModule("/src/AuthShell.jsx")
  ).default;
});

after(async () => {
  await server?.close();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
});

const bar = {
  id: 1,
  name: "Bar Demo PWA",
  selected: true,
  role: "owner",
  permissions: [],
};

function setup(logoutStatus = 200) {
  const requests = [];
  const navigation = [];

  globalThis.window = {
    history: {
      replaceState: (...args) => navigation.push(args),
    },
  };

  globalThis.fetch = async (path, options = {}) => {
    requests.push({ path, options });

    if (path === "/api/auth/session") {
      return Response.json({ user: { id: 1, email: "demo@barmanager.test" } });
    }
    if (path === "/api/auth/csrf") {
      return Response.json({ csrf_token: "fresh-csrf" });
    }
    if (path === "/api/auth/bars") {
      return Response.json([bar]);
    }
    if (path === "/api/auth/logout") {
      return logoutStatus === 200
        ? Response.json({ ok: true })
        : Response.json(
            { detail: "invalid CSRF token" },
            { status: logoutStatus }
          );
    }

    throw new Error(`Richiesta inattesa: ${path}`);
  };

  return { requests, navigation };
}

async function mount() {
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(React.createElement(AuthShell));
  });
  return renderer;
}

function button(renderer, label) {
  return renderer.root.findAllByType("button")
    .find(node => node.children.includes(label));
}

test("AT-007 React: successful logout returns to login", async () => {
  const { requests, navigation } = setup();
  const renderer = await mount();

  assert.ok(button(renderer, "Esci"));

  await act(async () => {
    await button(renderer, "Esci").props.onClick();
  });

  assert.ok(button(renderer, "Accedi"));
  assert.equal(button(renderer, "Esci"), undefined);

  const logoutIndex = requests.findIndex(
    request => request.path === "/api/auth/logout"
  );

  assert.ok(logoutIndex > 0);
  assert.equal(requests[logoutIndex - 1].path, "/api/auth/csrf");
  assert.equal(
    requests[logoutIndex].options.headers["X-CSRF-Token"],
    "fresh-csrf"
  );
  assert.deepEqual(navigation.at(-1), [null, "", "/"]);

  await act(async () => renderer.unmount());
});

test("AT-007 React: rejected logout preserves active bar and shows error", async () => {
  const { navigation } = setup(403);
  const renderer = await mount();

  assert.ok(button(renderer, "Esci"));

  await act(async () => {
    await button(renderer, "Esci").props.onClick();
  });

  assert.ok(button(renderer, "Esci"));
  assert.equal(button(renderer, "Accedi"), undefined);
  assert.equal(navigation.length, 0);

  const alerts = renderer.root.findAllByProps({ role: "alert" });
  assert.ok(alerts.some(
    node => JSON.stringify(node.children).includes("Logout non completato")
  ));

  assert.ok(renderer.root.findAllByType("h1").some(
    node => node.children.includes("Bar Demo PWA")
  ));

  await act(async () => renderer.unmount());
});

test("AT-007 React: failed CSRF refresh does not log the user out", async () => {
  const { navigation } = setup();
  const previousFetch = globalThis.fetch;

  globalThis.fetch = async (path, options) => {
    if (path === "/api/auth/csrf") {
      const csrfCalls = globalThis.__at007CsrfCalls =
        (globalThis.__at007CsrfCalls ?? 0) + 1;

      if (csrfCalls > 1) {
        return Response.json(
          { detail: "CSRF temporarily unavailable" },
          { status: 503 }
        );
      }
    }
    return previousFetch(path, options);
  };

  globalThis.__at007CsrfCalls = 0;
  const renderer = await mount();

  await act(async () => {
    await button(renderer, "Esci").props.onClick();
  });

  assert.ok(button(renderer, "Esci"));
  assert.equal(navigation.length, 0);
  assert.ok(renderer.root.findAllByProps({ role: "alert" }).length > 0);

  await act(async () => renderer.unmount());
  delete globalThis.__at007CsrfCalls;
});
