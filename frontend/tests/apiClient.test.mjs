import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { authRequest, createTenantClient, protectedUploadPath } from "../src/apiClient.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("authentication uses same-origin cookies and returns backend errors", async () => {
  let request;
  globalThis.fetch = async (path, options) => {
    request = { path, options };
    return Response.json({ detail: "invalid email or password" }, { status: 401 });
  };
  await assert.rejects(authRequest("/login", { method: "POST" }), (error) => error.status === 401);
  assert.equal(request.path, "/api/auth/login");
  assert.equal(request.options.credentials, "same-origin");
  assert.equal(request.options.cache, "no-store");
});

test("tenant requests bind bar, CSRF and credentials without caching", async () => {
  const requests = [];
  globalThis.fetch = async (path, options) => {
    requests.push({ path, options });
    return Response.json({ ok: true });
  };
  const client = createTenantClient(-1, () => "csrf", () => assert.fail());
  await client.fetch("/api/analytics/overview");
  await client.fetch("/api/documents/upload", { method: "POST", body: new FormData() });
  assert.equal(requests[0].options.headers.get("X-Expected-Bar-ID"), "-1");
  assert.equal(requests[0].options.headers.get("X-CSRF-Token"), null);
  assert.equal(requests[1].options.headers.get("X-CSRF-Token"), "csrf");
  assert.equal(requests[1].options.credentials, "same-origin");
  assert.equal(requests[1].options.cache, "no-store");
});

test("closed context aborts old requests and cannot send requests for another bar", async () => {
  let signal;
  globalThis.fetch = (_path, options) => {
    signal = options.signal;
    return new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    });
  };
  const client = createTenantClient(1, () => "csrf", () => assert.fail());
  const pending = client.fetch("/api/invoices");
  client.close();
  await assert.rejects(pending, { name: "AbortError" });
  assert.equal(signal.aborted, true);
  await assert.rejects(client.fetch("/api/invoices"), { name: "AbortError" });
});

test("session and context failures are distinguished from ordinary conflicts", async () => {
  const errors = [];
  const client = createTenantClient(1, () => "csrf", (status, detail) => errors.push([status, detail]));
  globalThis.fetch = async () => Response.json({ detail: "invoice already exists" }, { status: 409 });
  await client.fetch("/api/invoices");
  assert.deepEqual(errors, []);
  globalThis.fetch = async () => Response.json({ detail: "active bar does not match request" }, { status: 409 });
  await client.fetch("/api/invoices");
  globalThis.fetch = async () => Response.json({ detail: "authentication required" }, { status: 401 });
  await client.fetch("/api/invoices");
  globalThis.fetch = async () => Response.json({ detail: "bar permission denied" }, { status: 403 });
  await client.fetch("/api/invoices");
  globalThis.fetch = async () => Response.json({ detail: "invalid CSRF token" }, { status: 403 });
  await client.fetch("/api/invoices", { method: "DELETE" });
  globalThis.fetch = async () => Response.json({ detail: "X-Expected-Bar-ID header is required" }, { status: 428 });
  await client.fetch("/api/invoices");
  assert.deepEqual(errors, [
    [409, "active bar does not match request"],
    [401, "authentication required"],
    [403, "invalid CSRF token"],
    [428, "X-Expected-Bar-ID header is required"],
  ]);
});

test("protected downloads only accept backend upload paths", () => {
  assert.equal(protectedUploadPath("/uploads/previews/file_1.png"), "/api/uploads/previews/file_1.png");
  for (const path of ["https://example.test/a", "//evil.test/a", "/uploads/documents/../secret", "/uploads/other/a"]) {
    assert.throws(() => protectedUploadPath(path));
  }
});

test("CSRF recovery retries a mutation once with refreshed token", async () => {
  const calls = [];
  let csrf = "old-token";
  const errors = [];

  globalThis.fetch = async (path, options) => {
    calls.push({
      path,
      token: options?.headers?.get?.("X-CSRF-Token"),
    });

    if (path === "/api/auth/csrf") {
      return Response.json({ csrf_token: "new-token" });
    }
    if (calls.filter((call) => call.path === "/api/invoices").length === 1) {
      return Response.json({ detail: "invalid CSRF token" }, { status: 403 });
    }
    return Response.json({ ok: true });
  };

  const client = createTenantClient(
    1,
    () => csrf,
    (status, detail) => errors.push([status, detail]),
    (token) => { csrf = token; }
  );

  const response = await client.fetch("/api/invoices", {
    method: "POST",
    body: JSON.stringify({ amount: 10 }),
  });

  assert.equal(response.status, 200);
  assert.equal(csrf, "new-token");
  assert.deepEqual(errors, []);
  assert.deepEqual(calls.map((call) => call.path), [
    "/api/invoices",
    "/api/auth/csrf",
    "/api/invoices",
  ]);
  assert.equal(calls[0].token, "old-token");
  assert.equal(calls[2].token, "new-token");
});

test("CSRF recovery never retries permission-denied responses", async () => {
  const calls = [];
  globalThis.fetch = async (path) => {
    calls.push(path);
    return Response.json({ detail: "bar permission denied" }, { status: 403 });
  };

  const client = createTenantClient(
    1,
    () => "csrf",
    () => assert.fail("Ordinary permission denial must not close context"),
    () => assert.fail("CSRF must not change")
  );

  const response = await client.fetch("/api/invoices", { method: "DELETE" });

  assert.equal(response.status, 403);
  assert.deepEqual(calls, ["/api/invoices"]);
});

test("CSRF recovery does not retry after context closure", async () => {
  let resolveRefresh;
  const calls = [];
  globalThis.fetch = (path) => {
    calls.push(path);
    if (path === "/api/auth/csrf") {
      return new Promise((resolve) => { resolveRefresh = resolve; });
    }
    return Promise.resolve(
      Response.json({ detail: "invalid CSRF token" }, { status: 403 })
    );
  };

  const client = createTenantClient(
    1,
    () => "old-token",
    () => assert.fail("Closed context must not report another error"),
    () => assert.fail("Closed context must not update CSRF")
  );

  const pending = client.fetch("/api/invoices", { method: "DELETE" });

  while (!resolveRefresh) {
    await new Promise((resolve) => setImmediate(resolve));
  }

  client.close();
  resolveRefresh(Response.json({ csrf_token: "new-token" }));

  await assert.rejects(pending, { name: "AbortError" });
  assert.deepEqual(calls, ["/api/invoices", "/api/auth/csrf"]);
});


test("CSRF recovery must not replay a mutation after session change", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];

  try {
    globalThis.fetch = async (url, options = {}) => {
      calls.push({ url, options });

      if (url === "/api/auth/session") {
        return new Response(
          JSON.stringify({ session_id: 999, user: { id: 1 } }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (url === "/api/auth/csrf") {
        return new Response(
          JSON.stringify({ csrf_token: "new-csrf" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({ detail: "invalid CSRF token" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    };

    const client = createTenantClient(
      1,
      () => "old-csrf",
      () => {},
      () => {},
      () => 123
    );

    await assert.rejects(
      client.fetch("/api/test", { method: "POST" }),
      { name: "AbortError" }
    );

    const mutations = calls.filter(
      (call) => call.url === "/api/test"
    );

    assert.equal(
      mutations.length,
      1,
      "A mutation must not be replayed under a different session"
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Session identity is included in authenticated reads", async () => {
  globalThis.fetch = async (_path, options) => {
    assert.equal(
      options.headers.get("X-Expected-Session-ID"),
      "123"
    );
    assert.equal(
      options.headers.get("X-CSRF-Token"),
      null
    );
    return Response.json({ ok: true });
  };

  const client = createTenantClient(
    4,
    () => "csrf",
    () => assert.fail(),
    () => {},
    () => 123
  );

  await client.fetch("/api/invoices");
});

test("Session identity remains fixed during client lifetime", async () => {
  let sessionId = 123;

  const client = createTenantClient(
    4,
    () => "csrf",
    () => assert.fail(),
    () => {},
    () => sessionId
  );

  sessionId = 999;

  globalThis.fetch = async (_path, options) => {
    assert.equal(
      options.headers.get("X-Expected-Session-ID"),
      "123"
    );
    return Response.json({ ok: true });
  };

  await client.fetch("/api/invoices");
  await client.fetch("/api/invoices", {
    method: "POST"
  });
});

test("Session mismatch closes the authenticated context", async () => {
  const errors = [];

  globalThis.fetch = async () =>
    Response.json(
      { detail: "authenticated session changed" },
      { status: 409 }
    );

  const client = createTenantClient(
    4,
    () => "csrf",
    (status, detail) => {
      errors.push([status, detail]);
      client.close();
    },
    () => {},
    () => 123
  );

  await assert.rejects(
    client.fetch("/api/invoices"),
    { name: "AbortError" }
  );

  assert.deepEqual(errors, [
    [409, "authenticated session changed"]
  ]);

  await assert.rejects(
    client.fetch("/api/invoices"),
    { name: "AbortError" }
  );
});

test("Concurrent mutations share a single CSRF refresh", async () => {
  let csrf = "old-token";
  let refreshCount = 0;
  let mutationCount = 0;

  globalThis.fetch = async (path, options) => {
    const headers = new Headers(options.headers);

    assert.equal(
      headers.get("X-Expected-Session-ID"),
      "123"
    );

    if (path === "/api/auth/session") {
      return Response.json({ session_id: 123 });
    }

    if (path === "/api/auth/csrf") {
      refreshCount++;

      await new Promise(resolve =>
        setTimeout(resolve, 30)
      );

      return Response.json({
        csrf_token: "new-token"
      });
    }

    mutationCount++;

    if (headers.get("X-CSRF-Token") === "old-token") {
      return Response.json(
        { detail: "invalid CSRF token" },
        { status: 403 }
      );
    }

    assert.equal(
      headers.get("X-CSRF-Token"),
      "new-token"
    );

    return Response.json({ ok: true });
  };

  const client = createTenantClient(
    4,
    () => csrf,
    () => assert.fail(),
    token => { csrf = token; },
    () => 123
  );

  const responses = await Promise.all([
    client.fetch("/api/invoices", { method: "POST" }),
    client.fetch("/api/documents", { method: "POST" })
  ]);

  assert.equal(responses[0].status, 200);
  assert.equal(responses[1].status, 200);
  assert.equal(refreshCount, 1);
  assert.equal(mutationCount, 4);
  assert.equal(csrf, "new-token");
});
