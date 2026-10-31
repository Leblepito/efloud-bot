const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const out = path.join(root, 'launch-assets', '2026-05-31-first-share');
fs.mkdirSync(out, { recursive: true });

const palette = {
  bg: '#050510',
  panel: '#0c1224',
  cyan: '#00f0ff',
  blue: '#0080ff',
  purple: '#a855f7',
  ink: '#f8fafc',
  muted: '#94a3b8',
  green: '#00ff88',
  red: '#ff3366',
  warn: '#fbbf24'
};

function esc(s) {
  return String(s).replace(/[&<>]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[ch]));
}

function svg({ width, height, title, subtitle, bullets = [], footer, layout = 'landscape' }) {
  const isPortrait = height > width;
  const margin = isPortrait ? 72 : 90;
  const logoSize = isPortrait ? 70 : 62;
  const titleSize = isPortrait ? 74 : 68;
  const subSize = isPortrait ? 31 : 29;
  const bulletSize = isPortrait ? 34 : 29;
  const bulletGap = isPortrait ? 78 : 58;
  const footerSize = isPortrait ? 24 : 22;
  const maxTitleWidth = width - margin * 2;

  const bulletY = isPortrait ? 660 : 420;
  const bulletMarkup = bullets.map((b, i) => {
    const y = bulletY + i * bulletGap;
    return `<g transform="translate(${margin},${y})">
      <circle cx="12" cy="-10" r="8" fill="url(#cta)"/>
      <text x="38" y="0" font-size="${bulletSize}" fill="${palette.ink}" font-family="Inter, Arial, sans-serif" font-weight="600">${esc(b)}</text>
    </g>`;
  }).join('\n');

  const chartX = isPortrait ? 80 : width - 560;
  const chartY = isPortrait ? height - 640 : 190;
  const chartW = isPortrait ? width - 160 : 470;
  const chartH = isPortrait ? 360 : 360;

  const footerY = height - (isPortrait ? 100 : 70);

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}">
  <defs>
    <linearGradient id="cta" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="${palette.cyan}"/><stop offset="0.55" stop-color="${palette.blue}"/><stop offset="1" stop-color="${palette.purple}"/></linearGradient>
    <radialGradient id="glow" cx="35%" cy="20%" r="70%"><stop offset="0" stop-color="${palette.cyan}" stop-opacity="0.22"/><stop offset="0.45" stop-color="${palette.blue}" stop-opacity="0.10"/><stop offset="1" stop-color="${palette.bg}" stop-opacity="0"/></radialGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="18"/></filter>
    <pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse"><path d="M64 0H0V64" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="1"/></pattern>
  </defs>
  <rect width="100%" height="100%" fill="${palette.bg}"/>
  <rect width="100%" height="100%" fill="url(#glow)"/>
  <rect width="100%" height="100%" fill="url(#grid)" opacity="0.45"/>
  <circle cx="${width - 170}" cy="130" r="220" fill="${palette.purple}" opacity="0.12" filter="url(#soft)"/>

  <g transform="translate(${margin},${margin})">
    <rect width="${logoSize}" height="${logoSize}" rx="18" fill="url(#cta)"/>
    <path d="M18 ${logoSize - 20} C 30 ${logoSize - 38}, 40 ${logoSize - 32}, 52 20" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
    <text x="${logoSize + 18}" y="${logoSize / 2 + 9}" fill="${palette.ink}" font-size="34" font-family="Outfit, Inter, Arial, sans-serif" font-weight="800">u²Algo</text>
  </g>

  <g transform="translate(${margin},${isPortrait ? 245 : 190})">
    <text x="0" y="0" fill="${palette.cyan}" font-size="18" font-family="JetBrains Mono, monospace" letter-spacing="5">BUILD-IN-PUBLIC · RISK DISCIPLINE</text>
    <foreignObject x="0" y="38" width="${isPortrait ? maxTitleWidth : Math.min(720, maxTitleWidth)}" height="${isPortrait ? 280 : 180}">
      <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Outfit,Inter,Arial,sans-serif;color:${palette.ink};font-size:${titleSize}px;font-weight:800;line-height:0.95;letter-spacing:-0.04em;">${esc(title)}</div>
    </foreignObject>
    <foreignObject x="0" y="${isPortrait ? 330 : 235}" width="${isPortrait ? maxTitleWidth : 680}" height="130">
      <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Inter,Arial,sans-serif;color:${palette.muted};font-size:${subSize}px;line-height:1.35;">${esc(subtitle)}</div>
    </foreignObject>
  </g>

  ${bulletMarkup}

  <g transform="translate(${chartX},${chartY})" opacity="${isPortrait ? 0.95 : 1}">
    <rect width="${chartW}" height="${chartH}" rx="28" fill="rgba(255,255,255,.035)" stroke="rgba(255,255,255,.12)"/>
    <path d="M42 ${chartH-88} C 110 ${chartH-160}, 170 ${chartH-112}, 236 ${chartH-210} S 360 ${chartH-95}, ${chartW-45} 82" fill="none" stroke="url(#cta)" stroke-width="8" stroke-linecap="round"/>
    <rect x="${chartW*0.57}" y="48" width="${chartW*0.34}" height="70" rx="14" fill="rgba(255,51,102,.10)" stroke="rgba(255,51,102,.38)"/>
    <text x="${chartW*0.59}" y="92" fill="#ff8aa6" font-size="18" font-family="JetBrains Mono, monospace">SUPPLY</text>
    <rect x="50" y="${chartH-120}" width="${chartW*0.36}" height="66" rx="14" fill="rgba(0,255,136,.10)" stroke="rgba(0,255,136,.38)"/>
    <text x="72" y="${chartH-78}" fill="#79ffbd" font-size="18" font-family="JetBrains Mono, monospace">DEMAND</text>
    <circle cx="${chartW-80}" cy="104" r="15" fill="${palette.green}"/><text x="${chartW-52}" y="111" fill="${palette.green}" font-size="17" font-family="JetBrains Mono, monospace">MCP marker</text>
  </g>

  <text x="${margin}" y="${footerY}" fill="${palette.warn}" font-size="${footerSize}" font-family="JetBrains Mono, monospace">Yatırım tavsiyesi değildir · DYOR · Risk içerir</text>
</svg>`;
}

const assets = [
  {
    file: 'x-launch-1600x900.svg', width: 1600, height: 900,
    title: 'Bot analiz akışı artık daha görünür',
    subtitle: 'TradingView + MCP gözlem katmanı ile efloud-bot’un takip ettiği coin evreni açıklanabilir markerlarla izleniyor.',
    bullets: ['SMC tabanlı araştırma', 'Scalp · Mid · Long profilleri', 'Public-safe gözlem katmanı']
  },
  {
    file: 'instagram-carousel-cover-1080x1080.svg', width: 1080, height: 1080,
    title: 'Sinyal değil, açıklanabilir araştırma',
    subtitle: 'u2algo public site: risk-disiplinli algoritmik trading araştırması ve chart üstü bot hareketleri.',
    bullets: ['TradingView + MCP', 'Coin evreni gözlemi', 'DYOR + risk çerçevesi']
  },
  {
    file: 'shorts-cover-1080x1920.svg', width: 1080, height: 1920,
    title: 'Trading bot analizini görünür kılmak',
    subtitle: 'u2algo, efloud-bot tabanlı SMC araştırmasını chart üzerinde izlenebilir hale getiriyor.',
    bullets: ['Bot markerları', 'Risk disiplini', 'Build-in-public']
  }
];

for (const a of assets) {
  fs.writeFileSync(path.join(out, a.file), svg(a));
}

const captions = `# u2algo İlk Paylaşım Paketi — Final Draft

Durum: YAYIN İÇİN BLOKLU. Bu paket manuel onay ve domain/connector düzeltmesi sonrası kullanılmak üzere hazırlandı.

## X / Twitter tek post
u2algo public site hazırlandı: efloud-bot tabanlı SMC ve risk-disiplinli algoritmik trading araştırmasını artık TradingView + MCP gözlem katmanı ile daha açıklanabilir gösteriyoruz.

Botun takip ettiği coin evreni, chart üzerindeki hareket markerları ve scalp/mid/long profilleri tek deneyimde.

Yatırım tavsiyesi değildir. DYOR. Kripto ve kaldıraçlı işlemler yüksek risk içerir.

Link: https://u2algo.com/  (DNS/TLS 200 OK olmadan paylaşma)

## Instagram caption
u2algo public site launch hazırlığı tamamlandı.

Bu bir “kesin sinyal” servisi değil; efloud-bot tabanlı SMC yaklaşımını, risk disiplinini ve botun analiz akışını daha şeffaf hale getiren build-in-public araştırma katmanı.

Yeni TradingView + MCP gözlem bölümüyle botun takip ettiği coin evreni ve önemli hareket markerları chart üzerinde daha okunabilir hale geliyor.

Yatırım tavsiyesi değildir. DYOR. Kripto piyasaları ve kaldıraçlı işlemler yüksek risk içerir; kararlarınızdan siz sorumlusunuz.

#u2algo #algoritmiktrading #tradingview #riskmanagement #dyor

## Telegram duyurusu
Merhaba u2algo topluluğu,

u2algo public site ve ilk launch içerik paketi hazırlandı. Yeni yapı, efloud-bot tabanlı SMC ve risk-disiplinli algoritmik trading araştırmasını daha şeffaf şekilde göstermek için TradingView + MCP gözlem katmanını öne çıkarıyor.

Botun takip ettiği coin evreni, chart üstü hareket markerları ve scalp/mid/long trade profilleri tek yerde anlatılıyor.

Not: Custom domain DNS/TLS ve sosyal connector kontrolleri tamamlanmadan dış paylaşıma geçmiyoruz. Bu yaklaşım bir kâr vaadi veya yatırım yönlendirmesi değildir.

Yatırım tavsiyesi değildir. DYOR. Kripto ve kaldıraçlı işlemler yüksek risk içerir.

## YouTube Shorts / Reels açıklaması
u2algo, efloud-bot tabanlı SMC araştırmasını TradingView + MCP gözlem katmanıyla daha açıklanabilir hale getiriyor. Amaç getiri vaadi değil; bot analiz akışını, risk disiplinini ve chart üstü hareket markerlarını şeffaf biçimde göstermek.

Yatırım tavsiyesi değildir. DYOR. Kripto piyasaları yüksek risk içerir.
`;
fs.writeFileSync(path.join(out, 'captions.md'), captions);

console.log(JSON.stringify({ out, files: assets.map(a => a.file).concat(['captions.md']) }, null, 2));
