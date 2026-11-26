import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'

const configUrl = new URL('../vite.config.test.js', import.meta.url).href

function loadConfig(hostname, codespaceName) {
  const env = { ...process.env }

  delete env.PWA_TEST_HOSTNAME
  delete env.CODESPACE_NAME

  if (hostname !== undefined) {
    env.PWA_TEST_HOSTNAME = hostname
  }

  if (codespaceName !== undefined) {
    env.CODESPACE_NAME = codespaceName
  }
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


test('PWA Vite config allows the exact Codespaces host', () => {
  const result = loadConfig(undefined, 'test-codespace')
  assert.equal(result.status, 0, result.stderr)

  const server = JSON.parse(result.stdout)

  assert.deepEqual(server.allowedHosts, [
    'test-codespace-5174.app.github.dev',
  ])
  assert.equal(server.host, '127.0.0.1')
  assert.equal(server.port, 5174)
  assert.equal(server.strictPort, true)
})

test('PWA Vite config allows both explicitly configured hosts', () => {
  const result = loadConfig(
    'test-node.tail123.ts.net',
    'test-codespace',
  )

  assert.equal(result.status, 0, result.stderr)

  const server = JSON.parse(result.stdout)

  assert.deepEqual(server.allowedHosts, [
    'test-node.tail123.ts.net',
    'test-codespace-5174.app.github.dev',
  ])

  assert.equal(server.proxy['/api'].target, 'http://127.0.0.1:8001')
  assert.equal(server.proxy['/api'].changeOrigin, false)
})

test('PWA Vite config rejects invalid Codespaces names', () => {
  for (const name of [
    '*',
    '*.app.github.dev',
    '.app.github.dev',
    'example.com',
    'test:443',
    'test/name',
    '-test',
    'test-',
    'test--name',
  ]) {
    const result = loadConfig(undefined, name)
    assert.notEqual(result.status, 0, name)
    assert.match(result.stderr, /Invalid CODESPACE_NAME/)
  }
})
