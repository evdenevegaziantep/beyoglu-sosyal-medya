# Render Kurulumu — WhatsApp Dönüşüm Webhook'u

Kod güvenli biçimde GitHub deposundaki `whatsapp-conversions/` klasörüne yüklendi. Depo köküne Render Blueprint dosyası `render.yaml` eklendi.

## 1. Render Blueprint'i oluşturun

1. `https://dashboard.render.com/` adresine gidin.
2. **New → Blueprint** seçin.
3. GitHub hesabınızı Render'a bağlayın.
4. Beyoğlu sosyal medya deposunu seçin.
5. Render, depo kökündeki `render.yaml` dosyasını otomatik bulacaktır.
6. Servis adı `beyoglu-whatsapp-conversions` olarak görünmelidir.

## 2. Gizli değerleri yalnızca Render paneline girin

Render otomatik oluşturacak:

- `WEBHOOK_VERIFY_TOKEN`
- `ADMIN_KEY`
- `PII_HASH_SALT`

Sizin Meta panelinden doğrudan Render'a girmeniz gereken:

- `META_APP_SECRET`

Dönüşüm dataseti oluşturulduktan sonra girilecek:

- `META_DATASET_ID`
- `CAPI_ACCESS_TOKEN`

Bu değerleri sohbet içinde paylaşmayın ve GitHub'a yüklemeyin.

## 3. Sağlık kontrolü

Dağıtım tamamlandığında şu adresi açın:

`https://SERVIS-ADRESI.onrender.com/health`

Beklenen ilk yanıt:

```json
{"ok":true,"dataset_configured":false}
```

## 4. Meta webhook bağlantısı

Meta App Dashboard'da `BeyogluPaylasim` uygulamasını açın:

1. WhatsApp → Configuration → Webhooks
2. Callback URL: `https://SERVIS-ADRESI.onrender.com/webhook`
3. Verify token: Render'ın oluşturduğu `WEBHOOK_VERIFY_TOKEN`
4. `messages` ve `automatic_events` alanlarına abone olun.
5. Uygulamayı doğru WhatsApp Business Account'a bağlayın.

## 5. Doğrulamalar

- WABA incelemesi şu anda `PENDING`.
- İşletme doğrulaması `pending_submission`.
- Telefon kod doğrulaması `NOT_VERIFIED`.

Belge ve doğrulama kodlarını yalnızca Meta panelinde kullanın; sohbet içinde paylaşmayın.

## 6. Dataset ve CAPI

Events Manager'da Business Messaging/WhatsApp dataseti oluşturulduğunda:

1. Dataset ID'yi Render'da `META_DATASET_ID` alanına girin.
2. Sistem kullanıcısı veya dataset tokenını `CAPI_ACCESS_TOKEN` alanına girin.
3. Servisi yeniden dağıtın.
4. `/health` yanıtında `dataset_configured:true` olduğunu doğrulayın.

Sonra test WhatsApp konuşmasıyla `ctwa_clid`, `QualifiedLead` ve `Purchase` olayları kontrol edilecektir.

## Reklam güvenliği

- Mevcut reklam kapalıdır.
- Sabah yeniden başlatma kuralı kapalıdır.
- Sonuç maliyeti 3 günlük ortalamada ₺80'i aşarsa reklam setini otomatik durduran koruma kuralı etkindir.
- Dönüşüm olayları doğrulanmadan reklam açılmayacaktır.
