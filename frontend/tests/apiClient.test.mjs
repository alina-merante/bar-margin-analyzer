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
