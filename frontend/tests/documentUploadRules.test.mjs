import test from "node:test";
import assert from "node:assert/strict";
import {
  isOversizedNonImage,
  needsImageCompression,
} from "../src/documentUploadRules.js";

const MB = 1024 * 1024;

test("fotografia di 25 MB: compressione consentita", () => {
  const file = { size: 25 * MB, type: "image/jpeg" };
  assert.equal(isOversizedNonImage(file), false);
  assert.equal(needsImageCompression(file), true);
});

test("fotografia di 10 MB: caricamento diretto", () => {
  const file = { size: 10 * MB, type: "image/png" };
  assert.equal(isOversizedNonImage(file), false);
  assert.equal(needsImageCompression(file), false);
});

test("PDF di 25 MB: caricamento bloccato", () => {
  const file = { size: 25 * MB, type: "application/pdf" };
  assert.equal(isOversizedNonImage(file), true);
  assert.equal(needsImageCompression(file), false);
});

test("PDF esattamente di 20 MB: consentito", () => {
  const file = { size: 20 * MB, type: "application/pdf" };
  assert.equal(isOversizedNonImage(file), false);
});
