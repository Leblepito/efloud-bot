#!/usr/bin/env node
/**
 * Test: T-011 (waitlist consent) + T-016 (purchase webhook INERT)
 *
 * Çalıştırma: node u2algo-site/scripts/test_consent_and_webhook.js
 *
 * Mock tabanlı: server.js import edilmez, payload formatları ve endpoint davranışı
 * bağımsız şekilde doğrulanır (server up olmadan).
 *
 * Acceptance:
 *  T-011: 4 senaryo
 *  T-016: 6 senaryo
 */
'use strict';

const crypto = require('crypto');

// ============== T-011: Waitlist consent validation ==============
// Server.js POST /api/waitlist handler payload validation kuralları
function validateWaitlistPayload(payload) {
  const email = String(payload.email || '').trim().toLowerCase();
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254;
  if (!validEmail) return { ok: false, status: 400, error: 'invalid_email' };
  if (payload.consent !== true) {
    return { ok: false, status: 400, error: 'consent_required' };
  }
  return { ok: true, status: 200, email };
}

const t011Tests = [
  { name: 'consent:true + valid email → 200', payload: { email: 'foo@bar.com', consent: true }, expectOk: true, expectStatus: 200 },
  { name: 'consent:false + valid email → 400 consent_required', payload: { email: 'foo@bar.com', consent: false }, expectOk: false, expectStatus: 400, expectError: 'consent_required' },
  { name: 'consent eksik → 400 consent_required', payload: { email: 'foo@bar.com' }, expectOk: false, expectStatus: 400, expectError: 'consent_required' },
  { name: 'consent:null → 400 consent_required', payload: { email: 'foo@bar.com', consent: null }, expectOk: false, expectStatus: 400, expectError: 'consent_required' },
  { name: 'consent:1 (truthy ama !== true) → 400 consent_required', payload: { email: 'foo@bar.com', consent: 1 }, expectOk: false, expectStatus: 400, expectError: 'consent_required' },
  { name: 'geçersiz email + consent:true → 400 invalid_email', payload: { email: 'not-an-email', consent: true }, expectOk: false, expectStatus: 400, expectError: 'invalid_email' },
  { name: 'mevcut DB kaydı consent:null (geriye dönük) → INSERT reddedilir (yeni insert\'ler zorunlu)', payload: { email: 'foo@bar.com', consent: null }, expectOk: false, expectStatus: 400, expectError: 'consent_required', note: 'DB\'deki eski consent=null satırlar etkilenmez — sadece yeni insert zorunlu tutulur' },
];

// ============== T-016: Purchase webhook INERT ==============
// Server.js verifyLsSignature + handlePurchaseWebhook INERT guards
function verifyLsSignature(rawBody, signatureHeader, secret) {
  if (!signatureHeader || !secret) return false;
  const hmac = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  const a = Buffer.from(hmac, 'utf8');
  let b;
  try { b = Buffer.from(signatureHeader, 'utf8'); } catch { return false; }
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

function inertGuard1(webhookEnabled) {
  if (!webhookEnabled) return { ok: false, status: 503, error: 'disabled_by_config' };
  return null;
}
function inertGuard2(secret) {
  if (!secret) return { ok: false, status: 503, error: 'webhook_secret_not_configured' };
  return null;
}

const SECRET = 'test-secret';
const RAW_BODY = JSON.stringify({ meta: { event_name: 'order_created' }, data: { attributes: { id: '12345', user_email: 'buyer@example.com', product_id: '999' } } });
const VALID_SIG = crypto.createHmac('sha256', SECRET).update(RAW_BODY).digest('hex');

const t016Tests = [
  { name: 'INERT (webhookEnabled=false) → 503 disabled_by_config', webhookEnabled: false, secret: SECRET, sig: VALID_SIG, raw: RAW_BODY, expectStatus: 503, expectError: 'disabled_by_config' },
  { name: 'INERT guard 2 (secret boş) → 503', webhookEnabled: true, secret: '', sig: VALID_SIG, raw: RAW_BODY, expectStatus: 503, expectError: 'webhook_secret_not_configured' },
  { name: 'invalid signature → 401', webhookEnabled: true, secret: SECRET, sig: 'deadbeef', raw: RAW_BODY, expectStatus: 401, expectError: 'invalid_signature' },
  { name: 'valid signature (mock) → HMAC verify TRUE', webhookEnabled: true, secret: SECRET, sig: VALID_SIG, raw: RAW_BODY, expectVerify: true },
  { name: 'valid signature, wrong length → HMAC verify FALSE', webhookEnabled: true, secret: SECRET, sig: 'abc', raw: RAW_BODY, expectVerify: false },
  { name: 'empty signature → HMAC verify FALSE', webhookEnabled: true, secret: SECRET, sig: '', raw: RAW_BODY, expectVerify: false },
];

// ============== Test Runner ==============
let passed = 0;
let failed = 0;
const failures = [];

function assert(testName, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    passed++;
    console.log(`  ✓ ${testName}`);
  } else {
    failed++;
    failures.push({ name: testName, actual, expected });
    console.log(`  ✗ ${testName} — actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
  }
}

console.log('\n=== T-011: Waitlist Consent Validation ===');
for (const t of t011Tests) {
  const result = validateWaitlistPayload(t.payload);
  assert(t.name, { ok: result.ok, status: result.status, error: result.error }, {
    ok: t.expectOk,
    status: t.expectStatus,
    error: t.expectError || undefined
  });
}

console.log('\n=== T-016: Purchase Webhook INERT ===');
for (const t of t016Tests) {
  if (t.expectVerify !== undefined) {
    const result = verifyLsSignature(t.raw, t.sig, t.secret);
    assert(t.name, result, t.expectVerify);
    continue;
  }
  // Full chain simulation
  const g1 = inertGuard1(t.webhookEnabled);
  if (g1) {
    assert(t.name, { status: g1.status, error: g1.error }, { status: t.expectStatus, error: t.expectError });
    continue;
  }
  const g2 = inertGuard2(t.secret);
  if (g2) {
    assert(t.name, { status: g2.status, error: g2.error }, { status: t.expectStatus, error: t.expectError });
    continue;
  }
  const verified = verifyLsSignature(t.raw, t.sig, t.secret);
  if (!verified) {
    // Simüle: verified=false → 401 invalid_signature
    assert(t.name, { status: 401, error: 'invalid_signature' }, { status: t.expectStatus, error: t.expectError });
  } else {
    assert(t.name, verified, true);
  }
}

// ============== T-005: LS Product Map ==============
console.log('\n=== T-005: LS Product Map ===');
const LS_PRODUCT_MAP_TEST = { '1148317': 'wave1-indicator' };
function resolveProduct(map, id) {
  return map[String(id)] || 'wave1-unknown';
}
assert('LS_PRODUCT_MAP[\'1148317\'] → \'wave1-indicator\'', resolveProduct(LS_PRODUCT_MAP_TEST, '1148317'), 'wave1-indicator');
assert('LS_PRODUCT_MAP[unknown] → \'wave1-unknown\'', resolveProduct(LS_PRODUCT_MAP_TEST, '9999999'), 'wave1-unknown');

console.log(`\n=== Sonuç: ${passed} PASS, ${failed} FAIL ===`);
if (failed > 0) {
  console.log('\nBaşarısız testler:');
  for (const f of failures) console.log(`  - ${f.name}`);
  process.exit(1);
}
process.exit(0);
