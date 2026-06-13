# Template: Split (görev dağıtımı)

> Kopyalayıp `LLTODO/splits/S-XXX-<epic>.md` olarak kaydedin.
> SPLIT gate: implementasyondan önce yazılır, 3/3 ACK (veya 2/3 + operatör) → SPLIT_AGREED.
> Kural: `tester` ≠ `owner`. Her atamanın tek cümlelik gerekçesi yazılır.

```markdown
# S-XXX: <Epic ID> Görev Dağıtımı

**Tarih:** YYYY-AA-GG
**Yazar:** @<agent>
**Epic:** P-XXX
**Durum:** PROPOSED / SPLIT_AGREED

## Dağıtım

| Görev | owner | tester | Atama gerekçesi (tek cümle) |
|---|---|---|---|
| T-0xx <slug> | @<agent> | @<agent ≠ owner> | <neden bu ajan: alan/uzmanlık/erişim> |
| T-0xx <slug> | @<agent> | @<agent ≠ owner> | <gerekçe> |

## ACK'ler (3/3 hedef)
- ACK @<agent> @ YYYY-AA-GG HH:MM — <opsiyonel not>
- ACK @<agent> @ YYYY-AA-GG HH:MM
- (operatör fallback: 2/3 ACK + operatör onayı → SPLIT_AGREED)

## Karar
**Sonuç:** SPLIT_AGREED / NEEDS_REVISION
**Gerekçe:** <bir cümle>
```
