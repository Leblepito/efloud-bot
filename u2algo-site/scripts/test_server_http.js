#!/usr/bin/env node
/**
 * HTTP integration test for server.js (T-20261107-04, security audit T-20261106-06).
 *
 * Starts the real server on a free port (deps stubbed via -r _test_stub_deps.js,
 * no DB env → local JSONL fallback) and checks over real HTTP that:
 *  - public pages / brand assets / transparency JSON are still served
 *  - server source, package files, scripts/, supabase/, config files, dotfiles
 *    and the waitlist fallback (data/) are NOT served
 *  - POST /api/waitlist is rate-limited per client
 *  - the purchase webhook rejects oversized bodies
 *
 * Run: node u2algo-site/scripts/test_server_http.js
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

const SITE = path.join(__dirname, '..');
const FALLBACK = path.join(SITE, 'data', 'waitlist_leads.jsonl');
let failures = 0;

function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  -> ${detail}`}`);
  if (!ok) failures += 1;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function request(port, method, urlPath, { body, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, method, path: urlPath, headers }, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, type: res.headers['content-type'] || '', location: res.headers.location || '', body: Buffer.concat(chunks).toString('utf8') }));
    });
    req.on('error', reject);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

async function waitForHealth(port) {
  for (let i = 0; i < 50; i += 1) {
    try {
      const r = await request(port, 'GET', '/healthz');
      if (r.status === 200) return;
    } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('server did not start');
}

const postJson = (port, urlPath, obj, headers = {}) =>
  request(port, 'POST', urlPath, { body: JSON.stringify(obj), headers: { 'content-type': 'application/json', ...headers } });

async function main() {
  const port = await freePort();
  const env = { ...process.env, PORT: String(port), LS_WEBHOOK_ENABLED: 'true', LEMONSQUEEZY_WEBHOOK_SECRET: 'test-secret' };
  for (const k of ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DATABASE_URL', 'DATABASE_URL', 'LOCAL_WAITLIST_PATH']) delete env[k];
  const hadFallback = fs.existsSync(FALLBACK);
  const child = spawn(process.execPath, ['-r', path.join(__dirname, '_test_stub_deps.js'), 'server.js'], { cwd: SITE, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  child.stderr.on('data', d => { stderr += d; });

  try {
    await waitForHealth(port);

    // 1) public surface still served
    for (const [p, type] of [
      ['/', 'text/html'], ['/privacy.html', 'text/html'], ['/favicon.ico', 'image/x-icon'],
      ['/robots.txt', 'text/plain'], ['/sitemap.xml', ''], ['/brand/logo-horizontal.svg', 'image/svg+xml'],
      ['/brand-kit/css/tokens-generated.css', 'text/css'], ['/updates.json', 'application/json'],
      ['/premium_proof.json', 'application/json'], ['/assets/premium/wave1_btc_short_15m.png', 'image/png'],
      ['/brand/og-card.png', 'image/png'],
    ]) {
      const r = await request(port, 'GET', p);
      check(`serves ${p}`, r.status === 200 && r.type.startsWith(type), `${r.status} ${r.type}`);
      if (p !== '/') {
        const onDisk = fs.readFileSync(path.join(SITE, decodeURIComponent(p))).toString('utf8');
        check(`serves the real bytes of ${p}`, r.body === onDisk, `len ${r.body.length} vs ${onDisk.length}`);
      }
    }

    // 2) non-public files are not served (fall back to index.html like any unknown path)
    const indexBody = (await request(port, 'GET', '/index.html')).body;
    for (const p of [
      '/server.js', '/package.json', '/package-lock.json', '/railway.json', '/nixpacks.toml',
      '/scripts/smoke.js', '/scripts/test_consent_and_webhook.js', '/web/package.json',
      '/brand-kit/BRAND.md', '/brand-kit/css/design-tokens.ts', '/brand-kit/css/postcss.config.mjs',
      '/.gitignore', '/%2e%2e/server.js', '/brand/../server.js', '/brand%5c..%5cserver.js',
      '/%252e%252e/server.js', '/server.js?x=1', '/brand/%2e%2e/package.json',
    ]) {
      const r = await request(port, 'GET', p);
      check(`does not serve ${p}`, r.type.startsWith('text/html') && r.body === indexBody, `${r.status} ${r.type} len=${r.body.length}`);
    }
    const supabaseFiles = fs.existsSync(path.join(SITE, 'supabase')) ? fs.readdirSync(path.join(SITE, 'supabase')) : [];
    if (supabaseFiles.length) {
      const r = await request(port, 'GET', `/supabase/${encodeURIComponent(supabaseFiles[0])}`);
      check('does not serve /supabase/*', r.body === indexBody, `${r.status} ${r.type}`);
    }

    // 3) waitlist fallback file is never downloadable
    const email = `audit-${Date.now()}@example.com`;
    const w = await postJson(port, '/api/waitlist', { email, consent: true, source: 'test' }, { 'x-forwarded-for': '198.51.100.7' });
    check('waitlist accepts a valid lead', w.status === 200, `${w.status} ${w.body}`);
    const leak = await request(port, 'GET', '/data/waitlist_leads.jsonl');
    check('waitlist fallback is not served', !leak.body.includes(email) && leak.body === indexBody, `${leak.status} ${leak.type}`);

    // 4) per-client rate limit on POST /api/waitlist
    let limited = null;
    for (let i = 0; i < 15; i += 1) {
      const r = await postJson(port, '/api/waitlist', { email: `rl-${i}-${Date.now()}@example.com`, consent: true }, { 'x-forwarded-for': '203.0.113.9' });
      if (r.status === 429) { limited = i; break; }
    }
    check('waitlist rate-limits a single client', limited !== null && limited >= 3, `first 429 at request #${limited}`);
    const other = await postJson(port, '/api/waitlist', { email: `other-${Date.now()}@example.com`, consent: true }, { 'x-forwarded-for': '192.0.2.44' });
    check('rate limit is per client', other.status === 200, `${other.status}`);
    const spoof = await postJson(port, '/api/waitlist', { email: `spoof-${Date.now()}@example.com`, consent: true }, { 'x-forwarded-for': '1.2.3.4, 203.0.113.9' });
    check('spoofed left-most X-Forwarded-For does not reset the limit', spoof.status === 429, `${spoof.status}`);

    // 5) oversized webhook body is rejected before reading it all
    const big = await request(port, 'POST', '/api/purchase-webhook', { body: 'x'.repeat(200 * 1024), headers: { 'content-type': 'application/json', 'x-signature': 'nope' } });
    check('purchase webhook rejects oversized body', big.status === 413, `${big.status} ${big.body.slice(0, 80)}`);
    const small = await request(port, 'POST', '/api/purchase-webhook', { body: '{}', headers: { 'content-type': 'application/json', 'x-signature': 'nope' } });
    check('purchase webhook still checks signature', small.status === 401, `${small.status}`);
  } finally {
    // 6) one canonical host: www → apex (301), path + query kept; health checks untouched
    const www = await request(port, 'GET', '/premium.html?ref=x', { headers: { host: 'www.u2algo.com' } });
    check('www redirects to the apex host', www.status === 301 && www.location === 'https://u2algo.com/premium.html?ref=x', `${www.status} ${www.location}`);
    const wwwRoot = await request(port, 'GET', '/', { headers: { host: 'WWW.u2algo.com:443' } });
    check('www root redirects to the apex root', wwwRoot.status === 301 && wwwRoot.location === 'https://u2algo.com/', `${wwwRoot.status} ${wwwRoot.location}`);
    const apex = await request(port, 'GET', '/', { headers: { host: 'u2algo.com' } });
    check('apex host is served directly', apex.status === 200, `${apex.status}`);
    const wwwHealth = await request(port, 'GET', '/healthz', { headers: { host: 'www.u2algo.com' } });
    check('healthz is never redirected', wwwHealth.status === 200, `${wwwHealth.status}`);
    const wwwPost = await postJson(port, '/api/waitlist', { email: 'www-host@example.com', consent: true }, { host: 'www.u2algo.com' });
    check('API calls on www are not redirected', wwwPost.status !== 301, `${wwwPost.status}`);

    child.kill();
    if (!hadFallback && fs.existsSync(FALLBACK)) fs.rmSync(FALLBACK);
    if (stderr.trim()) console.log(`[server stderr]\n${stderr.trim().slice(0, 1500)}`);
  }

  console.log(failures ? `\n${failures} FAILED` : '\nALL PASS');
  process.exit(failures ? 1 : 0);
}

main().catch(err => { console.error(err); process.exit(1); });
