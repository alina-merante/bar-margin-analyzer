import { defineConfig } from "@playwright/test";

const baseURL =
  "http://127.0.0.1:5174";

export default defineConfig({
  testDir: "../acceptance-tests/automated",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,

  expect: {
    timeout: 10000,
  },

  reporter: [
    ["list"],
    ["html", {
      outputFolder: "../acceptance-tests/reports/playwright-html",
      open: "never",
    }],
    ["json", {
      outputFile: "../acceptance-tests/reports/playwright-results.json",
    }],
  ],

  outputDir: "../acceptance-tests/reports/browser-artifacts",

  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    screenshot: "off",
    trace: "off",
    video: "off",
  },
});
