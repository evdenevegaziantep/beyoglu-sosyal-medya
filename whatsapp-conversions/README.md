# WhatsApp Reklam Dönüşüm Altyapısı

Bu servis, Click-to-WhatsApp reklamından gelen mesajdaki `ctwa_clid` değerini yakalar; gerçek müşteri durumlarını Meta Conversions API'ye geri gönderir.

## Ne yapar?

- WhatsApp Cloud API webhook doğrulaması
- `X-Hub-Signature-256` imza kontrolü
- Reklam tıklama kimliğini (`ctwa_clid`) saklama
- Ham mesaj metnini **saklamama**
- Telefon kimliğini tuzlu HMAC ile anonimleştirme
- Müşteriyi `message → qualified → booked` aşamalarında izleme
- `QualifiedLead` ve `Purchase` olaylarını Business Messaging Conversions API'ye gönderme
- Meta Automatic Events webhook'undaki `LeadSubmitted` ve `Purchase` olaylarını işleme
- Yönetim uçlarını ayrı `ADMIN_KEY` ile koruma

Bu sistem **reklam ücretlendirmesini değiştirmez**. Meta yine reklam teslimatına göre ücret yazar; altyapı Meta'nın hangi görüşmelerin gerçek müşteriye dönüştüğünü öğrenmesini ve raporlamasını sağlar.

## Uçlar

- `GET /health`
- `GET /webhook` — Meta doğrulaması
- `POST /webhook` — WhatsApp olayları
- `GET /admin/leads` — anonim müşteri listesi
- `POST /admin/leads/<id>/qualified` — gerçek taşıma talebi
- `POST /admin/leads/<id>/booked` — rezervasyon/satış; JSON: `{ "value": 12500 }`
- `GET /admin/summary`

Yönetim uçlarında `X-Admin-Key` başlığı zorunludur.

## Tamamlanması gereken dış adımlar

1. Meta Business doğrulamasını tamamlayın. Belge, şifre veya SMS kodunu hiçbir sohbet içinde paylaşmayın; yalnızca Meta paneline girin.
2. `+90 546 112 27 97` numarasının WhatsApp Manager doğrulamasını tamamlayın.
3. Bu klasörü kalıcı HTTPS adresi sağlayan bir sunucuya dağıtın. `render.yaml` ve `Dockerfile` hazırdır.
4. Sunucuda `.env.example` içindeki değerleri gizli ortam değişkenleri olarak tanımlayın.
5. Meta App Dashboard → Webhooks → WhatsApp Business Account bölümüne `https://SUNUCU/webhook` callback adresini ve `WEBHOOK_VERIFY_TOKEN` değerini girin.
6. `messages` ve `automatic_events` alanlarına abone olun.
7. Uygulamayı doğru WhatsApp Business Account'a `subscribed_apps` ile bağlayın.
8. Events Manager'da WhatsApp/Business Messaging dataset oluşturun; Dataset ID ve CAPI tokenını sunucuya ekleyin.
9. Test görüşmesinden `ctwa_clid` geldiğini, ardından `QualifiedLead` test olayının Events Manager'da göründüğünü doğrulayın.

## Yerel test

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python test_app.py
```

## Yayına geçiş koşulu

- WABA incelemesi tamamlanmış olmalı.
- Telefon doğrulaması tamamlanmış olmalı.
- Webhook imzası doğrulanmalı.
- Events Manager test olaylarını hatasız almalı.
- En azından anlamlı sayıda gerçek `QualifiedLead`/rezervasyon olayı birikmeli.
- Reklam hesabının ödeme modeli ayrıca çözülmeli; mevcut hesap ön ödemeli değildir.
