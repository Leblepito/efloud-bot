# u²Algo — Brand Kit & Tasarım Referansı

> Kaynak: Leblepito/u2Algo repo'sunun frontend tasarım sistemi (eski repo, marka+logo için referans alındı).
> O repo SİLİNECEK — bu klasör efloud-bot içinde kalıcı marka kaynağıdır.
> Yeni u2algo sitesi/uygulaması SIFIRDAN yeni bot mantığıyla kurulacak; görsel kimlik buradan gelir.
> Alındığı tarih: 2026-05-31

---

## 1. Logo

| Dosya | Kullanım |
|---|---|
| `assets/logo-mark.svg` | Kare logo (512×512), favicon/app-icon/sosyal avatar. Yükselen grafik eğrisi + "u²" + filigran "ALGO". |
| `assets/logo-horizontal.svg` | Yatay logo (180×44), nav/header. "u²Algo" + mini eğri. |
| `assets/icon-192.png` / `icon-512.png` / `icon-512-maskable.png` | PWA ikonları. |
| `assets/favicon.ico` | Tarayıcı favicon. |

**Logo gradient (mavi→indigo→mor):** `#0EA5E9 → #6366F1 → #7C3AED`
Konsept: yükselen fiyat eğrisi üzerinde "u²" karakteri; tepe noktasında parlayan mor nokta.

---

## 2. Renk Paleti (kanonik — design-tokens.ts + globals.css'ten)

### Marka çekirdeği
```
--u2-cyan:    #00f0ff   /* primary accent — buton, link, aktif durum */
--u2-blue:    #0080ff   /* cyan→blue gradient'in ucu */
--u2-indigo:  #6366f1
--u2-purple:  #a855f7
```

### Gradient'ler
```
CTA buton:     linear-gradient(90deg/135deg, #00f0ff → #0080ff)
Text gradient: linear-gradient(90deg, #00f0ff 0%, #0080ff 50%, #a855f7 100%)
Logo:          linear-gradient(135deg, #0EA5E9 → #6366F1 → #7C3AED)
```

### Zemin & yüzeyler
```
--u2-bg-base:  #050510                      /* near-black, mavi tonlu */
Hero glow:     3 katmanlı radial (cyan .10 / indigo .07 / purple .06)
Kart bg:       rgba(255,255,255,0.03)        /* asla solid */
Kart bg hover: rgba(255,255,255,0.05)
Kart border:   rgba(255,255,255,0.06)
Border hover:  rgba(255,255,255,0.12)
```
**KURAL:** Border'lar ASLA solid renk değil — daima `rgba(255,255,255,opacity)` (white/opacity).

### Metin
```
Primary:   #f8fafc
Secondary: #94a3b8
Muted:     #64748b
```

### Trading durum renkleri
```
Bullish/LONG/profit:  #00ff88  (green)
Bearish/SHORT/loss:   #ff3366  (red)
Neutral:              #64748b
Warning:              #ffaa00 / #fbbf24
```

---

## 3. Tipografi
```
Body:    Inter            (--font-inter)
Mono:    JetBrains Mono   (--font-jetbrains)  + font-variant-numeric: tabular-nums
Display: Outfit           (--font-outfit)     — başlıklar, font-display class
```
Heading deseni: `text-white font-display font-bold tracking-tight`

---

## 4. Bileşen Desenleri (Tailwind)
```
Kart:          bg-white/[0.03] border border-white/[0.06] rounded-xl backdrop-blur-sm
Kart hover:    hover:bg-white/[0.05] hover:border-white/[0.12] transition-all duration-300
Gradient CTA:  bg-gradient-to-r from-[#00f0ff] to-[#0080ff] text-white font-semibold rounded-xl
Ghost buton:   border border-white/[0.1] bg-white/[0.04] text-slate-200 rounded-xl hover:bg-white/[0.08]
Glass panel:   bg-slate-900/60 backdrop-blur-xl border-white/10  (.glass-panel)
Tab aktif:     bg-cyan-500/20 text-cyan-300 rounded-lg
Köşe:          rounded-xl (kart/buton), rounded-2xl (büyük), rounded-full (badge)
Bölüm padding: py-20 px-4
Container:     mx-auto max-w-6xl
```

### Radius ölçeği
```
sm 6px · md 8px · lg 12px · xl 16px (varsayılan kart) · 2xl 20px · full 9999px
```

---

## 5. Animasyonlar (globals.css)
Hepsi `prefers-reduced-motion`'a saygılı olmalı.
```
animate-fade-in      opacity 0→1 (.25s)
animate-slide-up     translateY(20px)→0 (.5s)
animate-glow-pulse   opacity pulse (4s)
animate-cta-glow     CTA parıltısı, cyan glow (3s)
animate-shimmer      skeleton loading
animate-live-dot     canlı veri noktası (2s)
animate-stagger-in   kart giriş (.4s)
animate-count-up     sayı sayacı blur→net (.6s)
scroll-reveal        IntersectionObserver ile .visible
```
Easing: `--u2-ease-standard: cubic-bezier(0.16,1,0.3,1)` · emphasized: `cubic-bezier(0.34,1.56,0.64,1)`

### Arka plan desenleri
```
.bot-grid-bg       cyan çizgi grid 40px
.trading-grid-bg   radial dot grid 24px
```

---

## 6. Kaynak Dosyalar (bu klasörde)
```
css/globals.css        — tam Tailwind v4 @theme + tokens + animasyonlar + light mode (672 satır)
css/design-tokens.ts   — JS-land token sabitleri (colors/spacing/radius/typography/tw helpers)
css/root-layout.tsx    — Next.js font kurulumu (Inter/JetBrains/Outfit next/font)
css/postcss.config.mjs
landing-reference/      — eski landing component'leri (DESEN referansı, kopyalanmaz; yeni tasarımda fikir kaynağı)
                          Hero, Pricing, FAQ, FeatureCards, ComparisonTable, RiskDisclaimer, ROICalculator vb.
```

---

## 7. GTM Compliance Hatırlatması
Marka görseli ne olursa olsun, içerik kuralı değişmez (docs/marketing/GO_TO_MARKET):
- Getiri garantisi / "kesin kazanır" / fon toplama YASAK.
- "Yatırım tavsiyesi değildir" + risk disclosure ZORUNLU.
- landing-reference içindeki ROICalculator/Testimonials gibi bileşenler kullanılacaksa GTM'e göre süzülmeli (uydurma metrik/yorum yok).
