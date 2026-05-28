"""Social doctrine extraction tests."""


def test_extract_doctrine_identifies_btc_msb_ote_fvg_setup():
    from backend.social.doctrine import extract_doctrine

    item = {
        "id": "tg-fb1",
        "source": "telegram",
        "author": "Efloud TA & Charts",
        "content": "📌 BTC Güncelleme: 1D grafikte market yapısı bullish (MSB gerçekleşti). OTE bölgesinden (93200-94100) gelen pullback tepkisiyle 103k hedefine doğru ilerliyoruz. Güçlü FVG alanları destek olarak çalışmaya devam edecektir.",
        "timestamp": "2026-05-26T14:30:00Z",
    }

    doctrine = extract_doctrine(item)

    assert doctrine["feed_id"] == "tg-fb1"
    assert doctrine["symbols"] == ["BTC/USDT"]
    assert doctrine["timeframes"] == ["1d"]
    assert doctrine["bias"] == "bullish"
    assert "MSB" in doctrine["structure_terms"]
    assert "OTE" in doctrine["zones"]
    assert "FVG" in doctrine["zones"]
    assert "pullback" in doctrine["setup_recipe"]
    assert 93200.0 in doctrine["levels"]
    assert 94100.0 in doctrine["levels"]
    assert 103000.0 in doctrine["levels"]
    assert doctrine["confidence"] > 0.5


def test_extract_doctrine_identifies_eth_fvg_reaction_and_targets():
    from backend.social.doctrine import extract_doctrine

    item = {
        "id": "tg-fb2",
        "source": "telegram",
        "author": "Efloud TA & Charts",
        "content": "📈 ETH/USDT: 4H grafikte FVG (Fair Value Gap) test edildi ve reaksiyon alındı. 2480 seviyesi korunduğu sürece üst likidite hedefleri (2650 - 2800) masada kalacaktır. Risk yönetimine sadık kalın.",
        "timestamp": "2026-05-25T11:15:00Z",
    }

    doctrine = extract_doctrine(item)

    assert doctrine["symbols"] == ["ETH/USDT"]
    assert doctrine["timeframes"] == ["4h"]
    assert doctrine["bias"] == "bullish"
    assert doctrine["zones"] == ["FVG"]
    assert "liquidity_target" in doctrine["setup_recipe"]
    assert "risk_management" in doctrine["risk_terms"]
    assert doctrine["levels"] == [2480.0, 2650.0, 2800.0]


def test_extract_doctrine_marks_educational_liquidity_note():
    from backend.social.doctrine import extract_doctrine

    item = {
        "id": "tg-fb3",
        "source": "telegram",
        "author": "Efloud TA & Charts",
        "content": "💡 Mixed Price Action (MPA) Notu: Sabit indikatörlere bağımlı kalmak yerine piyasanın likidite hareketlerini izleyin. Likidite temizliği yapılan her bölge potansiyel bir dönüş noktasıdır.",
        "timestamp": "2026-05-24T09:00:00Z",
    }

    doctrine = extract_doctrine(item)

    assert doctrine["symbols"] == []
    assert doctrine["bias"] == "educational"
    assert "MPA" in doctrine["structure_terms"]
    assert "liquidity_sweep" in doctrine["liquidity_terms"]
    assert "reversal_zone" in doctrine["setup_recipe"]
