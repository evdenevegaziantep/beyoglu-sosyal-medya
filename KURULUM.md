# ⏰ Zamanlanmış Yayın Kurulumu (bir kezlik, ~15 dk)

Bu kurulum bitince: asistanın içeriği hazırlar + sıraya koyar,
saati gelince GitHub otomatik yayınlar. Sana dokunmak kalmaz.

## Adım 1 — GitHub hesabı (3 dk)
1. `github.com` → Sign up (ücretsiz) → e-posta ile kaydol
2. Giriş yap

## Adım 2 — Depo (repo) aç (2 dk)
1. Sağ üst **+** → **New repository**
2. İsim: `beyoglu-sosyal-medya`
3. **Public** seç (görsellerin herkese açık linki için şart — zaten paylaşılacak postlar)
4. **Create repository**

## Adım 3 — Dosyaları yükle (3 dk)
1. Asistanın verdiği `github-repo` klasöründeki TÜM dosyaları
   repo sayfasına sürükle-bırak ile yükle (veya "uploading an existing file")
2. Dosyaların yerinde olduğunu kontrol et: `yayinla.py`, `schedule.json`,
   `.github/workflows/yayinla.yml`, `medya/OKU.md`

## Adım 4 — 4 gizli anahtar (5 dk) — değerleri asistandan al
1. Repo sayfası → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** ile şunları tek tek ekle:
   - `META_USER_TOKEN` → (asistan verecek)
   - `META_PAGE_TOKEN` → (asistan verecek)
   - `META_PAGE_ID` → (asistan verecek)
   - `META_IG_ID` → (asistan verecek)

## Adım 5 — Test (1 dk)
1. Repo → **Actions** sekmesi → "I understand my workflows..." → **Enable**
2. Soldan **Otomatik Yayın** → **Run workflow** → çalıştı
3. Yeşil tik ✅ = sistem hazır

## Adım 6 — Asistana yükleme yetkisi (2 dk, son!)
1. GitHub sağ üst profil → **Settings** → en altta **Developer settings**
2. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
3. İsim: `beyoglu-yukleyici` → Expiration: 1 yıl
4. **Repository access** → Only select repositories → `beyoglu-sosyal-medya` seç
5. **Permissions** → Contents → **Read and write** → Generate
6. Çıkan `github_pat_...` kodunu asistana yapıştır

BİTTİ 🎉 Artık asistan içeriği üretip sıraya koyar, saati gelince otomatik yayınlanır.
