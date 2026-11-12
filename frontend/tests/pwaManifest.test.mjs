import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("manifest references installable, correctly sized PNG icons", async () => {
  const manifest = JSON.parse(await readFile(new URL("../public/manifest.webmanifest", import.meta.url), "utf8"));
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /rel="manifest"\s+href="\/manifest\.webmanifest"/);
  assert.equal(manifest.name, "BarManager");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "/");
  for (const size of [192, 512]) {
    const icon = manifest.icons.find((entry) => entry.sizes === `${size}x${size}`);
    assert.ok(icon);
    assert.equal(icon.type, "image/png");
    const data = await readFile(new URL(`../public${icon.src}`, import.meta.url));
    assert.deepEqual([...data.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
    assert.equal(data.readUInt32BE(16), size);
    assert.equal(data.readUInt32BE(20), size);
  }
});
