'use strict';
// u2algo public-site walkthrough video (decision 5, spec 2026-11-07).
// ONLY the public illustrative pages: live.html (a labelled simulation) and
// premium.html. No login, no real account data. Control buttons are hovered,
// never clicked.
//
//   npm i playwright-core          (in any scratch dir; set PLAYWRIGHT_CORE to its path)
//   node scripts/demo/record_site_demo.cjs --rehearse
//   node scripts/demo/record_site_demo.cjs   # -> $DEMO_OUT_DIR/u2algo-site-demo.webm
//
// CHROME_PATH overrides the browser; default = Playwright's cached chromium-1223.
const path = require('path');
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const BASE = process.env.DEMO_BASE_URL || 'https://u2algo.com';
const OUT_DIR = process.env.DEMO_OUT_DIR || path.join(process.cwd(), 'demo-out');
const REHEARSAL = process.argv.includes('--rehearse');
const EXE = process.env.CHROME_PATH ||
  path.join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium-1223', 'chrome-win64', 'chrome.exe');

const CURSOR_SVG = '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M5 3L19 12L12 13L9 20L5 3Z" ' +
  'fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/></svg>';

async function injectOverlays(page) {
  await page.evaluate((svg) => {
    if (!document.getElementById('demo-cursor')) {
      const c = document.createElement('div');
      c.id = 'demo-cursor';
      c.innerHTML = svg;
      c.style.cssText = 'position:fixed;z-index:999999;pointer-events:none;width:24px;height:24px;' +
        'transition:left .1s,top .1s;filter:drop-shadow(1px 1px 2px rgba(0,0,0,.3));left:0;top:0';
      document.body.appendChild(c);
      document.addEventListener('mousemove', (e) => {
        c.style.left = e.clientX + 'px';
        c.style.top = e.clientY + 'px';
      });
    }
    if (!document.getElementById('demo-subtitle')) {
      const b = document.createElement('div');
      b.id = 'demo-subtitle';
      b.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:999998;text-align:center;' +
        'padding:12px 24px;background:rgba(0,0,0,.75);color:#fff;font:500 18px "Segoe UI",sans-serif;' +
        'opacity:0;transition:opacity .3s;pointer-events:none';
      document.body.appendChild(b);
    }
  }, CURSOR_SVG);
}

async function subtitle(page, text) {
  await page.evaluate((t) => {
    const b = document.getElementById('demo-subtitle');
    if (!b) return;
    b.textContent = t || '';
    b.style.opacity = t ? '1' : '0';
  }, text);
  if (text) await page.waitForTimeout(900);
}

const first = (page, sel) => page.locator(sel).first();

async function ensureVisible(page, sel, label) {
  const ok = await first(page, sel).isVisible().catch(() => false);
  console.log(`${ok ? 'REHEARSAL OK' : 'REHEARSAL FAIL'}: "${label}" (${sel})`);
  return ok;
}

async function moveTo(page, sel, label, pause = 700) {
  const el = first(page, sel);
  if (!(await el.isVisible().catch(() => false))) {
    console.error(`WARNING: "${label}" not visible`);
    return false;
  }
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 });
  await page.waitForTimeout(pause);
  return true;
}

async function moveAndClick(page, sel, label) {
  if (await moveTo(page, sel, label, 400)) {
    await first(page, sel).click();
    await page.waitForTimeout(1500);
  }
}

async function scrollToText(page, text, label) {
  const el = page.getByText(text, { exact: false }).first();
  const y = await el.evaluate((e) => e.getBoundingClientRect().top + window.scrollY - 80)
    .catch(() => { console.error(`WARNING: "${label}" not found`); return null; });
  if (y === null) return;
  await page.evaluate((top) => window.scrollTo({ top, behavior: 'smooth' }), y);
  await page.waitForTimeout(2200);
}

const LIVE = [
  ['.sym-btn:has-text("ETH/USDT")', 'ETH symbol'],
  ['button:has-text("1h")', '1h timeframe'],
  ['.ctrl-btn:has-text("Başlat")', 'Start (hover only)'],
  ['.ctrl-btn:has-text("Kill Switch")', 'Kill switch (hover only)'],
];
const LIVE_TEXT = ['7 Katmanlı', '3 Bot, 3 Zaman Ufku'];
const PREMIUM_TEXT = ['Indicator or full automation', 'What it is'];

async function rehearse(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto(`${BASE}/live.html`, { waitUntil: 'networkidle' });
  let ok = true;
  for (const [sel, label] of LIVE) ok = (await ensureVisible(page, sel, label)) && ok;
  for (const t of LIVE_TEXT) {
    const n = await page.getByText(t).count();
    console.log(`${n ? 'REHEARSAL OK' : 'REHEARSAL FAIL'}: text "${t}"`);
    ok = n > 0 && ok;
  }
  await page.goto(`${BASE}/premium.html`, { waitUntil: 'networkidle' });
  for (const t of PREMIUM_TEXT) {
    const n = await page.getByText(t).count();
    console.log(`${n ? 'REHEARSAL OK' : 'REHEARSAL FAIL'}: text "${t}"`);
    ok = n > 0 && ok;
  }
  return ok;
}

async function record(browser) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: OUT_DIR, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  try {
    await page.goto(`${BASE}/live.html`, { waitUntil: 'networkidle' });
    await injectOverlays(page);
    await page.waitForTimeout(1500);
    await subtitle(page, 'u2algo bot izleme paneli — illüstratif demo (simülasyon verisi)');
    await page.waitForTimeout(2500);
    await subtitle(page, 'Sembol ve zaman dilimi seç');
    await moveAndClick(page, LIVE[0][0], LIVE[0][1]);
    await moveAndClick(page, LIVE[1][0], LIVE[1][1]);
    await page.waitForTimeout(1500);
    await subtitle(page, 'Kontroller ve acil durdurma (Kill Switch)');
    await moveTo(page, LIVE[2][0], LIVE[2][1], 1200);
    await moveTo(page, LIVE[3][0], LIVE[3][1], 1500);
    await subtitle(page, '7 katmanlı güvenlik motoru');
    await scrollToText(page, LIVE_TEXT[0], 'safety section');
    await page.waitForTimeout(1500);
    await subtitle(page, 'Scalp · Mid · Long — üç zaman ufku');
    await scrollToText(page, LIVE_TEXT[1], 'strategy section');
    await page.waitForTimeout(2000);

    await page.goto(`${BASE}/premium.html`, { waitUntil: 'networkidle' });
    await injectOverlays(page);
    await subtitle(page, 'TradingView için SMC + Fibonacci indikatörü');
    await page.waitForTimeout(2500);
    await scrollToText(page, PREMIUM_TEXT[0], 'plans');
    await page.waitForTimeout(1500);
    await subtitle(page, 'Ne olduğu — ve ne olmadığı');
    await scrollToText(page, PREMIUM_TEXT[1], 'honesty section');
    await page.waitForTimeout(2500);
    await subtitle(page, 'u2algo.com · Karar desteği — yatırım tavsiyesi değildir');
    await page.waitForTimeout(3000);
  } catch (err) {
    console.error('DEMO ERROR:', err.message);
    process.exitCode = 1;
  } finally {
    const video = page.video();
    await context.close();
    if (video) {
      const dest = path.join(OUT_DIR, 'u2algo-site-demo.webm');
      fs.copyFileSync(await video.path(), dest);
      console.log('Video saved:', dest);
    }
  }
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  try {
    if (REHEARSAL) {
      const ok = await rehearse(browser);
      console.log(ok ? 'REHEARSAL PASSED' : 'REHEARSAL FAILED');
      process.exitCode = ok ? 0 : 1;
    } else {
      await record(browser);
    }
  } finally {
    await browser.close();
  }
})();
