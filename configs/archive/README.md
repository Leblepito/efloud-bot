# Configs Archive

Bu klasör **artık aktif kullanılmayan** config dosyalarını barındırır. Tarihsel
referans olarak (PR / docs link'leri kırılmasın diye) repo'da tutulur, ama yeni
geliştirmede dikkate alınmaz.

## İçerik

| Config | Eski rol | Çekildiği yer |
|---|---|---|
| `config.phase1.yaml` | İlk conservative kurulum (Faz 1) | Phase 1 deploy döneminden |
| `config.phase2.yaml` | İntermedyer Phase 2 baseline (öncesi micro) | Phase 2 ana sürüm |
| `config.phase2_micro.yaml` | $1k mikro wallet için ayar | Phase 2 micro test variant |
| `config.phase2_1k_h1a_conf60.yaml` | H1 confluence sweep — conf=60 (loser, -34%) | Epic 6 H1 sweep |
| `config.phase2_1k_h1b_conf70.yaml` | H1 confluence sweep — conf=70 (mid, +4.89%) | Epic 6 H1 sweep |

## Aktif top-level configs (`configs/`)

| Config | Status |
|---|---|
| `config.aggressive_v1.yaml` | 🟢 Şu anki production |
| `config.phase2_1k_h2a2_risk2_notional6.yaml` | 🟡 Önceki production (rollback hedefi) |
| `config.phase2_1k_h1c_conf80.yaml` | 🟡 H1c sweet-spot baseline (referans) |
| `config.phase2_1k.yaml` | 🟡 Initial baseline (history) |
| `config.testnet.yaml` | 🟢 Testnet kurulumu için kullanılıyor |

## Strateji evrimi

Tam karşılaştırma için: [`docs/strategy-evolution.md`](../../docs/strategy-evolution.md)
