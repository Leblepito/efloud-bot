---
name: efloud-railway-supabase
description: Railway durumunu ve Supabase REST sayılarını salt okunur sorgula.
---

# Railway ve Supabase incelemesi

## Adımlar
1. Railway için proje `u2algo-prod`, hedef servis `efloud-bot` ve ortamı API yanıtından kimlikleriyle doğrula. GraphQL endpoint `https://backboard.railway.com/graphql/v2`; proje token'ını yerel `.env.railway` dosyasından yalnız istemci süreci içinde oku ve `Project-Access-Token` header'ına bellekte koy. Token'ı komut satırına, URL'ye, loga veya rapora koyma.
2. Salt okunur GraphQL sorgularıyla proje/servis/ortam kimliğini, son deployment durumunu ve deployment'ın hedef commit'ini iste. API şemasını ve yetki kapsamını kontrol et; yalnız `variables` sonucunun anahtarlarını, asla değerleri yazdırma. Referans/değer çözümlemesi veya API hatası secret içerebileceğinden ham yanıtı ya da stack trace'i dökme.
3. İsimlerin kaynak kodunda ve deployment konfigürasyonunda kullanımlarını ara. Hiç görünmeyenleri `olası gereksiz — doğrulanmadı` olarak işaretle; platform, runtime, harici servis veya dolaylı referanslar olabilir. Silme veya değişken değiştirme için önceden kullanıcı onayı gerekir; bu skill kendiliğinden değişiklik yapmaz.
4. Supabase proje ref'i `kjaicqpqfwnfbioofdib`. Yönetim token'ı geçersizse Management API ile tablo açmaya çalışma. Yetkili mevcut REST anahtarını yalnız süreç içinde güvenli dosyadan/ortamdan oku; `HEAD https://<ref>.supabase.co/rest/v1/<tablo>?select=*` isteğine bellek içi `apikey`, `Authorization` ve `Prefer: count=exact` başlıkları koy. Sadece HTTP durumunu ve `Content-Range` toplamını yazdır; tablo adı ve izinleri önce doğrula. RLS sonucu filtreleyebilir; sayım tüm tabloyu temsil etmeyebilir. 401/403/404/PGRST205 veya eksik anahtar halinde `doğrulanmadı` yaz, kayıtları dökme.

## Doğrulama
Proje, servis ve ortam kimliği; deployment zamanı/durumu; yalnız değişken adları; varsa REST sayısının kapsamı görev sonucunda bulunsun. Veri, secret, response body ve header değerleri yok. Yalnız isimden hareketle kullanım dışı olduğu kesinlenemez. Commit hash ve healthz yanıtını da ekle. Aynı komut iki kez başarısız olursa üçüncü kez deneme; blocked yaz.
