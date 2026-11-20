import assert from "node:assert/strict";
import test, { before, after } from "node:test";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let server;
let HistoryPage;
let ApiContext;

before(async () => {
  server = await createServer({
    root: new URL("..", import.meta.url).pathname,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });

  HistoryPage = (
    await server.ssrLoadModule("/src/pages/CashClosureHistoryPage.jsx")
  ).default;

  ApiContext = (
    await server.ssrLoadModule("/src/ApiContext.jsx")
  ).ApiContext;
});

after(async () => {
  await server?.close();
});

const approved = {
  id: 11,
  closure_id: 101,
  date: "2026-11-18",
  closure_number: "8",
  status: "approved",
  total_amount: "150.00",
  cash_amount: "100.00",
  card_amount: "50.00",
  can_annul: true,
  document: { original_filename: "chiusura.jpg" },
};

function button(renderer, label) {
  return renderer.root.findAllByType("button").find(
    (node) => node.children.includes(label)
  );
}

async function mount(fetch, props = {}) {
  let renderer;

  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(
        ApiContext.Provider,
        { value: { fetch } },
        React.createElement(HistoryPage, {
          month: "2026-11",
          activeBarId: 1,
          ...props,
        })
      )
    );
  });

  return renderer;
}

async function mountWithPendingRequest(fetch, props) {
  let renderer;

  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(
        ApiContext.Provider,
        { value: { fetch } },
        React.createElement(HistoryPage, props)
      )
    );
  });

  return renderer;
}

function mockFetch(items, postResponse = { ok: true }) {
  const calls = [];

  const fetch = async (url, options = {}) => {
    calls.push({ url, options });

    if (options.method === "POST") {
      return postResponse;
    }

    return {
      ok: true,
      json: async () => items,
    };
  };

  return { fetch, calls };
}

test("annulment button is shown only when backend grants permission", async () => {
  const api = mockFetch([{ ...approved, can_annul: false }]);
  const renderer = await mount(api.fetch);

  assert.equal(button(renderer, "Annulla chiusura"), undefined);

  await act(async () => {
    renderer.unmount();
  });

  const permitted = mockFetch([approved]);
  const allowed = await mount(permitted.fetch);

  assert.ok(button(allowed, "Annulla chiusura"));

  await act(async () => {
    allowed.unmount();
  });
});

test("annulment requires a non-empty reason", async () => {
  const api = mockFetch([approved]);
  const renderer = await mount(api.fetch);

  await act(async () => {
    button(renderer, "Annulla chiusura").props.onClick();
  });

  assert.equal(
    button(renderer, "Conferma annullamento").props.disabled,
    true
  );

  const textarea = renderer.root.findByType("textarea");

  await act(async () => {
    textarea.props.onChange({ target: { value: "   " } });
  });

  assert.equal(
    button(renderer, "Conferma annullamento").props.disabled,
    true
  );

  assert.equal(
    api.calls.filter((call) => call.options.method === "POST").length,
    0
  );

  await act(async () => {
    renderer.unmount();
  });
});

test("changing bar invalidates the previous annulment confirmation", async () => {
  const api = mockFetch([approved]);
  const renderer = await mount(api.fetch);

  await act(async () => {
    button(renderer, "Annulla chiusura").props.onClick();
  });

  await act(async () => {
    renderer.root.findByType("textarea").props.onChange({
      target: { value: "Errore contabile" },
    });
  });

  await act(async () => {
    renderer.update(
      React.createElement(
        ApiContext.Provider,
        { value: { fetch: api.fetch } },
        React.createElement(HistoryPage, {
          month: "2026-11",
          activeBarId: 2,
        })
      )
    );
  });

  assert.equal(button(renderer, "Conferma annullamento"), undefined);
  assert.equal(
    api.calls.filter((call) => call.options.method === "POST").length,
    0
  );

  await act(async () => {
    renderer.unmount();
  });
});

test("late responses cannot overwrite another bar or month", async () => {
  for (const change of [
    { name: "bar", props: { activeBarId: 2, month: "2026-11" } },
    { name: "month", props: { activeBarId: 1, month: "2026-10" } },
  ]) {
    let resolveOld;
    let reads = 0;

    const fetch = async () => {
      reads += 1;

      if (reads === 1) {
        return new Promise((resolve) => {
          resolveOld = resolve;
        });
      }

      return {
        ok: true,
        json: async () => [{
          ...approved,
          closure_number: "22",
          document: { original_filename: "nuovo-contesto.jpg" },
        }],
      };
    };

    const renderer = await mountWithPendingRequest(
      fetch,
      { activeBarId: 1, month: "2026-11" }
    );

    try {
      assert.equal(reads, 1);

      await act(async () => {
        renderer.update(
          React.createElement(
            ApiContext.Provider,
            { value: { fetch } },
            React.createElement(HistoryPage, change.props)
          )
        );
      });

      assert.equal(reads, 2);

      let output = JSON.stringify(renderer.toJSON());
      assert.ok(output.includes("Chiusura n. 22"), change.name);
      assert.ok(!output.includes("Chiusura n. 8"), change.name);

      await act(async () => {
        resolveOld({
          ok: true,
          json: async () => [approved],
        });
      });

      output = JSON.stringify(renderer.toJSON());
      assert.ok(output.includes("Chiusura n. 22"), change.name);
      assert.ok(!output.includes("Chiusura n. 8"), change.name);
    } finally {
      await act(async () => {
        renderer.unmount();
      });
    }
  }
});

test("successful annulment refreshes history and notifies dashboard", async () => {
  let historyReads = 0;
  let updates = 0;
  const calls = [];

  const fetch = async (url, options = {}) => {
    calls.push({ url, options });

    if (options.method === "POST") {
      return { ok: true };
    }

    historyReads += 1;
    return {
      ok: true,
      json: async () => historyReads === 1
        ? [approved]
        : [{ ...approved, status: "annulled", can_annul: false,
            annulment_reason: "Errore contabile" }],
    };
  };

  const renderer = await mount(fetch, {
    onHistoryChanged: async () => { updates += 1; },
  });

  await act(async () => {
    button(renderer, "Annulla chiusura").props.onClick();
  });

  await act(async () => {
    renderer.root.findByType("textarea").props.onChange({
      target: { value: "Errore contabile" },
    });
  });

  await act(async () => {
    await button(renderer, "Conferma annullamento").props.onClick();
  });

  assert.equal(updates, 1);
  assert.ok(historyReads >= 2);
  assert.equal(
    calls.filter((call) => call.options.method === "POST").length,
    1
  );
  assert.match(JSON.stringify(renderer.toJSON()), /Annullata/);

  await act(async () => {
    renderer.unmount();
  });
});

test("successful annulment remains successful if dashboard refresh fails", async () => {
  let historyReads = 0;
  let postCount = 0;

  const fetch = async (_url, options = {}) => {
    if (options.method === "POST") {
      postCount += 1;
      return { ok: true };
    }

    historyReads += 1;
    return {
      ok: true,
      json: async () => historyReads === 1
        ? [approved]
        : [{
            ...approved,
            status: "annulled",
            can_annul: false,
            annulment_reason: "Errore contabile",
          }],
    };
  };

  const originalConsoleError = console.error;
  console.error = () => {};

  let renderer;

  try {
    renderer = await mount(fetch, {
      onHistoryChanged: async () => {
        throw new Error("Dashboard temporaneamente non disponibile");
      },
    });

    await act(async () => {
      button(renderer, "Annulla chiusura").props.onClick();
    });

    await act(async () => {
      renderer.root.findByType("textarea").props.onChange({
        target: { value: "Errore contabile" },
      });
    });

    await act(async () => {
      await button(renderer, "Conferma annullamento").props.onClick();
    });

    const rendered = JSON.stringify(renderer.toJSON());

    assert.equal(postCount, 1);
    assert.ok(historyReads >= 2);
    assert.match(rendered, /Annullata/);
    assert.match(rendered, /Chiusura annullata correttamente/);
    assert.equal(button(renderer, "Conferma annullamento"), undefined);
  } finally {
    console.error = originalConsoleError;

    if (renderer) {
      await act(async () => {
        renderer.unmount();
      });
    }
  }
});

test("retry loads history after a temporary server error", async () => {
  let attempts = 0;

  const fetch = async () => {
    attempts += 1;

    if (attempts === 1) {
      return { ok: false, status: 503 };
    }

    return {
      ok: true,
      json: async () => [approved],
    };
  };

  const renderer = await mount(fetch);

  try {
    assert.match(
      JSON.stringify(renderer.toJSON()),
      /Impossibile caricare lo storico/
    );

    assert.ok(button(renderer, "Riprova caricamento"));

    await act(async () => {
      button(renderer, "Riprova caricamento").props.onClick();
    });

    assert.equal(attempts, 2);
    assert.equal(button(renderer, "Riprova caricamento"), undefined);
    assert.ok(JSON.stringify(renderer.toJSON()).includes("Chiusura n. 8"));
  } finally {
    await act(async () => {
      renderer.unmount();
    });
  }
});

test("failed annulment shows an error and keeps confirmation open", async () => {
  const api = mockFetch([approved], { ok: false, status: 409 });
  const renderer = await mount(api.fetch);

  await act(async () => {
    button(renderer, "Annulla chiusura").props.onClick();
  });

  await act(async () => {
    renderer.root.findByType("textarea").props.onChange({
      target: { value: "Errore contabile" },
    });
  });

  await act(async () => {
    await button(renderer, "Conferma annullamento").props.onClick();
  });

  assert.ok(button(renderer, "Conferma annullamento"));
  assert.match(JSON.stringify(renderer.toJSON()), /409/);

  await act(async () => {
    renderer.unmount();
  });
});
