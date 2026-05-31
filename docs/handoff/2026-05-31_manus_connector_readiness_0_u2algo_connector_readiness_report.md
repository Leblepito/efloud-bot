# u2algo Connector Readiness Kontrolü — PRIVATE, DRY-RUN ONLY

**Hazırlayan:** Manus AI  
**Tarih:** 31 Mayıs 2026 UTC  
**Kapsam:** Bu kontrol yalnızca mevcut Manus hesabındaki connector durumunu, okunabilir bağlantıları, web/DNS/TLS erişimini ve ilk paylaşım pipeline’ı için eksikleri incelemiştir. **Hiçbir platforma yayın yapılmamış, post oluşturulmamış, mesaj gönderilmemiş ve dış aksiyon alınmamıştır.** Instagram tarafında yalnızca profil okuma, Meta Ads Manager tarafında yalnızca reklam hesabı okuma kontrolü yapılmıştır.

> Bu rapor yatırım tavsiyesi değildir. u2algo iletişimlerinde **kâr/getiri garantisi verilmemeli**, **fon yönetimi veya para toplama iması kurulmamali**, “yatırım tavsiyesi değildir”, “DYOR” ve “risk” vurgusu korunmalıdır.

## 1. Yönetici özeti

Mevcut hesapta ilk paylaşım pipeline’ı için en kritik connector’lar kısmen hazırdır: **Instagram**, **Meta Ads Manager**, **Google Drive**, **Make**, **Zapier** ve **Gmail** connector’ları yapılandırma listesinde etkin görünmektedir. Ancak gerçek çalışma düzeyinde iki önemli blokaj vardır. İlk olarak, Instagram native connector okunabilir durumdadır fakat bağlı görünen hesap **@leblepito** hesabıdır; hedef sosyal hesap olarak belirtilen **@u2algo** ile eşleşmemektedir. İkinci olarak, **Make** ve **Zapier** MCP tarafında OAuth yeniden yetkilendirme istemiş ve tool listesi alınamamıştır; bu nedenle fallback otomasyon hattı şu anda doğrulanmış çalışır durumda kabul edilmemelidir.

Web tarafında Railway’in sağladığı canlı URL `https://u2algo-site-production.up.railway.app/` erişilebilir ve 200 OK durumundadır.[1] Buna karşılık `https://u2algo.com/` Railway 404 “domain provisioned/network settings” ekranına düşmektedir; `https://www.u2algo.com/` ise tarayıcıda sertifika ortak ad hatası vermektedir.[2] Bu nedenle DNS/TLS tam hazır kabul edilmemeli ve custom domainleri içeren dış paylaşımlar bekletilmelidir.

## 2. Bu hesapta kullanılacak connector adları ve id’leri

Aşağıdaki tablo, mevcut Manus connector yapılandırmasından alınan ad, UID ve etkinlik durumlarını özetler. “MCP çalışma durumu” sütunu, bu dry-run sırasında yayın yapmadan yapılan okuma/listeleme denemesinin sonucudur.

| Öncelik | Connector adı | UID | Config durumu | Dry-run çalışma durumu | Not |
|---|---:|---|---|---|---|
| 1 | Instagram | `4b899211-fd12-410e-a8d2-264a409cbc78` | Etkin | Okunabilir | Profil okuma sonucu bağlı hesap **@leblepito** göründü; hedef **@u2algo** ile eşleşmiyor. |
| 2 | Meta Ads Manager | `c073ede4-35a7-4c89-8158-c9b40c489932` | Etkin | Okunabilir | Bağlı reklam hesabı görüldü: `act_327551395`, ad: `Utkucan Uysal`, durum: `ACTIVE`, para birimi: `USD`. |
| 3 | Google Drive | `f8900a57-4bd7-46cc-83a3-5ebd2420a817` | Etkin | CLI düzeyinde token yok | Asset deposu için gerekli; komut satırı erişiminde “Token not found. Please re-authorize to continue.” hatası görüldü. |
| 4 | Make | `f8405590-5602-4fee-bfd6-f221623e6f72` | Etkin | OAuth bekliyor | Tool listesi OAuth yetkilendirmesi bekledi; fallback hattı doğrulanamadı. |
| 5 | Zapier | `433d2fe0-e56d-42b2-8625-9996eab0bb1d` | Etkin | OAuth bekliyor / zaman aşımı | Tool listesi OAuth gerektirdi ve zaman aşımına düştü; fallback hattı doğrulanamadı. |
| 6 | Gmail | `9444d960-ab7e-450f-9cb9-b9467fb0adda` | Etkin | Tool listesi alınabilir | Taslak e-posta veya iç bildirim için kullanılabilir; bu görevde mesaj gönderilmedi. |
| 7 | n8n | `d6b4170a-4001-450d-823a-287dfd9716a7` | Devre dışı | Kullanılamaz | Fallback olarak isteniyorsa Manus web app içinde etkinleştirilmesi gerekir. |
| 8 | Instagram Creator Marketplace | `9777f7bd-4ca3-431a-98d6-a7ed5221dd81` | Devre dışı | Gerekli değil | İlk yayın pipeline’ı için gerekli görünmüyor. |

Yapılandırmada **X/Twitter**, **Telegram** veya **YouTube** için doğrudan native yayın connector’ı bulunamadı. Bu platformlar için ilk aşamada native Manus connector yerine **draft-only içerik üretimi + manuel yayın** veya Make/Zapier/n8n üzerinden onaylı fallback senaryosu kullanılmalıdır. Özellikle X, Telegram ve YouTube için otomatik yayın hattı, custom domain DNS/TLS hazır olmadan ve her platform için yetkilendirme doğrulanmadan aktif edilmemelidir.

## 3. İlk yayın öncesi Manus web app içinde authorize edilmesi gerekenler

Aşağıdaki yetkilendirme listesi, “yayın kapalı, taslak/onaylı akış” yaklaşımını koruyacak şekilde hazırlanmıştır. Burada amaç otomatik paylaşımı açmak değil, ilk paylaşım öncesi üretim, kontrol, asset depolama ve raporlama hattını güvenli şekilde hazırlamaktır.

| Connector / Entegrasyon | Yetkilendirme gereği | Öncelik | Gerekçe | Güvenli ayar |
|---|---|---:|---|---|
| Instagram | **Yeniden doğrulanmalı / doğru hesaba bağlanmalı** | Kritik | Mevcut okuma sonucu **@leblepito** göründü, hedef **@u2algo**. Native connector kullanılacaksa doğru Instagram Business/Professional hesabı bağlı olmalıdır. | Native yayın aracı yalnızca manuel kullanıcı onayıyla çalışmalı; otomatik yayın kapalı kalmalı. |
| Meta Ads Manager | Hazır görünüyor, erişim kapsamı doğrulanmalı | Yüksek | Reklam hesabı okundu ve `ACTIVE` göründü. İlk aşamada sadece raporlama/okuma için kullanılmalı. | Campaign/ad değişikliği, bütçe, yayın veya optimizasyon aksiyonu kapalı kalmalı. |
| Google Drive | **Yeniden authorize edilmeli** | Yüksek | Connector config etkin görünse de Drive CLI token bulunamadı. Asset deposu klasörleri, naming ve paylaşılabilir URL akışı doğrulanmalı. | Asset depolama ve okunabilir public/share link üretimi ayrı onay adımıyla yapılmalı. |
| Make | **OAuth tamamlanmalı** | Orta-yüksek | Config etkin fakat tool listesi OAuth bekledi. On-demand scenario listesi alınmadan fallback hazır sayılmaz. | Sadece “draft oluştur”, “review kuyruğuna ekle”, “dosya kopyala” gibi aksiyonsuz veya onaylı senaryolar açık olmalı. |
| Zapier | **OAuth tamamlanmalı** | Orta-yüksek | Config etkin fakat MCP tool listesi OAuth hatası/zaman aşımı verdi. | Yayın, mesaj gönderme, form submit gibi aksiyonlar “manual approval” veya “draft-only” olmalı. |
| n8n | Etkinleştirilmeli ve ayrı yetkilendirilmeli | Orta | Config devre dışı. Fallback isteniyorsa senaryo/webhook tarafı ayrı kurulmalı. | Webhook’lar yalnızca taslak üretmeli; otomatik platform publish kapalı olmalı. |
| Gmail | Hazır görünüyor | Düşük-orta | Tool listesi alınabildi. İç review e-postaları için draft-only kullanılabilir. | `send` yerine “draft kaydet” ve kullanıcı onayı şartı korunmalı. |

## 4. Güvenli, otomatik yayın kapalı / draft-only pipeline önerisi

İlk paylaşım hattı, sosyal platformlara yazma yetkisi verilmiş olsa bile **yayın otomasyonu kapalı** olacak şekilde tasarlanmalıdır. Önerilen akış, içeriği önce üretir, risk/compliance kontrolünden geçirir, asset dosyalarını depolar ve ancak insan onayı sonrasında platform bazlı manuel veya connector onay kartlı paylaşımı mümkün kılar.

| Aşama | Çıktı | Otomasyon seviyesi | Kontrol kapısı | Neden güvenli? |
|---|---|---|---|---|
| İçerik brief’i | Türkçe post metni, başlık, CTA, risk uyarısı | Otomatik üretim olabilir | Compliance checklist | Kâr garantisi, yatırım tavsiyesi, fon yönetimi iması ve agresif getiri dili engellenir. |
| Asset hazırlama | Görsel/video dosyaları ve alt metin | Otomatik üretim veya manuel tasarım | Dosya adı, oran, boyut, marka tonu kontrolü | Platforma gönderim yapılmadan format uyumsuzlukları yakalanır. |
| Asset depo | Google Drive klasörü ve paylaşılabilir dosya linkleri | Drive yetkilendirmesi sonrası yarı otomatik | Link erişimi “view-only” ve doğru dosya versiyonu | Instagram API gibi sistemler medyayı public erişilebilir URL’den çekebildiği için link doğrulaması gerekir.[3] |
| Platform taslakları | Instagram caption, X thread, Telegram mesajı, Shorts açıklaması | Draft-only | İnsan onayı | Metinler yayınlanmaz; sadece review kuyruğuna alınır. |
| Preflight | URL, DNS/TLS, UTM, disclaimer, görsel ratio kontrolü | Otomatik kontrol | “Ready/Blocked” bayrağı | Custom domain bozuksa ilgili CTA otomatik olarak bloklanır. |
| Yayın | Manuel yayın veya connector onay kartı | Kapalı varsayılan | Açık insan onayı | Bu görevdeki güvenlik çizgisi korunur; hiçbir kör otomatik publish yapılmaz. |
| Raporlama | Meta Ads ve organik performans okuma | Sadece read-only | Veri kapsamı ve tarih aralığı kontrolü | Reklam hesabında değişiklik yapılmadan performans izlenir. |

Bu akış için pratik öneri, Google Drive’da `u2algo/assets/YYYY-MM-DD_campaign-slug/` klasör yapısı kurmak; her kampanya için `source/`, `exports/`, `captions/`, `review/` ve `published/` alt klasörlerini kullanmaktır. İlk aşamada `published/` klasörü yalnızca manuel olarak doldurulmalı; otomasyon sadece `review/` klasörüne taslak ve asset üretmelidir.

## 5. DNS hazır olmadan bekletilmesi gereken paylaşımlar

Railway URL’i canlı olsa da apex ve www custom domainleri henüz güvenilir şekilde hazır değildir. `u2algo.com` HTTPS üzerinden Railway 404 ekranına düşmektedir; `www.u2algo.com` sertifika hostname uyuşmazlığı vermektedir. Bu nedenle dış platformlarda marka güveni, tracking ve reklam incelemesi açısından custom domain kullanılacak tüm paylaşımlar bekletilmelidir.

| Paylaşım türü | DNS/TLS hazır değilken durum | Gerekçe | Geçici güvenli alternatif |
|---|---|---|---|
| Bio link değişiklikleri | Bekletilmeli | `u2algo.com` 404 ve `www` TLS hatası marka güvenini düşürür. | Geçici olarak Railway URL’i sadece iç testte kullanılabilir; halka açık bio için beklemek daha güvenli. |
| İlk lansman duyurusu | Bekletilmeli | İlk izlenimde broken domain görünmemeli. | “Yakında” teaser metni link olmadan draft olarak tutulabilir. |
| Reklam kampanyası / paid traffic | Kesinlikle bekletilmeli | Destination URL hataları reklam onayı ve kullanıcı güveni açısından risklidir. | Meta Ads Manager sadece raporlama modunda kalmalı. |
| Instagram carousel CTA | Linkli CTA bekletilmeli | Instagram caption linkleri tıklanabilir olmasa da bio/domain referansı bozuk görünür. | “Profil linki yakında” veya linksiz eğitim carousel’i draftta kalabilir. |
| X/Twitter thread linkleri | Bekletilmeli | Broken domain paylaşımı indekslenebilir ve kalıcı güven sorunu yaratabilir. | Linksiz, eğitim amaçlı thread taslağı hazırlanabilir. |
| Telegram kanal duyurusu | Bekletilmeli | Telegram’da link preview kırık/404 görünebilir. | Link içermeyen risk/compliance duyurusu taslakta tutulabilir. |
| YouTube Shorts açıklama linki | Bekletilmeli | Açıklama linki bozuksa kullanıcı akışı zarar görür. | Shorts draft açıklamasında domain linki kullanılmamalı. |

## 6. Platformlara göre asset formatları

Aşağıdaki format matrisi, ilk paylaşım pipeline’ında kullanılacak güvenli üretim hedeflerini verir. Instagram için native connector’ın kendi sınırları ayrıca dikkate alınmalıdır: connector aracı post için 1–10 medya, story için 1–10 medya, reels için 1 medya kabul eder; image dosya limiti 8 MB, reels video limiti 300 MB, story video limiti 100 MB olarak listelenmiştir. Meta’nın resmi Instagram içerik yayınlama dokümanı ise API ile yayınlanan medyanın yayın denemesi sırasında public erişilebilir URL’de bulunması gerektiğini, JPEG’in desteklenen görsel format olduğunu ve carousel’in en fazla 10 medya içerebildiğini belirtir.[3]

| Platform | Önerilen ana format | Güvenli çözünürlük / oran | Dosya türü | İçerik notu | Publish durumu |
|---|---|---|---|---|---|
| X / Twitter | Tek görsel veya kısa video; gerekirse thread | Görsel için 1600×900 veya 1080×1080; video için 1280×720, 720×1280 veya 720×720 | JPG/PNG/WebP; video H.264 + AAC | X API dokümanına göre bir postta en fazla 4 fotoğraf, 1 GIF veya 1 video eklenebilir; görsel dosyaları 5 MB altında tutulmalıdır.[4] | Native connector yok; draft-only + manuel yayın önerilir. |
| Instagram carousel | Eğitim/şeffaflık carousel’i | 1080×1350 portre veya 1080×1080 kare; tüm slaytlar aynı oran | JPEG tercih edilmeli | 5–8 slaytlık açıklayıcı içerik; ilk slaytta vaat değil araştırma çerçevesi; son slaytta “yatırım tavsiyesi değildir / DYOR / risk” | Native connector doğru hesaba bağlanana kadar yayın yok. |
| Instagram Reel | Kısa dikey video | 1080×1920, 9:16 | MP4/H.264/AAC | 15–45 saniyelik araştırma süreci, backtest/shadow rapor bağlamı; getiri iddiası yok | Native connector doğru hesaba bağlanana kadar yayın yok. |
| Telegram | Metin + görsel veya kısa video | Görsel 1080×1080 veya 1600×900; video 720×1280 | JPG/PNG/MP4 | Telegram Bot FAQ botların dosya gönderim limitini 50 MB olarak belirtir; bu yüzden assetler 50 MB altına sıkıştırılmalıdır.[5] | Native connector yok; bot/fallback kurulmadan manuel veya draft-only. |
| YouTube Shorts | Dikey kısa video | 1080×1920, 9:16; maksimum 3 dakika hedeflenmeli | MP4/H.264/AAC | YouTube’un resmi Shorts yardım içeriği üç dakikalık Shorts yaklaşımını ve geniş 16:9 içeriklerin Shorts olarak sınıflandırılmaması gerektiğini açıklar.[6] | Native connector yok; upload manuel veya onaylı fallback. |

## 7. Compliance kontrol şablonu

Her taslak, yayın öncesinde aşağıdaki kontrol metninden geçmelidir. Metinlerde “kesin kazanç”, “garantili getiri”, “pasif gelir”, “fon toplanıyor”, “paranızı yönetiyoruz”, “sinyal satıyoruz” gibi ifadeler kullanılmamalıdır. İzinli çerçeve, **araştırma**, **gözlem**, **risk disiplini**, **backtest/shadow rapor**, **ölçülebilir süreç** ve **şeffaflık** olmalıdır.

| Kontrol maddesi | Kabul kriteri | Bloklayan örnek |
|---|---|---|
| Yatırım tavsiyesi | “Yatırım tavsiyesi değildir; kendi araştırmanı yap (DYOR)” ifadesi korunur. | “Bu coini alın”, “kesin fırsat” |
| Getiri dili | Geçmiş sonuçların geleceği garanti etmediği belirtilir. | “Garantili kâr”, “risksiz getiri” |
| Fon yönetimi | Kullanıcı parasını tutma/yönetme iması yoktur. | “Fonunu bize bırak”, “portföyünü yönetelim” |
| Risk | Volatilite, kayıp riski ve belirsizlik açıkça vurgulanır. | “Risk yok”, “stop gerekmez” |
| Şeffaflık | Backtest ve canlı gözlem ayrımı net yapılır. | “Canlı sonuçlar kesin kanıt” |
| CTA | Waitlist veya takip çağrısı, yatırım yönlendirmesi gibi durmaz. | “Hemen al/sat”, “kaçırma, gir” |

## 8. İlk yayın için önerilen güvenli sıra

İlk adım olarak domain hazır olana kadar halka açık linkli lansman yapılmamalıdır. Buna paralel olarak Instagram connector’ın doğru hedef hesap olan **@u2algo** ile eşleştirilmesi gerekir; şu an okunan hesap **@leblepito** olduğu için native Instagram publish hattı bloklu sayılmalıdır. Google Drive yetkisi yenilenip asset deposu doğrulanmalı, ardından Make/Zapier/n8n fallback sadece **draft-only** senaryolarla test edilmelidir.

| Sıra | Aksiyon | Beklenen sonuç | Ready kriteri |
|---:|---|---|---|
| 1 | `u2algo.com` ve `www.u2algo.com` DNS/TLS düzeltmesi | Her iki domain 200 OK veya doğru canonical redirect verir | 404 yok, TLS hostname hatası yok |
| 2 | Instagram hesabını doğrulama | Native connector **@u2algo** profilini okur | `get_account_info` hedef hesapla eşleşir |
| 3 | Google Drive re-authorization | Asset klasörü okunur/yazılır; paylaşım linkleri test edilir | Token hatası yok, public/view-only link doğrulanır |
| 4 | Make/Zapier OAuth | On-demand tool/scenario listesi alınır | Publish aksiyonu olmayan draft-only senaryo görünür |
| 5 | Compliance preflight | Tüm metinler risk ve DYOR uyarısı taşır | Bloklayan vaat dili yok |
| 6 | İlk içerik dry-run | Platformlara uygun dosya ve caption seti üretilir | `review/` klasörüne taslak olarak düşer, yayın yok |

## 9. Son readiness kararı

Genel durum **kısmen hazır, yayın için bloklu** olarak değerlendirilmelidir. Railway live URL çalışır durumdadır, Meta Ads Manager raporlama okuması yapılabilir, Gmail okunabilir ve Instagram connector teknik olarak yanıt vermektedir. Ancak doğru Instagram hesabı eşleşmediği, Google Drive token erişimi eksik olduğu, Make/Zapier OAuth tamamlanmadığı ve custom domain DNS/TLS hazır olmadığı için ilk halka açık paylaşım hattı **yayına açılmamalıdır**. En güvenli sonraki adım, tüm içeriklerin Google Drive review deposuna draft olarak üretilmesi ve domain + connector düzeltmeleri tamamlanana kadar sosyal platformlarda manuel veya otomatik paylaşım yapılmamasıdır.

## References

[1]: https://u2algo-site-production.up.railway.app/ "u2algo Railway live site"
[2]: https://u2algo.com/ "u2algo custom apex domain"
[3]: https://developers.facebook.com/docs/instagram-platform/content-publishing/ "Meta for Developers — Instagram Platform Content Publishing"
[4]: https://docs.x.com/x-api/media/quickstart/best-practices "X API — Media upload best practices"
[5]: https://core.telegram.org/bots/faq "Telegram Bots FAQ"
[6]: https://support.google.com/youtube/answer/15424877?hl=en "YouTube Help — Understand three-minute YouTube Shorts"
