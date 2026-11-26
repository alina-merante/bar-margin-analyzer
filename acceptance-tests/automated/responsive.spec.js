import { test, expect } from "../../frontend/node_modules/@playwright/test/index.mjs";

const resolutions = [
  [320, 568],
  [390, 844],
  [430, 932],
  [768, 1024],
  [1024, 768],
  [1280, 800],
  [1440, 900],
  [1920, 1080],
];

const pages = [
  "/dashboard",
  "/invoices",
  "/upload",
  "/cash-closures/review",
  "/cash-closures/history",
];

async function checkOverflow(page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;

    return [...document.querySelectorAll(
      "main, .dashboard-chart-card, .bar-group, " +
      ".invoice-filters-row, .invoice-status-filter, " +
      ".invoice-search-box, .invoice-clean-table-row, " +
      ".upload-history-card, .cash-review-card, " +
      ".cash-history-item"
    )].filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 &&
        (r.right > width + 2 || r.left < -2);
    }).map(el => ({
      element: el.className || el.tagName,
      right: Math.round(el.getBoundingClientRect().right),
      viewport: width,
    }));
  });
}

test("AT-RESP: layout operativo su otto risoluzioni", async ({ page }) => {
  test.setTimeout(240000);

  await page.goto("/");
  await page.getByLabel("Email").fill(process.env.BMA_TEST_EMAIL);
  await page.getByLabel("Password").fill(process.env.BMA_TEST_PASSWORD);
  await page.getByRole("button", { name: "Accedi", exact: true }).click();

  const selection = page.getByRole("heading", {
    name: "Seleziona un bar",
  });

  await expect(selection.or(page.locator("#active-bar"))).toBeVisible();

  if (await selection.isVisible()) {
    await page.getByRole("button", {
      name: process.env.BMA_TEST_BAR,
      exact: true,
    }).click();
  }

  await expect(page).toHaveURL(/\/dashboard$/);

  for (const [width, height] of resolutions) {
    await page.setViewportSize({ width, height });

    for (const path of pages) {
      await test.step(`${width}x${height} ${path}`, async () => {
        await page.goto(path);
        await expect(page).toHaveURL(new RegExp(path + "$"));
        await expect(page.locator("main")).toBeVisible();
        await page.evaluate(() => document.fonts.ready);

        const overflow = await checkOverflow(page);

        console.log(
          `${width}x${height} ${path}: ` +
          (overflow.length ? JSON.stringify(overflow) : "OK")
        );

        expect.soft(overflow, `${width}x${height} ${path}`).toEqual([]);
      });
    }
  }
});

test("AT-RESP: contenuti popolati e finestre modali", async ({ page }) => {
  test.setTimeout(240000);

  const month = new Date().toISOString().slice(0, 7);

  const invoice = {
    id: 999001,
    supplier: "Forniture alimentari e prodotti professionali per la ristorazione",
    invoice_number: "FT-2026-000012345678",
    invoice_date: `${month}-01`,
    date: `${month}-01`,
    due_date: `${month}-28`,
    total: 12345.67,
    linked_amount: 0,
    remaining_amount: 12345.67,
    status: "pending",
    category: "Alimentari",
    file_url: null,
  };

  const review = {
    id: 999002,
    date: `${month}-01`,
    closure_number: "RESP-TEST-001",
    total_amount: null,
    cash_amount: "255.50",
    card_amount: null,
    receipts_count: 25,
    receipts_total: null,
    anomalies: [],
    ocr_values: {},
    can_edit: true,
    can_verify: true,
    verification: null,
    created_at: new Date().toISOString(),
    document: {
      id: 999003,
      original_filename: "chiusura-test-responsive.png",
      file_url: "",
    },
  };

  await page.route("**/api/invoices", async route => {
    if (route.request().method() !== "GET") {
      return route.abort();
    }
    await route.fulfill({ json: [invoice] });
  });

  await page.route("**/api/cash-closures/review", async route => {
    if (route.request().method() !== "GET") {
      return route.abort();
    }
    await route.fulfill({ json: [review] });
  });

  await page.goto("/");
  await page.getByLabel("Email").fill(process.env.BMA_TEST_EMAIL);
  await page.getByLabel("Password").fill(process.env.BMA_TEST_PASSWORD);
  await page.getByRole("button", {
    name: "Accedi", exact: true
  }).click();

  const selection = page.getByRole("heading", {
    name: "Seleziona un bar",
  });

  await expect(selection.or(page.locator("#active-bar"))).toBeVisible();

  if (await selection.isVisible()) {
    await page.getByRole("button", {
      name: process.env.BMA_TEST_BAR,
      exact: true,
    }).click();
  }

  async function checkBounds(locator, label) {
    await expect(locator).toBeVisible();

    const result = await locator.evaluate(el => {
      const r = el.getBoundingClientRect();
      return {
        fits: r.left >= -2 &&
          r.right <= document.documentElement.clientWidth + 2,
        internalOverflow: el.scrollWidth > el.clientWidth + 2,
      };
    });

    expect.soft(result.fits, label).toBe(true);
    expect.soft(result.internalOverflow, label).toBe(false);
  }

  for (const [width, height] of resolutions) {
    await page.setViewportSize({ width, height });

    await test.step(`${width}x${height} fattura popolata`, async () => {
      await page.goto("/invoices");

      const row = page.locator(".invoice-clean-table-row")
        .filter({ hasText: invoice.supplier });

      await checkBounds(row, "Riga fattura");
      await expect(row.locator(".invoice-modern-total")).toBeVisible();

      await page.locator(".invoice-category-dropdown-btn").click();

      await checkBounds(
        page.locator(".invoice-category-popover-menu"),
        "Menu categorie"
      );

      await page.locator(".invoice-category-dropdown-btn").click();

      await page.locator(".invoice-manual-btn").click();

      await checkBounds(
        page.locator(".invoice-manual-modal"),
        "Modale fattura manuale"
      );

      console.log(`${width}x${height}: fatture controllate`);
    });

    await test.step(`${width}x${height} revisione OCR`, async () => {
      await page.goto("/cash-closures/review");

      const card = page.locator(".cash-review-card").first();

      await checkBounds(card, "Scheda OCR");
      await expect(card.locator("input").first()).toBeVisible();

      console.log(`${width}x${height}: OCR controllato`);
    });
  }
});
