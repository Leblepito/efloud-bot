#!/usr/bin/env node
// Generates brand/og-card.png — the 1200x630 social share card used by
// og:image / twitter:image. Meta (Facebook/Instagram/WhatsApp), X and
// LinkedIn do not render SVG share images, so the card must be a raster PNG.
//
// Usage (from the repo root, where `sharp` is installed for the frontend):
//   node u2algo-site/scripts/generate-og-card.js
'use strict';

const fs = require('fs');
const path = require('path');

const SITE = path.resolve(__dirname, '..');
let sharp;
try {
  sharp = require('sharp');
} catch {
  sharp = require(path.resolve(SITE, '..', 'node_modules', 'sharp'));
}

const W = 1200;
const H = 630;
const logo = fs.readFileSync(path.join(SITE, 'brand', 'logo-horizontal.svg'), 'utf8')
  .replace(/<\?xml[^>]*>/, '')
  .replace(/<svg[^>]*>/, '')
  .replace(/<\/svg>\s*$/, '');

const FONT = "'Segoe UI','Inter','DejaVu Sans',Arial,sans-serif";

const card = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="glow" cx="0.82" cy="0.18" r="0.75">
      <stop offset="0" stop-color="#6366F1" stop-opacity="0.35"/>
      <stop offset="1" stop-color="#050510" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="#050510"/>
  <rect width="${W}" height="${H}" fill="url(#glow)"/>
  <g transform="translate(90 120) scale(3.2)">${logo}</g>
  <text x="90" y="350" font-family="${FONT}" font-size="54" font-weight="700" fill="#F8FAFC">SMC + Fibonacci indicator</text>
  <text x="90" y="418" font-family="${FONT}" font-size="54" font-weight="700" fill="#F8FAFC">for TradingView</text>
  <text x="90" y="488" font-family="${FONT}" font-size="30" fill="#94A3B8">Market structure, order blocks and confluence — on one chart.</text>
  <rect x="90" y="530" width="${W - 180}" height="2" fill="#1E293B"/>
  <text x="90" y="585" font-family="${FONT}" font-size="26" font-weight="600" fill="#00F0FF">u2algo.com</text>
  <text x="${W - 90}" y="585" text-anchor="end" font-family="${FONT}" font-size="22" fill="#64748B">Decision support · Not investment advice</text>
</svg>`;

const out = path.join(SITE, 'brand', 'og-card.png');
sharp(Buffer.from(card))
  .png({ compressionLevel: 9 })
  .toFile(out)
  .then((info) => console.log(`wrote ${path.relative(process.cwd(), out)} ${info.width}x${info.height} ${info.size}B`))
  .catch((err) => { console.error(err); process.exit(1); });
