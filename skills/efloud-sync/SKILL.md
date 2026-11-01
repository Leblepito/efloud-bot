---
name: efloud-sync
description: Efloud-bot local, GitHub ve VPS commit farklarını güvenle karşılaştır.
---

# Efloud commit eşitleme

## Adımlar
1. Local `git status --short --branch`, `git rev-parse HEAD` ve `git branch --show-current`; GitHub için `git ls-remote origin refs/heads/master`; VPS için `ssh root@2.28.139.82 'cd /opt/efloud-bot && git rev-parse HEAD && git status --short --branch'` çalıştır. Uzak branch'i local önbellekten değil doğrudan sorgula.
2. Tam hash'leri, çalışma ağacı durumunu ve karşılaştırma zamanını görev dosyasına yaz. Çalışma ağacı temizliği görüntüyü sınırlayabilir; Git HEAD eşitliği çalışan Docker imajının aynı commit olduğunu kanıtlamaz.
3. Senkronizasyon yazma işlemi gerektiriyorsa önce dal/ata ilişkisini ve kullanıcı iznini doğrula. Korunmayan değişiklikleri ezme; `reset --hard`, force push ve otomatik merge yapma. VPS çalışma ağacı güncellemesi/deploy canlı sistemi etkileyebilir: `efloud-deploy` kapılarını ve Telegram onayını uygula. Pozisyon kontrolünü ve onayı atlama.

## Doğrulama
Değişiklik yapıldıysa hedefleri yeniden doğrudan oku, hash'leri karşılaştır ve imajın ayrıca doğrulanıp doğrulanmadığını belirt. Erişilemeyen hedefleri eşit varsayma; `doğrulanmadı` yaz. Secret dökme.
