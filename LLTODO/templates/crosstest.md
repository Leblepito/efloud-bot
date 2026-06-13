# Template: Cross-Test (çapraz test)

> Kopyalayıp `LLTODO/tests/X-XXX-<tester>.md` olarak kaydedin.
> Kural: tester ≠ owner (kimse kendi işini test etmez). Kanıt (komut + çıktı) zorunlu.
> Tüm görevler PASS → TEST_CONSENSUS → DONE. Bir FAIL → owner'a fix-task.

```markdown
# X-XXX: <Görev/Epic ID> Cross-Test — @<tester>

**Tarih:** YYYY-AA-GG
**Tester:** @<tester>   (owner: @<owner> — farklı olmalı)
**Görev:** T-XXX
**Sonuç:** PASS / FAIL

## 1. Test Kapsamı
<Ne test edildi, hangi acceptance kriterine karşı>

## 2. Çalıştırılan Komutlar + Kanıt
```
<komut>
<çıktının ilgili kısmı / metrik>
```

## 3. Bulgular
- <gözlem 1>
- <gözlem 2>

## 4. Karar
**Sonuç:** PASS / FAIL
**FAIL ise fix-task:** tasks/BACKLOG/T-XXX-fix-*.md (owner: @<owner>)
```
