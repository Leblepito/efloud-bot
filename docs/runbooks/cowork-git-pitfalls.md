# Cowork / sandbox git tuzakları

> CLAUDE.md'deki "Cowork/Sandbox Git Uyarısı (2026-07-03)" bölümünden taşındı (metin aynen).
> Ortam-özel operasyonel not: yalnız Cowork sandbox'ından (mount senkron katmanı üzerinden)
> bu repo'da çalışırken geçerlidir.

Cowork sandbox'ından bu repo'da çalışırken mount senkron katmanı git metadata'sını
bozabiliyor (`.git/index` null-byte korupsiyonu, `.git/config` boşalması, Windows
edit'lerinin Linux'ta kesik görünmesi). Kural: (1) commit'leri `GIT_INDEX_FILE=/tmp/...`
sandbox-local index ile yap, (2) her git hatasında önce ilgili `.git/` dosyasında
null-byte kontrolü yap, (3) dosya yazımlarını tek seferde deterministik yap.
Detay: `git show f96b7d8^:docs/handoff/2026-07-03-merge-bugfix-and-repo-hardening.md` (doküman `f96b7d8`'de repodan kaldırıldı, git geçmişinde duruyor).

## Doğrulama

```bash
# index başlığı sağlam mı (beklenen: DIRC; ikili dosyadır, null-byte'lar normaldir)
head -c 4 .git/index; echo
# metin dosyalarında null-byte olmamalı (beklenen: 0) ve config boş olmamalı
tr -dc '\000' < .git/config | wc -c
test -s .git/config && git config --get remote.origin.url
```
