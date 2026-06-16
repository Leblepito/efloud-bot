const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, '..', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const lower = html.toLowerCase();

const required = [
  'u2algo',
  'yatırım tavsiyesi değildir',
  'dyor',
  'risk bildirimi',
  'geçmiş performans',
  'waitlist'
];

const forbidden = [
  'garantili getiri',
  'garanti getiri',
  'her gün kâr',
  'pasif gelir',
  'sinyal al kazan',
  'fonumuza para yatır',
  '%100 kazanç',
  'guaranteed returns'
];

let ok = true;
for (const phrase of required) {
  if (!lower.includes(phrase)) {
    console.error(`MISSING_REQUIRED: ${phrase}`);
    ok = false;
  }
}

for (const phrase of forbidden) {
  if (lower.includes(phrase)) {
    console.error(`FORBIDDEN_PHRASE: ${phrase}`);
    ok = false;
  }
}

// Allowed only in explicit denial/negation context.
if (lower.includes('kesin kazan') && !lower.includes('"kesin kazanır" sinyal servisi satmıyoruz')) {
  console.error('FORBIDDEN_CONTEXT: kesin kazan');
  ok = false;
}

// T-014: updates.json runtime'da sayfaya enjekte edilir — compliance gate'ten
// o kanal da geçmeli (CHANGELOG'a yazılan ifadeler müşteri yüzeyine ulaşır).
const updatesPath = path.join(__dirname, '..', 'updates.json');
if (fs.existsSync(updatesPath)) {
  let updatesText = '';
  try {
    const updates = JSON.parse(fs.readFileSync(updatesPath, 'utf8'));
    updatesText = (updates.entries || [])
      .flatMap(e => [e.label || ''].concat((e.items || []).map(i => `${i.type || ''} ${i.text || ''}`)))
      .join('\n')
      .toLowerCase();
  } catch (err) {
    console.error('UPDATES_JSON_PARSE_FAILED');
    ok = false;
  }
  for (const phrase of forbidden) {
    if (updatesText.includes(phrase)) {
      console.error(`FORBIDDEN_PHRASE_IN_UPDATES: ${phrase}`);
      ok = false;
    }
  }
  if (updatesText.includes('kesin kazan')) {
    console.error('FORBIDDEN_CONTEXT_IN_UPDATES: kesin kazan');
    ok = false;
  }
}

for (const asset of ['favicon.ico', 'brand/logo-horizontal.svg', 'brand/logo-mark.svg', 'robots.txt', 'sitemap.xml']) {
  const p = path.join(__dirname, '..', asset);
  if (!fs.existsSync(p)) {
    console.error(`MISSING_ASSET: ${asset}`);
    ok = false;
  }
}

const robotsPath = path.join(__dirname, '..', 'robots.txt');
const sitemapPath = path.join(__dirname, '..', 'sitemap.xml');
if (fs.existsSync(robotsPath)) {
  const robots = fs.readFileSync(robotsPath, 'utf8');
  if (!robots.includes('https://u2algo.com/sitemap.xml')) {
    console.error('ROBOTS_CANONICAL_SITEMAP_MISSING');
    ok = false;
  }
}
if (fs.existsSync(sitemapPath)) {
  const sitemap = fs.readFileSync(sitemapPath, 'utf8');
  if (!sitemap.includes('<loc>https://u2algo.com/</loc>')) {
    console.error('SITEMAP_CANONICAL_HOME_MISSING');
    ok = false;
  }
}

// T-010: Legal sayfalar compliance gate (terms.html + privacy.html)
// Yasal yüzeyde G-P3-B1 disclaimer'ı NET taşınmalı.
// T-010 kapsamı: terms.html ticari ürün disclaimer'ı taşır (yatırım tavsiyesi değil + DYOR +
//   getiri garantisi yok). privacy.html KVKK aydınlatması olduğu için bu 3 ticari cümleyi
//   taşıması GEREKMEZ; sadece mevcut/yasal-yeterliliğini doğrularız (KVKK/GDPR referansı).
const legalPages = {
  'terms.html': {
    required: ['yatırım tavsiyesi değildir', 'dyor', 'getiri garantisi yok', 'u2algo'],
    description: 'ticari ürün (T-010)'
  },
  'privacy.html': {
    required: ['kvkk', 'veri sorumlusu', 'u2algo'],
    description: 'KVKK/GDPR aydınlatma'
  }
};
for (const [legalFile, spec] of Object.entries(legalPages)) {
  const legalPath = path.join(__dirname, '..', legalFile);
  if (!fs.existsSync(legalPath)) {
    console.error(`MISSING_LEGAL_PAGE: ${legalFile}`);
    ok = false;
    continue;
  }
  const legalText = fs.readFileSync(legalPath, 'utf8').toLowerCase();
  // Yasal sayfa kendi spec'ine göre disclaimer kontrolü
  for (const phrase of spec.required) {
    if (!legalText.includes(phrase)) {
      console.error(`LEGAL_DISCLAIMER_MISSING in ${legalFile} (${spec.description}): ${phrase}`);
      ok = false;
    }
  }
  // Yasal sayfa forbidden phrase kontrolü (yatırım tavsiyesi dili YOK)
  for (const phrase of forbidden) {
    if (legalText.includes(phrase)) {
      console.error(`FORBIDDEN_PHRASE_IN_${legalFile}: ${phrase}`);
      ok = false;
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Track-1 premium launch: premium.html ürün satış sayfası compliance gate.
// Ürün TradingView SMC indikatörünü KARAR-DESTEK aracı olarak satar — kâr/getiri
// vaadi YASAK. Gate, zorunlu compliance token'larının varlığını ve forbidden
// dilin yokluğunu doğrular. (T-010 legal-gate pattern'ini takip eder.)
const premiumPath = path.join(__dirname, '..', 'premium.html');
if (!fs.existsSync(premiumPath)) {
  console.error('PREMIUM_MISSING: premium.html missing');
  process.exit(1);
}
const premiumRaw = fs.readFileSync(premiumPath, 'utf8');
const premiumLower = premiumRaw.toLowerCase();

const premiumRequired = [
  'yatırım tavsiyesi değildir',
  'getiri garantisi',
  'geçmiş performans',
  'founding',
  'checkout/buy',
  '/privacy.html',
  '/terms.html'
];
for (const phrase of premiumRequired) {
  if (!premiumLower.includes(phrase.toLowerCase())) {
    console.error(`PREMIUM_MISSING_REQUIRED: ${phrase}`);
    ok = false;
  }
}
for (const phrase of forbidden) {
  if (premiumLower.includes(phrase)) {
    console.error(`PREMIUM_FORBIDDEN_PHRASE: ${phrase}`);
    ok = false;
  }
}
if (ok) {
  console.log('[INFO] premium.html compliance gate passed');
}

// Track-1 premium launch: premium_proof.json şeffaflık snapshot doğrulaması.
// Zorunlu istatistik anahtarları bulunmalı; mutlak bakiye (balance / equity_usdt)
// ASLA bulunmamalı — sadece yüzde-normalize edilmiş veriler paylaşılır (G-P3-1).
const proofPath = path.join(__dirname, '..', 'premium_proof.json');
if (!fs.existsSync(proofPath)) {
  console.error('PREMIUM_PROOF_MISSING: premium_proof.json missing');
  ok = false;
} else {
  let proof;
  try {
    proof = JSON.parse(fs.readFileSync(proofPath, 'utf8'));
  } catch (err) {
    console.error('PREMIUM_PROOF_PARSE_FAILED');
    ok = false;
  }
  if (proof) {
    const proofRequired = ['as_of', 'period_days', 'closed_trades', 'win_rate_pct', 'return_pct', 'max_drawdown_pct'];
    for (const key of proofRequired) {
      if (!(key in proof)) {
        console.error(`PREMIUM_PROOF_MISSING_KEY: ${key}`);
        ok = false;
      }
    }
    if ('balance' in proof || 'equity_usdt' in proof) {
      console.error('PREMIUM_PROOF_FORBIDDEN_KEY: proof must NOT contain absolute balance (G-P3-1)');
      ok = false;
    }
    if (ok) {
      console.log('[INFO] premium_proof.json valid');
    }
  }
}

if (!ok) process.exit(1);
console.log(`smoke OK: ${html.length} bytes, compliance gate passed`);
