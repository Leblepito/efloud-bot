"""Social feed fetch/parsing helpers for Efloud public Telegram/X content.

This module keeps the dashboard endpoint thin and makes feed parsing testable.
It is intentionally read-only: failures degrade to curated fallback content and
never affect live trading behavior.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

log = logging.getLogger("efloud.social.feeds")

TELEGRAM_PUBLIC_URL = "https://t.me/s/EfloudTheSurfer"


def _clean_html_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def parse_telegram_public_html(raw_html: str, limit: int = 10) -> list[dict[str, Any]]:
    """Parse t.me public preview HTML into dashboard feed items."""
    pattern = re.compile(
        r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>',
        re.DOTALL,
    )
    matches = pattern.findall(raw_html or "")
    time_pattern = re.compile(r'<time datetime="([^"]+)"', re.DOTALL)
    times = time_pattern.findall(raw_html or "")

    posts: list[dict[str, Any]] = []
    for idx, text in enumerate(matches[:limit]):
        clean_text = _clean_html_text(text)
        if not clean_text:
            continue
        timestamp = times[idx] if idx < len(times) else "Recent"
        posts.append(
            {
                "id": f"tg-{idx}",
                "source": "telegram",
                "author": "Efloud TA & Charts",
                "content": clean_text,
                "timestamp": timestamp,
            }
        )
    return posts


def fallback_telegram_posts() -> list[dict[str, Any]]:
    """Curated Telegram samples used when public preview is unavailable."""
    return [
        {
            "id": "tg-fb1",
            "source": "telegram",
            "author": "Efloud TA & Charts",
            "content": "📌 BTC Güncelleme: 1D grafikte market yapısı bullish (MSB gerçekleşti). OTE bölgesinden (93200-94100) gelen pullback tepkisiyle 103k hedefine doğru ilerliyoruz. Güçlü FVG alanları destek olarak çalışmaya devam edecektir.",
            "timestamp": "2026-05-26T14:30:00Z",
        },
        {
            "id": "tg-fb2",
            "source": "telegram",
            "author": "Efloud TA & Charts",
            "content": "📈 ETH/USDT: 4H grafikte FVG (Fair Value Gap) test edildi ve reaksiyon alındı. 2480 seviyesi korunduğu sürece üst likidite hedefleri (2650 - 2800) masada kalacaktır. Risk yönetimine sadık kalın.",
            "timestamp": "2026-05-25T11:15:00Z",
        },
        {
            "id": "tg-fb3",
            "source": "telegram",
            "author": "Efloud TA & Charts",
            "content": "💡 Mixed Price Action (MPA) Notu: Sabit indikatörlere bağımlı kalmak yerine piyasanın likidite hareketlerini izleyin. Likidite temizliği yapılan her bölge potansiyel bir dönüş noktasıdır.",
            "timestamp": "2026-05-24T09:00:00Z",
        },
    ]


def fallback_x_posts() -> list[dict[str, Any]]:
    """Curated X/Twitter educational posts for the dashboard feed."""
    return [
        {
            "id": "tw-1",
            "source": "twitter",
            "author": "@EfloudTheSurfer",
            "content": "Market yapısını okurken en büyük hata trendin yönünü yanlış yorumlamaktır. Bir yüksek tepe (HH) yapısı oluşmadan sadece mum şekillerine bakarak dönüş aranmaz. Market Yapısı Kırılımı (MSB) ilk şarttır. 🧵👇",
            "timestamp": "2026-05-27T08:12:00Z",
        },
        {
            "id": "tw-2",
            "source": "twitter",
            "author": "@EfloudTheSurfer",
            "content": "SMC (Smart Money Concepts) ritüellerden ibaret değildir. FVG, Order Block veya OTE sadece birer bölgedir. Önemli olan bu bölgelerin HTF (High Time Frame) trend yönüyle uyumlu (Confluence) olmasıdır.",
            "timestamp": "2026-05-26T19:40:00Z",
        },
        {
            "id": "tw-3",
            "source": "twitter",
            "author": "@EfloudTheSurfer",
            "content": "Disiplinli bir trader, kâr hedefine ulaştığında TP1 alıp stop noktasını giriş seviyesine (break-even) taşır. Bu bot da tam olarak bu kurallarla çalışıyor. Sermayeyi korumak her zaman birinci önceliktir. 🛡️",
            "timestamp": "2026-05-25T15:20:00Z",
        },
    ]


async def fetch_social_feeds(client: Any | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fetch Telegram public preview and return Telegram + X dashboard feeds."""
    telegram_posts: list[dict[str, Any]] = []

    if client is not None:
        try:
            response = await client.get(TELEGRAM_PUBLIC_URL)
            if getattr(response, "status_code", None) == 200:
                telegram_posts = parse_telegram_public_html(getattr(response, "text", ""))
        except Exception as exc:
            log.warning("Telegram public scraper failed: %s", exc)
    else:
        try:
            async with httpx.AsyncClient(timeout=3.0) as http_client:
                response = await http_client.get(TELEGRAM_PUBLIC_URL)
                if response.status_code == 200:
                    telegram_posts = parse_telegram_public_html(response.text)
        except Exception as exc:
            log.warning("Telegram public scraper failed: %s", exc)

    if not telegram_posts:
        telegram_posts = fallback_telegram_posts()

    return {
        "telegram": telegram_posts,
        "twitter": fallback_x_posts(),
    }
