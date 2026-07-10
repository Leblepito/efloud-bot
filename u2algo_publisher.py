"""
u2Algo Sosyal Medya Publisher
─────────────────────────────
• 3 botun (MID/LONG/SCALP) gerçek işlem verilerini VPS API'sinden çeker
• Her paylaşım için Telegram'a onay mesajı gönderir (✅ Onayla / ❌ Reddet)
• Onaylanınca Instagram'a grafik görseli + metin paylaşımı yapar
• Yeni işlem açılışı/kapanışında otomatik Telegram bildirimi gönderir
• Systemd servisi olarak çalışır (kalıcı)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from typing import Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ─── Yapılandırma ─────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = "8953010285:AAGNUH8-jcPSYaaHR63Vi_zqVunjDkwcazo"
TELEGRAM_CHAT_ID = "6756699467"

BOTS = {
    "MID": {
        "label": "MID Bot",
        "base_url": "https://178-104-122-91.nip.io",
        "password": "qK4DHZfbC-8DrXAPsFpAU6jdJTMQPyRK",
        "timeframes": "15m / 4h / 12h",
    },
    "LONG": {
        "label": "LONG Bot",
        "base_url": "https://v2.178-104-122-91.nip.io",
        "password": "qK4DHZfbC-8DrXAPsFpAU6jdJTMQPyRK",
        "timeframes": "1h / 8h / 1d",
    },
    "SCALP": {
        "label": "SCALP Bot",
        "base_url": "https://v3.178-104-122-91.nip.io",
        "password": "c4c24cadcd602739014457f3c66b7626",
        "timeframes": "5m / 1h / 4h",
    },
}

DISCLAIMER = "⚠️ Yatırım tavsiyesi değildir."

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("u2algo.publisher")

# ─── Bekleyen onaylar (in-memory) ─────────────────────────────────────────────

_pending: dict[str, dict] = {}
_seen_trades: set[str] = set()

# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def fmt_price(val) -> str:
    f = safe_float(val)
    if f == 0:
        return "—"
    if f > 1000:
        return f"{f:,.1f}"
    elif f > 10:
        return f"{f:.3f}"
    else:
        return f"{f:.5f}"

def fmt_pnl(val) -> str:
    f = safe_float(val)
    sign = "+" if f > 0 else ""
    return f"{sign}{f:.2f} USDT"

def date_str(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b")
    except Exception:
        return ts[:10]

# ─── Bot API İstemcisi ────────────────────────────────────────────────────────

def get_bot_session(bot_id: str) -> Optional[requests.Session]:
    cfg = BOTS[bot_id]
    session = requests.Session()
    try:
        r = session.post(
            f"{cfg['base_url']}/api/login",
            json={"password": cfg["password"]},
            timeout=15,
        )
        if r.status_code == 200:
            return session
        logger.warning("Login başarısız %s: %s", bot_id, r.status_code)
    except Exception as e:
        logger.error("Login hatası %s: %s", bot_id, e)
    return None

def fetch_positions(bot_id: str) -> list:
    session = get_bot_session(bot_id)
    if not session:
        return []
    try:
        r = session.get(f"{BOTS[bot_id]['base_url']}/api/positions", timeout=10)
        if r.status_code == 200:
            return r.json() or []
    except Exception as e:
        logger.error("Positions hatası %s: %s", bot_id, e)
    return []

def fetch_history(bot_id: str, limit: int = 5) -> list:
    session = get_bot_session(bot_id)
    if not session:
        return []
    try:
        r = session.get(f"{BOTS[bot_id]['base_url']}/api/history?limit={limit}", timeout=10)
        if r.status_code == 200:
            hist = r.json()
            if isinstance(hist, list):
                return hist
            return hist.get("items", hist.get("trades", []))
    except Exception as e:
        logger.error("History hatası %s: %s", bot_id, e)
    return []

def fetch_equity(bot_id: str) -> Optional[float]:
    session = get_bot_session(bot_id)
    if not session:
        return None
    try:
        r = session.get(f"{BOTS[bot_id]['base_url']}/api/equity", timeout=10)
        if r.status_code == 200:
            eq = r.json()
            if isinstance(eq, list) and eq:
                return safe_float(eq[-1].get("balance"))
            elif isinstance(eq, dict):
                return safe_float(eq.get("balance") or eq.get("total"))
    except Exception as e:
        logger.error("Equity hatası %s: %s", bot_id, e)
    return None

# ─── Metin Oluşturucu ─────────────────────────────────────────────────────────

def build_post_text(bot_id: str, trade: dict, is_open: bool = True) -> str:
    cfg       = BOTS[bot_id]
    sym       = trade.get("symbol", "?").replace("/", "")
    direction = trade.get("direction", "?")
    entry     = trade.get("entry") or trade.get("entry_price")
    exit_p    = trade.get("exit") or trade.get("exit_price")
    sl        = trade.get("sl") or trade.get("initial_sl")
    tp1       = trade.get("tp1")
    pnl       = trade.get("pnl_usdt") or trade.get("realized_pnl")
    reason    = trade.get("reason") or trade.get("exit_reason") or ""
    
    conf_raw = trade.get("confluence_details") or trade.get("confluence") or ""
    conf_reasons: list[str] = []
    if isinstance(conf_raw, str) and conf_raw.startswith("{"):
        try:
            cd = json.loads(conf_raw)
            conf_reasons = cd.get("reasons", [])
        except Exception:
            pass
    elif isinstance(conf_raw, dict):
        conf_reasons = conf_raw.get("reasons", [])

    is_closed = not is_open and exit_p is not None and safe_float(exit_p) > 0
    pnl_f = safe_float(pnl)

    lines = []
    
    # Başlık
    lines.append(f"{sym} | Güncelleme\n")
    lines.append("Merhabalar,")
    
    # Giriş cümlesi
    if is_closed:
        if pnl_f > 0:
            lines.append(f"{cfg['label']} tarafından takip edilen {sym} {direction} pozisyonumuz başarıyla hedefine ulaştı ve kâr realizasyonu gerçekleştirildi.")
        else:
            lines.append(f"{cfg['label']} tarafından takip edilen {sym} {direction} pozisyonumuzda piyasa koşullarındaki değişim sebebiyle risk yönetimi kurallarımız gereği çıkış yapıldı.")
    else:
        lines.append(f"{cfg['label']} algoritmamız, {sym} paritesinde güncel fiyat hareketlerini analiz ederek yeni bir {direction} pozisyonu kurguladı.")
    
    lines.append("")
    
    # Analiz ve Mantık
    lines.append(f"{sym} Analizi:")
    
    # Neden girildiğine dair analiz metni oluştur (Confluence veya SMC tabanlı)
    analysis_text = ""
    if conf_reasons:
        analysis_text = "Sistemin bu bölgede işleme dahil olma sebepleri arasında; " + ", ".join(conf_reasons).lower() + " yapıları öne çıkıyor. "
    
    if direction == "LONG":
        analysis_text += f"Fiyatın güncel destek bölgesinden reaksiyon alması durumunda ilk hedefimiz {fmt_price(tp1)} seviyeleri olacaktır. Bu bölgenin kazanımı ise daha üst likidite alanlarını hedef haline getirebilir. "
        analysis_text += f"Markette majör anlamda bir negatiflik görmemek adına {fmt_price(sl)} seviyesinin korunması gerektiğini düşünüyorum. Aksi takdirde stop-loss seviyemiz tetiklenerek sermaye korunumu sağlanacaktır."
    else:
        analysis_text += f"Fiyatın önemli bir direnç bölgesinde konsolide olması ve zayıflık emareleri göstermesi sebebiyle, {fmt_price(tp1)} destek seviyesine doğru bir geri çekilme öngörülüyor. "
        analysis_text += f"Şayet fiyat bu direnci sert bir mumla (breakout candle) kazanırsa işlerin tatsızlaşacağını düşünüyor ve {fmt_price(sl)} seviyesinde pozisyonu sonlandırarak riskimizi sınırlandırıyoruz."
        
    lines.append(analysis_text)
    lines.append("")
    
    # Kapanış tavsiyesi
    if not is_closed:
        lines.append("Belirlenen seviyeler kaybedilmeden veya kazanılmadan aceleci davranılmaması gerektiği, trendin oturmasının beklenmesi gerektiği kanaatindeyim.")
        lines.append("Kâr gördüğünüzde realize edip kendinizi güvenceye almanız (stop -> entry) veya stop-loss'unuzu trailing (takipli) şekilde taşıyarak ilerletmeniz en güvenli yol olacaktır.")
        lines.append("")
        
    lines.append("Herkese keyifli bir hafta, bol kazançlar ve trade'lerinde başarılar dilerim 🤝")
    lines.append("")
    
    # Etiketler
    tag = bot_id.capitalize()
    lines.append(f"#{sym} #{tag}Bot #u2Algo #SMC #AlgoTrading")

    return "\n".join(lines)

# ─── Grafik Görsel Oluşturucu ────────────────────────────────────────────────

def make_chart_image(bot_id: str, trade: dict, is_open: bool) -> str | None:
    """Pozisyon için 1080x1350 Instagram görseli oluştur ve S3'e yükle."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        sym = trade.get("symbol", "?").replace("/", "")
        direction = trade.get("direction", "?")
        entry = trade.get("entry") or trade.get("entry_price")
        sl = trade.get("sl") or trade.get("initial_sl")
        tp1 = trade.get("tp1")
        pnl = trade.get("pnl_usdt") or trade.get("realized_pnl") or trade.get("unrealized_pct")
        equity = fetch_equity(bot_id)

        IG_W, IG_H = 1080, 1350
        BG = (13, 17, 23)
        canvas = Image.new("RGB", (IG_W, IG_H), BG)
        draw = ImageDraw.Draw(canvas)

        try:
            font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_sm  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
            font_tiny= ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except Exception:
            font_big = font_med = font_sm = font_tiny = ImageFont.load_default()

        y = 45
        cfg_label = BOTS[bot_id]["label"]
        draw.text((54, y), cfg_label.upper(), fill=(0, 255, 136), font=font_med)
        y += 50

        sym_display = sym[:3] + "/USDT" if "/" not in sym else sym
        title = f"{sym_display}  ·  15m  ·  {direction}"
        draw.text((54, y), title, fill=(255, 255, 255), font=font_big)
        y += 55

        draw.line([(54, y), (IG_W - 54, y)], fill=(40, 50, 60), width=1)
        y += 22

        def lbl(x, yy, label, value, val_color=(255, 255, 255)):
            draw.text((x, yy), label, fill=(160, 160, 160), font=font_sm)
            draw.text((x + 110, yy), str(value), fill=val_color, font=font_sm)

        pnl_f = safe_float(pnl)
        pnl_color = (0, 255, 136) if pnl_f >= 0 else (255, 80, 80)
        pnl_str = f"{'+' if pnl_f >= 0 else ''}{pnl_f:.2f}%" if abs(pnl_f) < 1000 else fmt_pnl(pnl)

        lbl(54, y, "Entry", fmt_price(entry))
        lbl(560, y, "PnL", pnl_str, pnl_color)
        y += 40
        lbl(54, y, "Stop", fmt_price(sl), (255, 80, 80))
        if equity:
            lbl(560, y, "Equity", f"${equity:,.2f}", (255, 255, 255))
        y += 40
        lbl(54, y, "TP1", fmt_price(tp1), (0, 255, 136))
        y += 40

        draw.line([(54, y), (IG_W - 54, y)], fill=(40, 50, 60), width=1)
        y += 20

        # Grafik screenshot'ı var mı kontrol et (bot_id bazlı)
        chart_candidates = [
            f"/tmp/ig_charts3/{bot_id}_{sym}_{direction}.png",
            f"/tmp/ig_charts3/MID_{sym}_{direction}.png",
            f"/tmp/ig_auto_{bot_id}_{sym}_{direction}_chart.png",
        ]
        for chart_path in chart_candidates:
            if os.path.exists(chart_path):
                try:
                    chart = Image.open(chart_path)
                    chart_area_h = IG_H - y - 120
                    cw, ch = chart.size
                    scale = min((IG_W - 40) / cw, chart_area_h / ch)
                    nw, nh = int(cw * scale), int(ch * scale)
                    chart_r = chart.resize((nw, nh), Image.LANCZOS)
                    xo = (IG_W - nw) // 2
                    canvas.paste(chart_r, (xo, y))
                    y += nh + 20
                    break
                except Exception as e:
                    logger.warning("Grafik eklenemedi: %s", e)

        draw.line([(54, y), (IG_W - 54, y)], fill=(40, 50, 60), width=1)
        y += 15
        draw.text((54, y), "⚠️  Yatırım tavsiyesi değildir. DYOR.", fill=(100, 100, 100), font=font_tiny)
        draw.text((IG_W - 200, y), "@u2algo", fill=(0, 255, 136), font=font_tiny)

        out_path = f"/tmp/ig_auto_{bot_id}_{sym}_{direction}.png"
        canvas.save(out_path, "PNG")
        logger.info("Grafik görsel oluşturuldu: %s", out_path)
        return out_path

    except Exception as e:
        logger.error("make_chart_image hatası: %s", e)
    return None

# ─── Instagram Yayınlama (MCP üzerinden) ─────────────────────────────────────

def publish_to_instagram(caption: str, image_path: str | None = None, bot_id: str = "unknown", symbol: str = "", direction: str = "") -> tuple[bool, str]:
    """
    Instagram paylaşımını /tmp/ig_pending/ klasörüne yazar.
    Sandbox'taki zamanlanmış görev bu dosyayı okuyup MCP ile yayınlar.
    """
    try:
        import base64, uuid
        pending_dir = "/tmp/ig_pending"
        os.makedirs(pending_dir, exist_ok=True)

        # Görseli base64 olarak kodla (dosya yolu yerine)
        image_b64 = None
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

        payload = {
            "caption": caption,
            "image_b64": image_b64,
            "image_path": image_path,
            "bot_id": bot_id,
            "symbol": symbol,
            "direction": direction,
            "created_at": time.time(),
        }

        fname = f"{pending_dir}/{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        logger.info("Paylaşım kuyruğa alındı: %s", fname)
        return True, "⏳ Sandbox kuyruğuna alındı, kısa süre içinde Instagram'da yayınlanacak"

    except Exception as e:
        logger.error("publish_to_instagram exception: %s", e)
        return False, f"❌ Exception: {str(e)[:100]}"

# ─── Telegram Onay Gönderici ──────────────────────────────────────────────────

async def send_approval_request(
    app: Application,
    bot_id: str,
    trade: dict,
    is_open: bool,
    callback_id: str,
) -> None:
    text = build_post_text(bot_id, trade, is_open)

    # Grafik görsel oluştur
    image_path = make_chart_image(bot_id, trade, is_open)
    _pending[callback_id] = {
        "text": text,
        "bot_id": bot_id,
        "image_path": image_path,
        "symbol": trade.get("symbol", ""),
        "direction": trade.get("direction", ""),
    }

    trade_type = "Açık Pozisyon" if is_open else "Kapanmış İşlem"
    sym = trade.get("symbol", "?")
    direction = trade.get("direction", "?")

    header = (
        f"📋 <b>Yeni Paylaşım Onayı</b>\n"
        f"Bot: <b>{BOTS[bot_id]['label']}</b> | {trade_type}\n"
        f"<b>{sym} {direction}</b>\n\n"
        f"Instagram'da paylaşılacak metin:\n"
        f"{'─'*28}\n\n"
        f"{text}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Instagram'da Paylaş", callback_data=f"approve|{callback_id}"),
        InlineKeyboardButton("❌ Reddet", callback_data=f"reject|{callback_id}"),
    ]])

    await app.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=header,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    logger.info("Onay isteği gönderildi: %s %s %s", bot_id, sym, direction)

# ─── Telegram Komutları ───────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>u2Algo Publisher Bot</b>\n\n"
        "Komutlar:\n"
        "/status — 3 botun anlık durumu\n"
        "/positions — Açık pozisyonlar\n"
        "/history — Son kapanmış işlemler\n"
        "/publish — Tüm açık pozisyonları onaya gönder\n"
        "/equity — Cüzdan bakiyeleri",
        parse_mode="HTML",
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📊 <b>Bot Durumları</b>\n"]
    for bot_id, cfg in BOTS.items():
        session = get_bot_session(bot_id)
        if not session:
            lines.append(f"❌ <b>{cfg['label']}</b>: Bağlantı hatası")
            continue
        try:
            r = session.get(f"{cfg['base_url']}/api/status", timeout=10)
            if r.status_code == 200:
                s = r.json()
                running = "🟢 Çalışıyor" if s.get("running") else "🔴 Durdu"
                breaker = s.get("breaker_state", "?")
                open_pos = s.get("open_positions", 0)
                lines.append(
                    f"<b>{cfg['label']}</b>: {running}\n"
                    f"  Breaker: {breaker} | Açık: {open_pos} pozisyon\n"
                    f"  Döngü: #{s.get('cycle_count', 0)}"
                )
        except Exception as e:
            lines.append(f"⚠️ <b>{cfg['label']}</b>: {e}")
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📈 <b>Açık Pozisyonlar</b>\n"]
    for bot_id, cfg in BOTS.items():
        positions = fetch_positions(bot_id)
        if not positions:
            lines.append(f"<b>{cfg['label']}</b>: Açık pozisyon yok")
            continue
        lines.append(f"<b>{cfg['label']}</b> ({len(positions)} pozisyon):")
        for p in positions:
            dir_e = "📈" if p.get("direction") == "LONG" else "📉"
            unr = p.get("unrealized_pct", 0)
            unr_e = "🟢" if unr >= 0 else "🔴"
            lines.append(
                f"  {dir_e} {p.get('symbol')} {p.get('direction')}\n"
                f"  Giriş: {fmt_price(p.get('entry'))} | "
                f"SL: {fmt_price(p.get('sl'))} | TP1: {fmt_price(p.get('tp1'))}\n"
                f"  {unr_e} Unrealized: {unr:+.2f}% ({p.get('unrealized_usdt', 0):+.2f} USDT)"
            )
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📋 <b>Son Kapanmış İşlemler</b>\n"]
    for bot_id, cfg in BOTS.items():
        history = fetch_history(bot_id, limit=3)
        closed = [t for t in history if t.get("exit") or t.get("exit_price")]
        if not closed:
            lines.append(f"<b>{cfg['label']}</b>: Kapanmış işlem yok")
            continue
        lines.append(f"<b>{cfg['label']}</b>:")
        for t in closed[:3]:
            pnl_f = safe_float(t.get("pnl_usdt") or t.get("realized_pnl"))
            pnl_e = "✅" if pnl_f > 0 else "❌"
            lines.append(
                f"  {pnl_e} {t.get('symbol')} {t.get('direction')}\n"
                f"  PnL: {fmt_pnl(t.get('pnl_usdt') or t.get('realized_pnl'))}\n"
                f"  {date_str(t.get('opened_at', ''))} → {date_str(t.get('closed_at', ''))}"
            )
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

async def cmd_equity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["💰 <b>Cüzdan Bakiyeleri</b>\n"]
    total = 0.0
    for bot_id, cfg in BOTS.items():
        eq = fetch_equity(bot_id)
        if eq:
            lines.append(f"<b>{cfg['label']}</b>: ${eq:,.2f} USDT")
            total += eq
        else:
            lines.append(f"<b>{cfg['label']}</b>: Veri alınamadı")
    lines.append(f"\n<b>Toplam: ${total:,.2f} USDT</b>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Açık pozisyonlar çekiliyor...")
    count = 0
    for bot_id in BOTS:
        positions = fetch_positions(bot_id)
        for pos in positions:
            cb_id = f"pos_{bot_id}_{pos.get('symbol','').replace('/','_')}_{int(time.time())}"
            await send_approval_request(context.application, bot_id, pos, True, cb_id)
            count += 1
            await asyncio.sleep(0.5)
    await update.message.reply_text(
        f"✅ {count} pozisyon onay için gönderildi." if count else "ℹ️ Açık pozisyon bulunamadı."
    )

# ─── Callback Handler ─────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if "|" not in data:
        return

    action, callback_id = data.split("|", 1)
    pending = _pending.get(callback_id)

    if action == "reject":
        await query.edit_message_text(
            text=query.message.text + "\n\n❌ <b>Paylaşım reddedildi.</b>",
            parse_mode="HTML",
        )
        _pending.pop(callback_id, None)
        return

    if not pending:
        await query.edit_message_text(
            text=query.message.text + "\n\n⚠️ <i>Bu onay isteği artık geçerli değil.</i>",
            parse_mode="HTML",
        )
        return

    if action == "approve":
        caption = pending["text"]
        image_path = pending.get("image_path")
        bot_id_p = pending.get("bot_id", "unknown")
        symbol_p = pending.get("symbol", "")
        direction_p = pending.get("direction", "")
        ok, info = publish_to_instagram(caption, image_path, bot_id_p, symbol_p, direction_p)
        result_line = f"📸 Instagram: {info}"
        await query.edit_message_text(
            text=query.message.text + f"\n\n📢 <b>Sonuç:</b>\n{result_line}",
            parse_mode="HTML",
        )
        _pending.pop(callback_id, None)

# ─── Arka Plan İzleyici ───────────────────────────────────────────────────────

async def trade_watcher(app: Application):
    """Her 60 saniyede yeni kapanmış işlemleri kontrol et."""
    logger.info("Trade izleyici başlatıldı (60s aralık)")
    await asyncio.sleep(30)
    while True:
        try:
            for bot_id in BOTS:
                history = fetch_history(bot_id, limit=10)
                for trade in history:
                    trade_id = trade.get("id") or trade.get("trade_id")
                    if not trade_id or trade_id in _seen_trades:
                        continue
                    if trade.get("exit") or trade.get("exit_price") or trade.get("closed_at"):
                        _seen_trades.add(trade_id)
                        sym = trade.get("symbol", "?")
                        direction = trade.get("direction", "?")
                        pnl = safe_float(trade.get("pnl_usdt") or trade.get("realized_pnl"))
                        pnl_e = "✅" if pnl > 0 else "❌"
                        eq = fetch_equity(bot_id)
                        eq_str = f"\n💰 Güncel bakiye: ${eq:,.2f}" if eq else ""

                        notif = (
                            f"{pnl_e} <b>{BOTS[bot_id]['label']} — {sym} {direction} kapandı</b>\n\n"
                            f"Giriş: {fmt_price(trade.get('entry'))}\n"
                            f"Çıkış: {fmt_price(trade.get('exit') or trade.get('exit_price'))}\n"
                            f"PnL: <b>{fmt_pnl(pnl)}</b>"
                            f"{eq_str}"
                        )

                        cb_id = f"closed_{trade_id}"
                        image_path = make_chart_image(bot_id, trade, False)
                        _pending[cb_id] = {
                            "text": build_post_text(bot_id, trade, False),
                            "bot_id": bot_id,
                            "image_path": image_path,
                        }

                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("📸 Instagram'da Paylaş", callback_data=f"approve|{cb_id}"),
                            InlineKeyboardButton("❌ Geç", callback_data=f"reject|{cb_id}"),
                        ]])

                        await app.bot.send_message(
                            chat_id=TELEGRAM_CHAT_ID,
                            text=notif,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
                        logger.info("Kapanmış işlem bildirimi: %s %s %s", bot_id, sym, direction)
        except Exception as e:
            logger.error("Trade watcher hatası: %s", e)

        await asyncio.sleep(60)

# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def main():
    async def post_init(application: Application) -> None:
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                "🤖 <b>u2Algo Publisher Servisi Başlatıldı</b>\n\n"
                "✅ Instagram: @u2algo bağlı\n"
                "✅ Telegram: @u2Algo_bot aktif\n\n"
                "3 botun (MID/LONG/SCALP) işlemleri izleniyor.\n"
                "Yeni işlem kapandığında Telegram'a bildirim gelecek.\n\n"
                "Komutlar: /status /positions /history /equity /publish"
            ),
            parse_mode="HTML",
        )
        asyncio.create_task(trade_watcher(application))

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("equity",    cmd_equity))
    app.add_handler(CommandHandler("publish",   cmd_publish))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Polling başlatıldı...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
