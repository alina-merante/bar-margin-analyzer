import { test, expect } from "../../frontend/node_modules/@playwright/test/index.mjs";

const email = process.env.BMA_TEST_EMAIL;
const password = process.env.BMA_TEST_PASSWORD;
const reason = "AT-CASH - Annullamento di prova";

test.describe.configure({ mode: "serial" });

async function login(page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {
    name: "Accedi", exact: true
  }).click();

  const selection = page.getByRole("heading", {
    name: "Seleziona un bar"
  });

  const dashboard = page.locator('nav a[href="/dashboard"]');

  await expect(dashboard.or(selection)).toBeVisible();

  if (await selection.isVisible()) {
    await page.getByRole("button", {
      name: "Bar Demo PWA", exact: true
    }).click();
  }

  await expect(dashboard).toBeVisible();

  await expect(
    page.locator("#active-bar-name")
  ).toHaveText("Bar Demo PWA");

  await expect(
    page.locator('.bar-picker-option[aria-pressed="true"]')
  ).toHaveAttribute("data-bar-id", "4");
}

async function navigate(page, path) {
  await page.locator(`nav a[href="${path}"]`).click();
  await expect.poll(
    () => new URL(page.url()).pathname
  ).toBe(path);
}

async function setMonth(page, month) {
  const labels = [
    "gennaio", "febbraio", "marzo", "aprile",
    "maggio", "giugno", "luglio", "agosto",
    "settembre", "ottobre", "novembre", "dicembre"
  ];

  const shortLabels = [
    "Gen", "Feb", "Mar", "Apr",
    "Mag", "Giu", "Lug", "Ago",
    "Set", "Ott", "Nov", "Dic"
  ];

  const [year, monthNumber] = month.split("-").map(Number);
  const expected = labels[monthNumber - 1] + " " + year;

  const button = page.locator(".month-label-button");

  await expect(button).toBeVisible();

  const current = (await button.innerText())
    .replace(/\s+/g, " ").trim().toLowerCase();

  if (current === expected) {
    await expect(button).toHaveText(expected);
    return;
  }

  await button.click();

  const monthButton = page.locator(".month-picker-month")
    .filter({
      hasText: new RegExp(
        "^" + shortLabels[monthNumber - 1] + "$", "i"
      )
    });

  await expect(monthButton).toBeVisible();
  await monthButton.click();

  await expect(button).toHaveText(expected);
}

function closure(page, suffix) {
  return page.locator(".cash-history-item").filter({
    has: page.getByRole("heading", {
      name: new RegExp(`Chiusura n\\. AT-CASH-${suffix}$`)
    })
  });
}

async function history(page, month = "2026-11") {
  await setMonth(page, month);
  await navigate(page, "/cash-closures/history");
  await expect(page.getByRole("heading", {
    name: "Storico chiusure di cassa"
  })).toBeVisible();
}

async function approved(page, suffix) {
  await expect(closure(page, suffix)).toBeVisible();
  await expect(closure(page, suffix)).toContainText("Approvata");
}

async function openAnnulment(page) {
  await approved(page, "A");
  await closure(page, "A").getByRole("button", {
    name: "Annulla chiusura", exact: true
  }).click();
}

async function revenue(page, expected) {
  const value = page.locator(".dashboard-kpi-card")
    .filter({ has: page.getByText("Ricavi totali", { exact: true }) })
    .locator(".kpi-value");

  await expect(value).toBeVisible();

  await expect.poll(async () => {
    const raw = await value.innerText();
    return Number(
      raw.replace(/\s/g, "")
         .replace(/€/g, "")
         .replace(/\./g, "")
         .replace(",", ".")
    );
  }).toBe(expected);
}

test.beforeEach(async ({ page }) => {
  if (!email || !password) {
    throw new Error("Credenziali test mancanti");
  }

  await login(page);
});

test("AT-002.01 - Storico novembre", async ({ page }) => {
  await history(page);
  await approved(page, "A");
  await approved(page, "B");
  await expect(page.locator(".cash-history-item")).toHaveCount(2);
});

test("AT-002.02 - Cambio mese", async ({ page }) => {
  await history(page);
  await approved(page, "A");

  await setMonth(page, "2026-10");
  await approved(page, "C");

  await expect(closure(page, "A")).toHaveCount(0);
  await expect(closure(page, "B")).toHaveCount(0);

  await setMonth(page, "2026-11");
  await approved(page, "A");
  await approved(page, "B");
  await expect(closure(page, "C")).toHaveCount(0);
});

test("AT-002.03 - Date e importi", async ({ page }) => {
  await history(page);

  const a = closure(page, "A");
  const b = closure(page, "B");

  await approved(page, "A");
  await approved(page, "B");

  await expect(a).toContainText("23/11/2026");
  await expect(a).toContainText(/1\.?375,00/);
  await expect(a).toContainText("550,00");
  await expect(a).toContainText("825,00");

  await expect(b).toContainText("24/11/2026");
  await expect(b).toContainText("880,00");
  await expect(b).toContainText("330,00");
  await expect(b).toContainText("550,00");
});

test("AT-003.01 - Apertura annullamento", async ({ page }) => {
  await history(page);
  await openAnnulment(page);

  await expect(
    closure(page, "A").getByLabel("Motivo dell'annullamento")
  ).toBeVisible();
});

test("AT-003.02 - Motivazione obbligatoria", async ({ page }) => {
  await history(page);
  await openAnnulment(page);

  const a = closure(page, "A");

  const confirm = a.getByRole("button", {
    name: "Conferma annullamento", exact: true
  });

  await expect(confirm).toBeDisabled();

  await a.getByLabel("Motivo dell'annullamento").fill("   ");
  await expect(confirm).toBeDisabled();

  await a.getByLabel("Motivo dell'annullamento").fill(reason);
  await expect(confirm).toBeEnabled();
});

test("AT-003.03 - Rinuncia annullamento", async ({ page }) => {
  await history(page);
  await openAnnulment(page);

  const a = closure(page, "A");

  await a.getByLabel("Motivo dell'annullamento").fill(reason);
  await a.getByRole("button", {
    name: "Indietro", exact: true
  }).click();

  await approved(page, "A");

  await expect(
    a.getByLabel("Motivo dell'annullamento")
  ).toHaveCount(0);

  await page.reload();
  await history(page);
  await approved(page, "A");
});

test("AT-004.01 - Ricavi prima annullamento", async ({ page }) => {
  await setMonth(page, "2026-11");
  await navigate(page, "/dashboard");
  await revenue(page, 2255);
});

test("AT-003.04 - Annullamento effettivo", async ({ page }) => {
  await history(page);
  await openAnnulment(page);

  const a = closure(page, "A");

  await expect(a).toContainText("AT-CASH-A.png");

  await a.getByLabel("Motivo dell'annullamento").fill(reason);

  const responsePromise = page.waitForResponse(r =>
    new URL(r.url()).pathname ===
      "/api/cash-closures/review/2/annul" &&
    r.request().method() === "POST"
  );

  await a.getByRole("button", {
    name: "Conferma annullamento", exact: true
  }).click();

  const response = await responsePromise;
  expect(response.status()).toBe(200);

  await expect(a).toContainText("Annullata");
  await expect(a).toContainText(reason);

  await page.reload();
  await history(page);

  await expect(a).toContainText("Annullata");
  await expect(a).toContainText(reason);

  await expect(a.getByRole("button", {
    name: "Annulla chiusura", exact: true
  })).toHaveCount(0);
});

test("AT-004.02 - Ricavi dopo annullamento", async ({ page }) => {
  await setMonth(page, "2026-11");
  await navigate(page, "/dashboard");
  await revenue(page, 880);
});

test("AT-004.03 - Integrita altre chiusure", async ({ page }) => {
  await history(page);

  await expect(closure(page, "A")).toContainText("Annullata");
  await expect(closure(page, "A")).toContainText(/1\.?375,00/);

  await approved(page, "B");
  await expect(closure(page, "B")).toContainText("880,00");

  await setMonth(page, "2026-10");
  await approved(page, "C");
  await expect(closure(page, "C")).toContainText("660,00");

  await navigate(page, "/dashboard");
  await revenue(page, 660);

  await setMonth(page, "2026-11");
  await revenue(page, 880);
});
