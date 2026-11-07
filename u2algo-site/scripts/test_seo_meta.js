#!/usr/bin/env node
// Static SEO / share-card checks for every page in sitemap.xml (Google + Meta Open Graph).
// No server, no network: reads the files that Railway serves.
'use strict';

const fs = require('fs');
const path = require('path');

const SITE = path.resolve(__dirname, '..');
const ORIGIN = 'https://u2algo.com';
let failures = 0;

function check(name, ok, detail = '') {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `  -> ${detail}`}`);
}

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
const meta = (html, attr, key) => {
  const m = html.match(new RegExp(`<meta ${attr}="${key.replace(/[.:]/g, '\\$&')}" content="([^"]*)"`));
  return m ? decode(m[1]) : null;
};

const sitemap = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
check('sitemap lists pages', locs.length >= 5, `${locs.length}`);
check('every sitemap entry has a lastmod', (sitemap.match(/<lastmod>\d{4}-\d{2}-\d{2}<\/lastmod>/g) || []).length === locs.length);

const indexed = fs.readdirSync(SITE).filter((f) => f.endsWith('.html')).filter((f) => {
  const html = fs.readFileSync(path.join(SITE, f), 'utf8');
  return !/<meta name="robots" content="[^"]*noindex/.test(html);
});
const fromSitemap = locs.map((u) => (u === `${ORIGIN}/` ? 'index.html' : u.slice(ORIGIN.length + 1)));
check('every indexable page is in the sitemap', indexed.every((f) => fromSitemap.includes(f)),
  indexed.filter((f) => !fromSitemap.includes(f)).join(', '));

for (const loc of locs) {
  const file = loc === `${ORIGIN}/` ? 'index.html' : loc.slice(ORIGIN.length + 1);
  const p = path.join(SITE, file);
  if (!fs.existsSync(p)) { check(`${file}: exists`, false); continue; }
  const html = fs.readFileSync(p, 'utf8');
  const head = html.slice(0, html.indexOf('</head>'));

  const title = decode((head.match(/<title>([^<]*)<\/title>/) || [, ''])[1]);
  check(`${file}: title 10-65 chars`, title.length >= 10 && title.length <= 65, `${title.length}: ${title}`);
  const desc = meta(head, 'name', 'description') || '';
  check(`${file}: description 50-170 chars`, desc.length >= 50 && desc.length <= 170, `${desc.length}`);
  const canon = (head.match(/<link rel="canonical" href="([^"]+)"/) || [, ''])[1];
  check(`${file}: canonical = sitemap loc`, canon === loc, canon);
  check(`${file}: exactly one <h1>`, (html.match(/<h1[\s>]/g) || []).length === 1);

  for (const k of ['og:title', 'og:description', 'og:type', 'og:site_name']) {
    check(`${file}: ${k}`, !!meta(head, 'property', k));
  }
  check(`${file}: og:url = canonical`, meta(head, 'property', 'og:url') === canon);
  const img = meta(head, 'property', 'og:image') || '';
  check(`${file}: og:image is an absolute PNG/JPG (Meta/X/LinkedIn do not render SVG)`, /^https:\/\/u2algo\.com\/.+\.(png|jpe?g)$/.test(img), img);
  check(`${file}: og:image file exists`, img.startsWith(ORIGIN) && fs.existsSync(path.join(SITE, img.slice(ORIGIN.length + 1))), img);
  check(`${file}: og:image is 1200x630`, meta(head, 'property', 'og:image:width') === '1200' && meta(head, 'property', 'og:image:height') === '630');
  check(`${file}: og:image:alt`, !!meta(head, 'property', 'og:image:alt'));
  check(`${file}: twitter:card summary_large_image`, meta(head, 'name', 'twitter:card') === 'summary_large_image');
  check(`${file}: twitter:image = og:image`, meta(head, 'name', 'twitter:image') === img);
  check(`${file}: no hreflang pointing at a #fragment`, !/hreflang="[^"]+" href="[^"]*#/.test(head));

  for (const m of head.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) {
    let ok = true;
    try { JSON.parse(m[1]); } catch { ok = false; }
    check(`${file}: JSON-LD parses`, ok);
  }
}

// The bot./v2./scalp.u2algo.com records were deleted on 2026-11-07; no public page may link or name them.
for (const f of fs.readdirSync(SITE).filter((x) => x.endsWith('.html'))) {
  const html = fs.readFileSync(path.join(SITE, f), 'utf8');
  const dead = html.match(/\b(?:bot|v2|scalp)\.u2algo\.com\b/g) || [];
  check(`${f}: no deleted bot subdomains`, dead.length === 0, [...new Set(dead)].join(', '));
}

const png = fs.readFileSync(path.join(SITE, 'brand', 'og-card.png'));
check('og-card.png is a 1200x630 PNG', png.readUInt32BE(16) === 1200 && png.readUInt32BE(20) === 630);

console.log(failures ? `\n${failures} FAILED` : '\nALL PASS');
process.exit(failures ? 1 : 0);
