import { test, expect } from "../../frontend/node_modules/@playwright/test/index.mjs";

const email = process.env.BMA_TEST_EMAIL;
const password = process.env.BMA_TEST_PASSWORD;

test.beforeEach(({}, testInfo) => {
  const simulated = /AT-007\.1[23]\b/.test(testInfo.title);

  if (!simulated && (!email || !password)) {
    throw new Error("Credenziali ambiente test mancanti");
  }
});

function loginButton(page) {
  return page.getByRole("button", {
    name: "Accedi",
    exact: true,
  });
}

async function login(page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await loginButton(page).click();

  const barSelection = page.getByRole("heading", {
    name: "Seleziona un bar",
  });

  const dashboard = page.locator(
    'nav a[href="/dashboard"]'
  );

  await expect(
    dashboard.or(barSelection)
  ).toBeVisible();

  if (await barSelection.isVisible()) {
    const barName = process.env.BMA_TEST_BAR;

    if (!barName) {
      throw new Error(
        "Impostare BMA_TEST_BAR per selezionare il bar"
      );
    }

    await page.getByRole("button", {
      name: barName,
      exact: true,
    }).click();
  }

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard).toBeVisible();
}

async function logout(page) {
  await page.getByRole("button", {
    name: "Esci",
    exact: true,
  }).click();

  await expect(loginButton(page)).toBeVisible();
}

async function navigate(page, path) {
  await page.locator(`nav a[href="${path}"]`).click();
  await expect.poll(
    () => new URL(page.url()).pathname
  ).toBe(path);
}

test.describe("AT-001 - Autenticazione", () => {

  test("AT-001.01 - Login valido", async ({ page }) => {
    await login(page);
    await expect(page.getByLabel("Bar attivo")).toBeVisible();
  });

  test("AT-001.02 - Credenziali errate", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(
      "invalid-test-password-" + Date.now()
    );

    await loginButton(page).click();

    await expect(page.getByRole("alert")).toContainText(
      "Email o password non valide"
    );

    await expect(loginButton(page)).toBeVisible();
    await expect(page.locator("nav.sidebar-nav")).toHaveCount(0);
  });

  test("AT-001.03 - Elenco bar autorizzati", async ({ page }) => {
    const expected = process.env.BMA_EXPECTED_BARS;

    test.skip(!expected, "Elenco bar attesi non configurato");

    await login(page);

    const actual = await page.locator(
      ".bar-picker-option > span:first-child"
    ).allTextContents();

    expect(actual.sort()).toEqual(
      expected.split("|").map(s => s.trim()).sort()
    );
  });
});

test.describe("AT-007 - Navigazione e sessioni", () => {

  const pages = [
    ["01", "Fatture", "/invoices"],
    ["02", "Caricamenti", "/upload"],
    ["03", "Storico", "/cash-closures/history"],
  ];

  for (const [id, name, path] of pages) {
    test(`AT-007.${id} - Logout da ${name}`, async ({ page }) => {
      await login(page);
      await navigate(page, path);
      await logout(page);
      await login(page);

      await expect(page).toHaveURL(/\/dashboard$/);
    });
  }

  test("AT-007.04 - Refresh mantiene Fatture", async ({ page }) => {
    await login(page);
    await navigate(page, "/invoices");
    await page.reload();

    await expect(
      page.locator('nav a[href="/invoices"]')
    ).toBeVisible();

    await expect(page).toHaveURL(/\/invoices$/);
  });

  test("AT-007.05 - Logout dopo rotazione CSRF", async ({ page }) => {
    await login(page);
    await navigate(page, "/invoices");

    const rotation = await page.request.get("/api/auth/csrf");
    expect(rotation.ok()).toBeTruthy();

    const responsePromise = page.waitForResponse(
      r => r.url().endsWith("/api/auth/logout")
        && r.request().method() === "POST"
    );

    await logout(page);

    const response = await responsePromise;
    expect(response.status()).toBe(200);
  });

  test("AT-007.06 - Errore logout visibile", async ({ page }) => {
    await login(page);

    await page.route("**/api/auth/logout", route =>
      route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "invalid CSRF token",
        }),
      })
    );

    await page.getByRole("button", {
      name: "Esci",
      exact: true,
    }).click();

    await expect(page.getByRole("alert")).toContainText(
      "Logout non completato"
    );

    await expect(loginButton(page)).toHaveCount(0);
  });

  test("AT-007.07 - Pagina iniziale proprietario", async ({ page }) => {
    await login(page);
    await page.goto("/");

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(
      page.locator('nav a[href="/dashboard"]')
    ).toBeVisible();
  });

  test("AT-007.08 - Sessione revocata", async ({ page, context }) => {
    await login(page);

    const second = await context.newPage();
    await second.goto("/");

    await expect(
      second.locator('nav a[href="/dashboard"]')
    ).toBeVisible();

    await logout(second);

    await page.reload();
    await expect(loginButton(page)).toBeVisible();
    await expect(page.locator("nav.sidebar-nav")).toHaveCount(0);
  });

  test("AT-007.09 - Indietro dopo logout", async ({ page }) => {
    await login(page);
    await navigate(page, "/invoices");
    await navigate(page, "/upload");

    await logout(page);
    await page.goBack();

    await expect(loginButton(page)).toBeVisible();
    await expect(page.locator("nav.sidebar-nav")).toHaveCount(0);
  });

  test("AT-007.10 - Logout con due schede", async ({ page, context }) => {
    test.setTimeout(90000);
    await login(page);
    await navigate(page, "/invoices");

    const second = await context.newPage();
    await second.goto("/invoices");

    await expect(
      second.locator('nav a[href="/invoices"]')
    ).toBeVisible();

    await logout(second);

    await page.bringToFront();

    await expect(loginButton(page)).toBeVisible({
      timeout: 60000,
    });

    await expect(page.locator("nav.sidebar-nav")).toHaveCount(0);
  });

  test("AT-007.11 - Login concorrente da altra scheda", async ({ page, context }) => {
    await login(page);

    const original = await (
      await page.request.get("/api/auth/session")
    ).json();

    const second = await context.newPage();

    const preAuth = await second.request.get(
      "/api/auth/login-csrf"
    );

    expect(preAuth.ok()).toBeTruthy();

    const { csrf_token } = await preAuth.json();

    const response = await second.request.post(
      "/api/auth/login",
      {
        headers: {
          "Origin": new URL(page.url()).origin,
          "X-CSRF-Token": csrf_token,
        },
        data: { email, password },
      }
    );

    expect(response.status()).toBe(200);

    const current = await response.json();

    expect(current.session_id).not.toBe(original.session_id);

    await second.goto("/");
    await expect(loginButton(second)).toHaveCount(0);
  });
});


test("AT-007.12 - Avviso blocco temporaneo in italiano", async ({ page }) => {
    await page.route("**/api/auth/login", async (route) => {
        await route.fulfill({
            status: 429,
            contentType: "application/json",
            headers: { "Retry-After": "900" },
            body: JSON.stringify({
                detail: "too many login attempts; try again later"
            })
        });
    });

    await page.goto("/");
    await page.getByLabel("Email").fill("at-owner@barmanager.test");
    await page.getByLabel("Password").fill("password-simulata");
    await page.getByRole("button", {
        name: "Accedi", exact: true
    }).click();

    await expect(page.getByRole("alert")).toContainText(
        "Accesso temporaneamente bloccato"
    );

    await expect(page.getByRole("timer")).toContainText(
        "Tempo di attesa:"
    );

    await expect(page.getByRole("button", {
        name: "Accedi", exact: true
    })).toBeDisabled();

    await expect(page.getByLabel("Password")).toHaveValue("");
    await expect(page.getByRole("alert")).not.toContainText(
        "too many login attempts"
    );

    await page.reload();

    await expect(page.getByRole("alert")).toContainText(
        "Accesso temporaneamente bloccato"
    );

    await expect(page.getByRole("button", {
        name: "Accedi", exact: true
    })).toBeDisabled();
});


test("AT-007.13 - Riattivazione automatica dopo il blocco", async ({ page }) => {
    await page.route("**/api/auth/login", async (route) => {
        await route.fulfill({
            status: 429,
            contentType: "application/json",
            headers: { "Retry-After": "5" },
            body: JSON.stringify({
                detail: "too many login attempts; try again later"
            })
        });
    });

    await page.goto("/");
    await page.getByLabel("Email").fill("at-owner@barmanager.test");
    await page.getByLabel("Password").fill("password-simulata");

    const button = page.getByRole("button", {
        name: "Accedi", exact: true
    });

    await button.click();
    await expect(page.getByRole("timer")).toBeVisible();
    await expect(button).toBeDisabled();

    await expect(button).toBeEnabled({ timeout: 10000 });
    await expect(page.getByRole("timer")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
});
