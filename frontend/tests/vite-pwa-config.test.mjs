import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'

const configUrl = new URL('../vite.config.test.js', import.meta.url).href

function loadConfig(hostname) {
  const env = { ...process.env }
  if (hostname === undefined) delete env.PWA_TEST_HOSTNAME
  else env.PWA_TEST_HOSTNAME = hostname
  return spawnSync(process.execPath, [
    '--input-type=module', '-e',
    `import c from ${JSON.stringify(configUrl)}; console.log(JSON.stringify(c.server))`,
  ], { env, encoding: 'utf8' })
}

test('PWA Vite config allows only the configured Tailscale host', () => {
  const result = loadConfig('test-node.tail123.ts.net')
  assert.equal(result.status, 0, result.stderr)
  const server = JSON.parse(result.stdout)
  assert.deepEqual(server.allowedHosts, ['test-node.tail123.ts.net'])
  assert.equal(server.host, '127.0.0.1')
  assert.equal(server.port, 5174)
  assert.equal(server.proxy['/api'].target, 'http://127.0.0.1:8001')
  assert.equal(server.proxy['/api'].changeOrigin, false)
})

test('PWA Vite config rejects wildcard and non-Tailscale hosts', () => {
  for (const host of ['*.ts.net', 'example.com', '.ts.net', 'good.ts.net:443']) {
    assert.notEqual(loadConfig(host).status, 0, host)
  }
  assert.deepEqual(JSON.parse(loadConfig().stdout).allowedHosts, [])
})
