
import { test, expect } from "../../frontend/node_modules/@playwright/test/index.mjs";

const password = process.env.BMA_AT_PASSWORD;
const origin = "http://127.0.0.1:5174";
const primary = "Bar Demo PWA";
const secondary = "AT-Bar Secondario";

const accounts = {
    staff: "at-staff@barmanager.test",
    admin: "at-admin@barmanager.test",
    owner: "at-owner@barmanager.test",
};

async function login(page, role, bar = primary) {
    if (!password) {
        throw new Error("Password account di test mancante");
    }

    await page.goto("/");
    expect(new URL(page.url()).origin).toBe(origin);

    await page.getByLabel("Email").fill(accounts[role]);
    await page.getByLabel("Password").fill(password);
    const [response] = await Promise.all([
        page.waitForResponse(response =>
            new URL(response.url()).pathname === "/api/auth/login" &&
            response.request().method() === "POST"
        ),
        page.getByRole("button", {
            name: "Accedi", exact: true
        }).click()
    ]);

    const status = response.status();

    if (status !== 200) {
        const messages = {
            401: "Credenziali di test non valide",
            403: "Accesso non autorizzato",
            429: "Accesso temporaneamente bloccato"
        };

        throw new Error(
            `Autenticazione fallita (HTTP ${status}): ` +
            (messages[status] || "Errore inatteso")
        );
    }

    const selection = page.getByRole("heading", {
        name: "Seleziona un bar"
    });
    const selector = page.locator("#active-bar");

    await expect(selection.or(selector)).toBeVisible();

    if (await selection.isVisible()) {
        await page.getByRole("button", {
            name: bar, exact: true
        }).click();
    }

    await expect(selector).toBeVisible();

    const id = bar === primary ? "4" : "5";

    const selected = page.locator(
        '.bar-picker-option[aria-pressed="true"]'
    );

    if (await selected.getAttribute("data-bar-id") !== id) {
        await switchBar(page, id);
    }

    await expect(selected).toHaveAttribute("data-bar-id", id);
    await expect(
        page.locator("#active-bar-name")
    ).toHaveText(bar);
}

async function chooseBar(page, id) {
    await page.locator("#active-bar").click();
    await page.locator(
        `.bar-picker-option[data-bar-id="${id}"]`
    ).click();
}

async function switchBar(page, id) {
    await chooseBar(page, id);
    await expect(
        page.locator('.bar-picker-option[aria-pressed="true"]')
    ).toHaveAttribute("data-bar-id", String(id));
}

async function apiHeaders(page, barId) {
    const session = await page.request.get("/api/auth/session");
    expect(session.status()).toBe(200);

    const csrf = await page.request.get("/api/auth/csrf");
    expect(csrf.status()).toBe(200);

    return {
        "Origin": origin,
        "X-CSRF-Token": (await csrf.json()).csrf_token,
        "X-Expected-Session-ID":
            String((await session.json()).session_id),
        "X-Expected-Bar-ID": String(barId),
    };
}

function annulButton(page, suffix) {
    return closure(page, suffix).getByRole("button", {
        name: "Annulla chiusura",
        exact: true,
    });
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



test("AT-005.01 - Owner autorizzato ad annullare", async ({ page }) => {
    await login(page, "owner");
    await history(page);
    await approved(page, "A");
    await expect(annulButton(page, "A")).toBeVisible();
    await annulButton(page, "A").click();
    await expect(page.locator("textarea")).toBeVisible();
});

test("AT-005.02 - Staff autorizzato alla consultazione", async ({ page }) => {
    await login(page, "staff");
    await history(page);
    await approved(page, "A");
    await approved(page, "B");
    await expect(page.locator(".cash-history-item")).toHaveCount(2);
});

test("AT-005.03 - Staff senza pulsante annullamento", async ({ page }) => {
    await login(page, "staff");
    await history(page);
    await approved(page, "A");
    await approved(page, "B");
    await expect(annulButton(page, "A")).toHaveCount(0);
    await expect(annulButton(page, "B")).toHaveCount(0);
});

test("AT-005.04 - Backend nega annullamento allo staff", async ({ page }) => {
    await login(page, "staff");
    await history(page);
    await approved(page, "A");

    const headers = await apiHeaders(page, 4);

    const response = await page.request.post(
        "/api/cash-closures/review/2/annul",
        {
            headers,
            data: {
                reason: "AT-005.04 - Tentativo non autorizzato"
            },
        }
    );

    expect(response.status()).toBe(403);
    expect((await response.json()).detail)
        .toContain("Solo il proprietario");

    await page.reload();
    await approved(page, "A");
});

test("AT-005.05 - Admin globale senza membership", async ({ page }) => {
    await login(page, "admin");

    const options = await page.locator(
        ".bar-picker-option > span:first-child"
    ).allTextContents();

    expect(options.sort()).toEqual(
        [primary, secondary].sort()
    );

    await history(page);
    await approved(page, "A");
    await expect(annulButton(page, "A")).toBeVisible();

    await switchBar(page, 5);
    await history(page);
    await approved(page, "D");
    await expect(annulButton(page, "D")).toBeVisible();
});

test("AT-006.01 - Owner visualizza entrambi i bar", async ({ page }) => {
    await login(page, "owner");

    const options = await page.locator(
        ".bar-picker-option > span:first-child"
    ).allTextContents();

    expect(options.sort()).toEqual(
        [primary, secondary].sort()
    );
});

test("AT-006.02 - Isolamento storico chiusure", async ({ page }) => {
    await login(page, "owner");
    await history(page);

    await approved(page, "A");
    await approved(page, "B");
    await expect(closure(page, "D")).toHaveCount(0);

    await switchBar(page, 5);
    await history(page);

    await approved(page, "D");
    await expect(closure(page, "D")).toContainText("940,00");
    await expect(closure(page, "A")).toHaveCount(0);
    await expect(closure(page, "B")).toHaveCount(0);
    await expect(page.locator(".cash-history-item")).toHaveCount(1);

    await switchBar(page, 4);
    await history(page);

    await approved(page, "A");
    await approved(page, "B");
    await expect(closure(page, "D")).toHaveCount(0);
});

test("AT-006.03 - Isolamento ricavi dashboard", async ({ page }) => {
    await login(page, "owner");
    await setMonth(page, "2026-11");
    await navigate(page, "/dashboard");
    await revenue(page, 2255);

    await switchBar(page, 5);
    await setMonth(page, "2026-11");
    await navigate(page, "/dashboard");
    await revenue(page, 940);

    await switchBar(page, 4);
    await setMonth(page, "2026-11");
    await navigate(page, "/dashboard");
    await revenue(page, 2255);
});

test("AT-006.04 - Staff non accede al secondo bar", async ({ page }) => {
    await login(page, "staff");

    await expect(page.locator(".bar-picker-option > span:first-child"))
        .toHaveCount(1);

    const headers = await apiHeaders(page, 4);

    const response = await page.request.put(
        "/api/auth/active-bar",
        {
            headers,
            data: { bar_id: 5 },
        }
    );

    expect(response.status()).toBe(403);
    expect((await response.json()).detail)
        .toBe("bar access denied");

    const active = await page.request.get("/api/auth/active-bar");
    expect(active.status()).toBe(200);
    expect((await active.json()).id).toBe(4);

    const mismatch = await page.request.get(
        "/api/cash-closures/history?month=2026-11",
        {
            headers: {
                ...headers,
                "X-Expected-Bar-ID": "5",
            },
        }
    );

    expect(mismatch.status()).toBe(409);
});

test("AT-006.05 - Owner non modifica chiusure di altro bar", async ({ page }) => {
    await login(page, "owner");
    await history(page);

    const headers = await apiHeaders(page, 4);

    const response = await page.request.post(
        "/api/cash-closures/review/5/annul",
        {
            headers,
            data: {
                reason: "AT-006.05 - Tentativo cross-tenant"
            },
        }
    );

    expect(response.status()).toBe(404);

    await switchBar(page, 5);
    await history(page);
    await approved(page, "D");

    await navigate(page, "/dashboard");
    await revenue(page, 940);
});


test("AT-005.06 - Annullamento effettivo amministratore globale", async ({ page }) => {
    await login(page, "admin");

    await setMonth(page, "2026-11");
    await navigate(page, "/dashboard");
    await revenue(page, 2255);

    await history(page);
    await approved(page, "A");
    await approved(page, "B");

    await annulButton(page, "A").click();

    await page.locator("textarea").fill(
        "AT-CASH - Annullamento di prova"
    );

    const [response] = await Promise.all([
        page.waitForResponse(response =>
            new URL(response.url()).pathname ===
                "/api/cash-closures/review/2/annul" &&
            response.request().method() === "POST"
        ),
        page.getByRole("button", {
            name: "Conferma annullamento",
            exact: true
        }).click()
    ]);

    expect(response.status()).toBe(200);

    const result = await response.json();

    expect(result.status).toBe("annulled");
    expect(result.annulled_by_user_id).toBe(6);
    expect(result.annulment_reason).toBe(
        "AT-CASH - Annullamento di prova"
    );

    await expect(closure(page, "A")).toContainText("Annullata");
    await expect(annulButton(page, "A")).toHaveCount(0);
    await approved(page, "B");

    await page.reload();

    await expect(closure(page, "A")).toContainText("Annullata");
    await approved(page, "B");

    await navigate(page, "/dashboard");
    await revenue(page, 880);

    await switchBar(page, 5);
    await history(page);
    await approved(page, "D");
    await expect(closure(page, "A")).toHaveCount(0);

    await navigate(page, "/dashboard");
    await revenue(page, 940);

    await switchBar(page, 4);
    await history(page);

    await expect(closure(page, "A")).toContainText("Annullata");
    await approved(page, "B");
});


async function replaceBrowserSession(page, role) {
    const previous = await page.request.get(
        "/api/auth/session"
    );

    expect(previous.status()).toBe(200);

    const old = await previous.json();

    const preAuth = await page.request.get(
        "/api/auth/login-csrf"
    );

    expect(preAuth.status()).toBe(200);

    const response = await page.request.post(
        "/api/auth/login",
        {
            headers: {
                "Origin": origin,
                "X-CSRF-Token":
                    (await preAuth.json()).csrf_token,
            },
            data: {
                email: accounts[role],
                password,
            },
        }
    );

    expect(response.status()).toBe(200);

    const current = await response.json();

    expect(current.session_id).not.toBe(old.session_id);
    expect(current.user.id).not.toBe(old.user.id);
    expect(current.user.email).toBe(accounts[role]);

    return { old, current };
}


test("AT-007.14 - Lettura bloccata dopo cambio utente", async ({ page }) => {
    await login(page, "admin", secondary);

    const { old, current } =
        await replaceBrowserSession(page, "staff");

    const headers = {
        "X-Expected-Session-ID": String(old.session_id),
    };

    for (const endpoint of [
        "/api/auth/session",
        "/api/auth/bars",
    ]) {
        const response = await page.request.get(
            endpoint,
            { headers }
        );

        expect(response.status()).toBe(409);
        expect((await response.json()).detail).toBe(
            "authenticated session changed"
        );
    }

    const active = await page.request.get(
        "/api/auth/session",
        {
            headers: {
                "X-Expected-Session-ID":
                    String(current.session_id),
            },
        }
    );

    expect(active.status()).toBe(200);
    expect((await active.json()).user.email).toBe(
        accounts.staff
    );
});


test("AT-007.15 - Rinnovo CSRF bloccato per vecchia sessione", async ({ page }) => {
    await login(page, "admin");

    const { old, current } =
        await replaceBrowserSession(page, "staff");

    const before = await page.context().cookies();

    const response = await page.request.get(
        "/api/auth/csrf",
        {
            headers: {
                "X-Expected-Session-ID":
                    String(old.session_id),
            },
        }
    );

    expect(response.status()).toBe(409);
    expect((await response.json()).detail).toBe(
        "authenticated session changed"
    );

    expect(response.headers()["set-cookie"])
        .toBeUndefined();

    const after = await page.context().cookies();

    expect(
        after.find(c => c.name === "barmanager_csrf")
    ).toEqual(
        before.find(c => c.name === "barmanager_csrf")
    );

    const valid = await page.request.get(
        "/api/auth/csrf",
        {
            headers: {
                "X-Expected-Session-ID":
                    String(current.session_id),
            },
        }
    );

    expect(valid.status()).toBe(200);

    expect((await valid.json()).csrf_token)
        .not.toBe(current.csrf_token);
});


test("AT-007.16 - Vecchia sessione non può disconnettere il nuovo utente", async ({ page }) => {
    await login(page, "admin");

    const { old, current } =
        await replaceBrowserSession(page, "staff");

    const response = await page.request.post(
        "/api/auth/logout",
        {
            headers: {
                "Origin": origin,
                "X-CSRF-Token": current.csrf_token,
                "X-Expected-Session-ID":
                    String(old.session_id),
            },
        }
    );

    expect(response.status()).toBe(409);
    expect((await response.json()).detail).toBe(
        "authenticated session changed"
    );

    expect(response.headers()["set-cookie"])
        .toBeUndefined();

    const active = await page.request.get(
        "/api/auth/session"
    );

    expect(active.status()).toBe(200);

    const session = await active.json();

    expect(session.session_id).toBe(current.session_id);
    expect(session.user.email).toBe(accounts.staff);
});


async function openStaffSession(page, current) {
    await page.goto("/");

    const selection = page.getByRole("heading", {
        name: "Seleziona un bar"
    });

    const selector = page.locator("#active-bar");

    await expect(selection.or(selector)).toBeVisible();

    if (await selection.isVisible()) {
        await expect(
            page.getByRole("button", {
                name: secondary,
                exact: true
            })
        ).toHaveCount(0);

        await page.getByRole("button", {
            name: primary,
            exact: true
        }).click();
    }

    await expect(
        page.locator('.bar-picker-option[aria-pressed="true"]')
    ).toHaveAttribute("data-bar-id", "4");

    await expect(
        page.locator("#active-bar-name")
    ).toHaveText(primary);

    await expect(
        page.locator('.bar-picker-option[data-bar-id="5"]')
    ).toHaveCount(0);

    await expectCurrentIdentity(page, current);
}


async function expectNewLoginRequired(page) {
    await expect(
        page.getByRole("button", {
            name: "Accedi",
            exact: true,
        })
    ).toBeVisible({ timeout: 60000 });

    await expect(
        page.locator("#active-bar")
    ).toHaveCount(0);

    await expect(
        page.locator("nav.sidebar-nav")
    ).toHaveCount(0);
}


async function expectCurrentIdentity(page, current) {
    const response = await page.request.get(
        "/api/auth/session"
    );

    expect(response.status()).toBe(200);

    const session = await response.json();

    expect(session.session_id).toBe(current.session_id);
    expect(session.user.email).toBe(current.user.email);
}


test("AT-007.17 - Vecchia scheda torna al login dopo cambio utente", async ({ page, context }) => {
    test.setTimeout(90000);

    await login(page, "admin", secondary);
    await history(page);
    await approved(page, "D");

    const second = await context.newPage();

    const { current } =
        await replaceBrowserSession(second, "staff");

    await openStaffSession(second, current);

    await page.bringToFront();

    await expectNewLoginRequired(page);

    await expect(
        page.getByText(
            "La sessione è cambiata in un'altra scheda. Accedi nuovamente.",
            { exact: true }
        )
    ).toBeVisible();

    await expectCurrentIdentity(second, current);

    await history(second);
    await approved(second, "B");

    await expect(
        closure(second, "D")
    ).toHaveCount(0);
});


test("AT-007.18 - Logout dalla vecchia scheda protegge il nuovo utente", async ({ page, context }) => {
    await login(page, "admin");

    const second = await context.newPage();

    const { current } =
        await replaceBrowserSession(second, "staff");

    const [response] = await Promise.all([
        page.waitForResponse(response =>
            new URL(response.url()).pathname ===
                "/api/auth/csrf" &&
            response.request().method() === "GET"
        ),
        page.getByRole("button", {
            name: "Esci",
            exact: true,
        }).click()
    ]);

    expect(response.status()).toBe(409);

    await expectNewLoginRequired(page);

    await expect(
        page.getByText(
            "La sessione è cambiata in un'altra scheda. Accedi nuovamente.",
            { exact: true }
        )
    ).toBeVisible();

    await expectCurrentIdentity(second, current);

    await openStaffSession(second, current);
});


test("AT-007.19 - Cambio bar bloccato dalla vecchia scheda", async ({ page, context }) => {
    await login(page, "admin", primary);

    const second = await context.newPage();

    const { current } =
        await replaceBrowserSession(second, "staff");

    const [response] = await Promise.all([
        page.waitForResponse(response =>
            new URL(response.url()).pathname ===
                "/api/auth/active-bar" &&
            response.request().method() === "PUT"
        ),
        chooseBar(page, 5)
    ]);

    expect(response.status()).toBe(409);

    await expectNewLoginRequired(page);

    await expect(
        page.getByText(/Selezione non riuscita:/)
    ).toBeVisible();

    await expect(
        page.getByText(/authenticated session changed/)
    ).toHaveCount(0);

    await expectCurrentIdentity(second, current);

    await openStaffSession(second, current);

    await expect(
        second.locator('.bar-picker-option[data-bar-id="5"]')
    ).toHaveCount(0);
});


test("AT-007.20 - Recupero CSRF con sessione invariata", async ({ page, context }) => {
    await login(page, "admin", primary);

    const sessionResponse = await page.request.get(
        "/api/auth/session"
    );

    expect(sessionResponse.status()).toBe(200);

    const current = await sessionResponse.json();

    const second = await context.newPage();

    const rotated = await second.request.get(
        "/api/auth/csrf",
        {
            headers: {
                "X-Expected-Session-ID":
                    String(current.session_id),
            },
        }
    );

    expect(rotated.status()).toBe(200);

    const statuses = [];

    const listener = response => {
        if (
            new URL(response.url()).pathname ===
                "/api/auth/active-bar" &&
            response.request().method() === "PUT"
        ) {
            statuses.push(response.status());
        }
    };

    page.on("response", listener);

    try {
        await switchBar(page, 5);

        await expect.poll(() => statuses)
            .toEqual([403, 200]);

        await history(page);
        await approved(page, "D");

        await expect(closure(page, "A"))
            .toHaveCount(0);

        await expectCurrentIdentity(page, current);

        await expect(
            page.getByRole("button", {
                name: "Accedi",
                exact: true,
            })
        ).toHaveCount(0);

    } finally {
        page.off("response", listener);
    }
});


test("AT-UI.01 - Identità amministratore globale", async ({ page }) => {
    await login(page, "admin");

    await expect(page.locator(".sidebar-user-email"))
        .toHaveText(accounts.admin);

    await expect(page.locator(".sidebar-user-role"))
        .toHaveText("Amministratore globale");
});

test("AT-UI.02 - Identità proprietario", async ({ page }) => {
    await login(page, "owner");

    await expect(page.locator(".sidebar-user-email"))
        .toHaveText(accounts.owner);

    await expect(page.locator(".sidebar-user-role"))
        .toHaveText("Proprietario");
});

test("AT-UI.03 - Identità dipendente", async ({ page }) => {
    await login(page, "staff");

    await expect(page.locator(".sidebar-user-email"))
        .toHaveText(accounts.staff);

    await expect(page.locator(".sidebar-user-role"))
        .toHaveText("Dipendente");

    await expect(page.locator(".bar-picker-option"))
        .toHaveCount(1);
});

test("AT-UI.04 - Apertura e chiusura del selettore", async ({ page }) => {
    await login(page, "admin");

    const trigger = page.locator("#active-bar");
    const options = page.locator("#active-bar-options");

    await expect(options).toBeHidden();

    await trigger.click();
    await expect(options).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");

    await trigger.click();
    await expect(options).toBeHidden();
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
});

test("AT-UI.05 - Accessibilità da tastiera", async ({ page }) => {
    await login(page, "admin", primary);

    const trigger = page.locator("#active-bar");
    const options = page.locator("#active-bar-options");

    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(options).toBeVisible();

    await page.keyboard.press("Tab");
    await expect(options.locator("button").first()).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(options).toBeHidden();
    await expect(trigger).toBeFocused();

    await page.keyboard.press("Enter");

    const secondaryOption = options.locator('[data-bar-id="5"]');
    await secondaryOption.focus();
    await page.keyboard.press("Enter");

    await expect(page.locator("#active-bar-name"))
        .toHaveText(secondary);

    await expect(options).toBeHidden();
});

test("AT-UI.06 - Chiusura cliccando all'esterno", async ({ page }) => {
    await login(page, "admin");

    await page.locator("#active-bar").click();

    await expect(page.locator("#active-bar-options"))
        .toBeVisible();

    await page.locator(".sidebar-logo").click();

    await expect(page.locator("#active-bar-options"))
        .toBeHidden();
});
