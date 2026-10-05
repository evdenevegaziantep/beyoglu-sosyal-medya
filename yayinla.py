#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Beyoğlu sosyal medya zamanlayıcısı.

schedule.json içindeki `program` kayıtlarını İstanbul saatine göre Facebook ve
Instagram'da yayınlar. published.json ile aynı içeriğin yeniden yayınlanmasını
engeller. GitHub Actions manuel çalıştırmada FORCE_IDS ile kaçırılan kayıtlar
sonradan yayınlanabilir.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from threads_api import publish as threads_publish

API = "https://graph.facebook.com/v26.0"
IST = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent
SCHEDULE = ROOT / "schedule.json"
STATE = ROOT / "published.json"


def api(path, params, method="POST", tries=3):
    encoded = urllib.parse.urlencode(params).encode()
    last = ""
    for attempt in range(1, tries + 1):
        try:
            if method == "GET":
                req = urllib.request.Request(API + path + "?" + encoded.decode(), method="GET")
            else:
                req = urllib.request.Request(API + path, data=encoded, method=method)
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last = exc.read().decode()
            print(f"  ⚠️ API denemesi {attempt}/{tries}: HTTP {exc.code} — {last[:350]}")
            try:
                error_code = (json.loads(last).get("error") or {}).get("code")
            except Exception:
                error_code = None
            # Geçersiz/süresi dolmuş token yeniden denemeyle düzelmez; hızlı ve
            # açık hata vererek her platform için gereksiz 24 saniyeyi önle.
            if error_code == 190:
                raise RuntimeError(last or "Meta erişim tokenı geçersiz veya süresi dolmuş")
            if attempt < tries:
                time.sleep(8 * attempt)
    raise RuntimeError(last or "Meta API üç denemede başarısız")


def today():
    return datetime.now(IST).strftime("%Y-%m-%d")


def current_slot():
    # Cronlar UTC 06:00 / 09:30 / 16:30; gecikme olsa da en yakın slot seçilir.
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60
    slots = [("sabah", 6.0), ("ogle", 9.5), ("aksam", 16.5)]
    return min(slots, key=lambda item: abs(item[1] - hour))[0]


def media_url(repo, filename):
    path = "medya/" + filename.lstrip("/")
    return "https://raw.githubusercontent.com/" + repo + "/main/" + urllib.parse.quote(path, safe="/")


def wait_ig_container(token, creation_id, limit=40):
    for _ in range(limit):
        status = api(f"/{creation_id}", {"fields": "status_code,status", "access_token": token}, "GET")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram medya işleme hatası: {status}")
        time.sleep(10)
    raise RuntimeError("Instagram medya işleme süresi aşıldı")


def instagram_post(cfg, urls, kind, caption, alt_texts=None):
    token = cfg["UT"]
    base = {"access_token": token}
    alt_texts = alt_texts or []
    if kind == "carousel":
        children = []
        for index, url in enumerate(urls):
            params = {**base, "image_url": url, "is_carousel_item": "true"}
            if index < len(alt_texts) and alt_texts[index]:
                params["alt_text"] = alt_texts[index]
            item = api(f"/{cfg['IG']}/media", params)
            children.append(item["id"])
        container = api(
            f"/{cfg['IG']}/media",
            {**base, "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
        )
        wait_ig_container(token, container["id"])
        return api(f"/{cfg['IG']}/media_publish", {**base, "creation_id": container["id"]})["id"]

    if kind == "video":
        container = api(
            f"/{cfg['IG']}/media",
            {**base, "media_type": "REELS", "video_url": urls[0], "share_to_feed": "true", "caption": caption},
        )
        wait_ig_container(token, container["id"])
        return api(f"/{cfg['IG']}/media_publish", {**base, "creation_id": container["id"]})["id"]

    if kind == "story":
        container = api(f"/{cfg['IG']}/media", {**base, "media_type": "STORIES", "image_url": urls[0]})
        wait_ig_container(token, container["id"])
        return api(f"/{cfg['IG']}/media_publish", {**base, "creation_id": container["id"]})["id"]

    params = {**base, "image_url": urls[0], "caption": caption}
    if alt_texts and alt_texts[0]:
        params["alt_text"] = alt_texts[0]
    container = api(f"/{cfg['IG']}/media", params)
    wait_ig_container(token, container["id"])
    return api(f"/{cfg['IG']}/media_publish", {**base, "creation_id": container["id"]})["id"]


def resolve_page_token(cfg):
    """Kullanıcı tokenından doğru Page Access Token'ı güvenli biçimde türetir.

    GitHub secret içindeki kullanıcı tokenı loglara yazılmaz. Böylece kullanıcıdan
    Page Token'ı ayırt edip ayrıca kopyalaması beklenmez; token yalnızca bu çalışma
    sürecinin belleğinde tutulur.
    """
    cached = cfg.get("_RESOLVED_PT")
    if cached:
        return cached

    try:
        response = api(
            "/me/accounts",
            {
                "fields": "id,name,access_token",
                "access_token": cfg["UT"],
            },
            "GET",
            tries=1,
        )
        for page in response.get("data", []):
            if str(page.get("id")) == str(cfg["PG"]) and page.get("access_token"):
                cfg["_RESOLVED_PT"] = page["access_token"]
                print("  🔐 Sayfa tokenı kullanıcı tokenından güvenli biçimde türetildi.")
                return cfg["_RESOLVED_PT"]
    except Exception as exc:
        print(f"  ⚠️ Sayfa tokenı otomatik türetilemedi: {exc}")

    # Geriye dönük uyumluluk: doğru bir META_PAGE_TOKEN zaten kayıtlıysa onu kullan.
    if cfg.get("PT"):
        print("  ⚠️ GitHub'da kayıtlı META_PAGE_TOKEN kullanılacak.")
        return cfg["PT"]
    raise RuntimeError("Beyoğlu Facebook Sayfası için Page Access Token alınamadı")


def facebook_post(cfg, urls, kind, caption):
    base = {"access_token": resolve_page_token(cfg)}
    if kind == "video":
        return api(f"/{cfg['PG']}/videos", {**base, "file_url": urls[0], "description": caption}).get("id")

    if kind == "carousel":
        attached = []
        for url in urls:
            photo = api(f"/{cfg['PG']}/photos", {**base, "url": url, "published": "false"})
            attached.append({"media_fbid": photo["id"]})
        return api(
            f"/{cfg['PG']}/feed",
            {**base, "message": caption, "attached_media": json.dumps(attached, separators=(",", ":"))},
        ).get("id")

    if kind == "story":
        photo = api(f"/{cfg['PG']}/photos", {**base, "url": urls[0], "published": "false"})
        return api(f"/{cfg['PG']}/photo_stories", {**base, "photo_id": photo["id"]}).get("post_id", photo["id"])

    result = api(f"/{cfg['PG']}/photos", {**base, "url": urls[0], "caption": caption})
    return result.get("post_id") or result.get("id")


def caption_for(item, platform):
    """Programdaki kısa ve uzun platform anahtarlarını birlikte destekler."""
    caption_data = item.get("aciklama", {})
    if not isinstance(caption_data, dict):
        return str(caption_data)
    aliases = {"instagram": "ig", "facebook": "fb", "threads": "threads"}
    return str(caption_data.get(platform) or caption_data.get(aliases.get(platform, "")) or "").strip()


def trim_utf8(text, max_bytes):
    """Unicode karakterlerini bölmeden UTF-8 bayt sınırına indirir."""
    text = text.strip()
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    suffix = "…"
    while text and len((text.rstrip() + suffix).encode("utf-8")) > max_bytes:
        text = text[:-1]
    return text.rstrip(" ,.;:-") + suffix


def threads_caption_for(item):
    """Açıkça yazılmış Threads metnini veya IG metninden güvenli kısa sürümü döndürür."""
    explicit = caption_for(item, "threads")
    if explicit:
        if len(explicit.encode("utf-8")) > 500:
            raise RuntimeError("Threads açıklaması 500 UTF-8 bayt sınırını aşıyor")
        return explicit

    source = caption_for(item, "instagram")
    blocks = []
    for block in source.split("\n\n"):
        folded = block.casefold()
        if not block.strip() or block.lstrip().startswith("#"):
            continue
        if any(mark in folded for mark in ("0546 112 27 97", "evdenevegaziantep.com", "whatsapp:", "profilimizdeki bağlantı")):
            continue
        blocks.append(block.strip())
        if len(blocks) == 2:
            break

    target = str(item.get("hedef_url") or "https://www.evdenevegaziantep.com/")
    parts = urllib.parse.urlsplit(target)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query.update({"utm_source": "threads", "utm_medium": "organic_social", "utm_campaign": "threads"})
    tracked = urllib.parse.urlunsplit((parts.scheme or "https", parts.netloc or "www.evdenevegaziantep.com", parts.path or "/", urllib.parse.urlencode(query), ""))
    footer = f"\n\n📞 0546 112 27 97\n🌐 {tracked}"
    body = trim_utf8("\n\n".join(blocks) or str(item.get("baslik", {}).get("ig", "Beyoğlu Nakliyat — Gaziantep")), 500 - len(footer.encode("utf-8")))
    return body + footer


def validate_caption(item, platform, caption):
    """Örnek/eksik açıklamaların canlıya çıkmasını engeller."""
    normalized = caption.casefold()
    forbidden = ("ornek -", "örnek -", "kurulumda doldurulacak", "placeholder", "todo:", "todo ")
    if any(word in normalized for word in forbidden):
        raise RuntimeError("örnek veya tamamlanmamış açıklama engellendi")
    # Hikâyelerde Instagram/Facebook API açıklama alanı göstermediği için iletişim
    # bilgileri hikâye görselinin içinde yer alır.
    if item.get("tip") != "story":
        missing = []
        if "0546 112 27 97" not in caption:
            missing.append("telefon")
        if "evdenevegaziantep.com" not in normalized:
            missing.append("site")
        if missing:
            raise RuntimeError("açıklamada zorunlu iletişim bilgisi eksik: " + ", ".join(missing))


def validate_seo_media(item, urls, alt_texts):
    """SEO işaretli görsel gönderilerinde açıklayıcı alternatif metni zorunlu tutar."""
    if not item.get("seo_uyumlu") or item.get("tip") not in {"post", "carousel"}:
        return
    if len(alt_texts) != len(urls) or any(not str(text).strip() for text in alt_texts):
        raise RuntimeError("SEO görsel alternatif metni eksik")
    if any(len(str(text)) > 1000 for text in alt_texts):
        raise RuntimeError("SEO görsel alternatif metni 1000 karakter sınırını aşıyor")


def load_state():
    if not STATE.exists():
        return {"published": {}}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save(plan, state):
    SCHEDULE.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    cfg = {
        "UT": os.environ["META_USER_TOKEN"],
        "PT": os.environ["META_PAGE_TOKEN"],
        "PG": os.environ["META_PAGE_ID"],
        "IG": os.environ["META_IG_ID"],
        "TT": os.environ.get("THREADS_ACCESS_TOKEN", ""),
        "TUID": os.environ.get("THREADS_USER_ID", ""),
    }
    repo = os.environ["REPO"]
    plan = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    state = load_state()
    published = state.setdefault("published", {})

    force_ids = {x.strip() for x in os.environ.get("FORCE_IDS", "").split(",") if x.strip()}
    force_platforms = {
        x.strip().casefold()
        for x in os.environ.get("FORCE_PLATFORMS", "").split(",")
        if x.strip()
    }
    force_republish = os.environ.get("FORCE_REPUBLISH") == "1"
    run_date = os.environ.get("FORCE_DATE") or today()
    slot = os.environ.get("FORCE_SLOT") or current_slot()
    program = plan.get("program", [])

    if force_ids:
        jobs = [x for x in program if x.get("id") in force_ids]
    else:
        jobs = [x for x in program if x.get("tarih") == run_date and x.get("slot") == slot]

    print(
        f"📅 {run_date} | 🕐 {slot} | işler: {len(jobs)} | "
        f"zorla: {sorted(force_ids)} | platform filtresi: {sorted(force_platforms)}"
    )
    failures = []

    for item in jobs:
        item_id = item["id"]
        urls = [media_url(repo, name) for name in item.get("dosyalar", [])]
        if not urls:
            failures.append(f"{item_id}: medya yok")
            continue
        alt_texts = item.get("alternatif_metinler", [])
        if not isinstance(alt_texts, list):
            alt_texts = []
        for platform in item.get("platformlar", []):
            if force_platforms and platform.casefold() not in force_platforms:
                print(f"↪️ platform filtresiyle atlandı: {item_id}:{platform}")
                continue
            key = f"{item_id}:{platform}"
            if key in published and not force_republish:
                print(f"↪️ zaten yayınlandı: {key} → {published[key].get('post_id')}")
                continue
            caption = threads_caption_for(item) if platform == "threads" else caption_for(item, platform)
            print(f"→ {key} / {item.get('tip')}")
            try:
                validate_caption(item, platform, caption)
                if platform == "instagram":
                    validate_seo_media(item, urls, alt_texts)
                    post_id = instagram_post(cfg, urls, item["tip"], caption, alt_texts)
                elif platform == "facebook":
                    post_id = facebook_post(cfg, urls, item["tip"], caption)
                elif platform == "threads":
                    if not cfg["TT"] or not cfg["TUID"]:
                        raise RuntimeError("Threads GitHub sırları eksik")
                    if item.get("tip") == "story":
                        raise RuntimeError("Threads hikâye biçimini desteklemiyor")
                    post_id = threads_publish(cfg["TT"], cfg["TUID"], urls, item["tip"], caption, alt_texts)
                else:
                    raise RuntimeError(f"Bilinmeyen platform: {platform}")
                published[key] = {"post_id": str(post_id), "published_at": datetime.now(IST).isoformat()}
                print(f"  ✅ yayınlandı: {post_id}")
            except Exception as exc:
                failures.append(f"{key}: {exc}")
                print(f"  ❌ {key}: {exc}")

        wanted = {f"{item_id}:{p}" for p in item.get("platformlar", [])}
        item["yayinlandi"] = bool(wanted) and wanted.issubset(published)

    save(plan, state)
    if failures:
        print("\nBAŞARISIZ İŞLER:")
        for failure in failures:
            print("-", failure)
        raise SystemExit(1)
    print("Bitti.")


if __name__ == "__main__":
    main()
