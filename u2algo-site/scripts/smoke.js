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

if (!ok) process.exit(1);
console.log(`smoke OK: ${html.length} bytes, compliance gate passed`);
