---
name: efloud-journal-analysis
description: Trade journal PnL, stop serisi, SL mesafesi ve süre analizi yap.
---

# Efloud journal analizi

## Adımlar
1. Canlı journal yolunu ve erişimini salt okunur doğrula: `/app/state_1k/trade_journal.jsonl`. Gerçek satırları, sırları ve gereksiz kimlik/veri alanlarını raporlama. Journal dosyasını veya bot state'ini değiştirme.
2. `python scripts/analyze_trade_journal.py --help` ile seçenekleri doğrula; script varsayılan olarak son 7 günü inceler. `--journal <dosya>` veya stdin için `--journal -` kullan. Uzak kopya gerekiyorsa canlı sisteme script yazmadan dosyayı izinli, korumalı yerel scratch alanına al ve kullanım sonrası politikaya uygun temizle; hassas verileri commit etme. Mümkünse SSH üzerinden salt okunur akış kullan.
3. Pencereyi UTC olarak ve hangi timestamp'e göre filtrelendiğini raporla. `realized_pnl` kaynağının tahmin veya borsa neti olduğunu ayır; kaynak etiketi de eski olabilir. Stop serisini `exit_reason` üzerinden tanımla, negatif PnL ile stop'u karıştırma. SL mesafesi `sl_initial` ve giriş fiyatından türetilir; bu alan sonradan güncellenmiş olabileceğinden orijinal risk olduğu garanti değildir. Tutma süresi UTC entry ile exit farkıdır.
4. Eksik/hatalı satır, zaman, fiyat, SL, PnL ve exit reason sayılarını bildir; elde olmayan metrikleri sıfır veya borsa tarafından doğrulanmış diye sunma. Canlı pozisyon kayıtlarını kapanmış işlem toplamlarına katma.

## Doğrulama
Script'in sentetik testleri ve gerçek veri analizinin zaman penceresi, kayıt sayısı, PnL/provenans, ardışık stop, SL mesafesi, tutma süresi ve eksik verileri görev dosyasında olsun. Borsa mutabakatı yapılmadıysa ayrı belirt. Secret'sız komut, commit hash ve healthz yanıtını ekle.
