"""Social feed parsing and API wiring tests."""

import pytest


TELEGRAM_HTML = """
<div class="tgme_widget_message_text js-message_text" dir="auto">
  BTC Güncelleme: 1D grafikte market yapısı bullish (MSB gerçekleşti).<br/>OTE bölgesi çalıştı.
</div>
<time datetime="2026-05-27T08:12:00+00:00"></time>
<div class="tgme_widget_message_text js-message_text" dir="auto">
  ETH/USDT: 4H grafikte FVG test edildi ve reaksiyon alındı.
</div>
<time datetime="2026-05-27T09:15:00+00:00"></time>
"""


def test_parse_telegram_public_html_extracts_text_and_timestamps():
    from backend.social.feeds import parse_telegram_public_html

    posts = parse_telegram_public_html(TELEGRAM_HTML)

    assert len(posts) == 2
    assert posts[0]["source"] == "telegram"
    assert posts[0]["author"] == "Efloud TA & Charts"
    assert posts[0]["timestamp"] == "2026-05-27T08:12:00+00:00"
    assert "BTC Güncelleme" in posts[0]["content"]
    assert "OTE bölgesi" in posts[0]["content"]
    assert "<br" not in posts[0]["content"]
    assert "ETH/USDT" in posts[1]["content"]


def test_parse_telegram_public_html_empty_input_returns_empty_list():
    from backend.social.feeds import parse_telegram_public_html

    assert parse_telegram_public_html("<html></html>") == []


def test_fallback_posts_keep_expected_response_shape():
    from backend.social.feeds import fallback_telegram_posts, fallback_x_posts

    telegram = fallback_telegram_posts()
    twitter = fallback_x_posts()

    assert telegram
    assert twitter
    for item in telegram + twitter:
        assert set(item) == {"id", "source", "author", "content", "timestamp"}


@pytest.mark.asyncio
async def test_fetch_social_feeds_uses_fallback_when_telegram_fetch_fails():
    from backend.social.feeds import fetch_social_feeds

    class FailingClient:
        async def get(self, *_args, **_kwargs):
            raise RuntimeError("blocked")

    feeds = await fetch_social_feeds(client=FailingClient())

    assert set(feeds) == {"telegram", "twitter"}
    assert feeds["telegram"]
    assert feeds["twitter"]
    assert feeds["telegram"][0]["source"] == "telegram"
    assert feeds["twitter"][0]["source"] == "twitter"
