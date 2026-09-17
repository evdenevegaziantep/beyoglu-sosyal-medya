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


def instagram_post(cfg, urls, kind, caption):
    token = cfg["UT"]
    base = {"access_token": token}
    if kind == "carousel":
        children = []
        for url in urls:
            item = api(f"/{cfg['IG']}/media", {**base, "image_url": url, "is_carousel_item": "true"})
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

    container = api(f"/{cfg['IG']}/media", {**base, "image_url": urls[0], "caption": caption})
    wait_ig_container(token, container["id"])
    return api(f"/{cfg['IG']}/media_publish", {**base, "creation_id": container["id"]})["id"]


def facebook_post(cfg, urls, kind, caption):
    base = {"access_token": cfg["PT"]}
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
    """Programdaki kısa (ig/fb) ve uzun platform anahtarlarını birlikte destekler."""
    caption_data = item.get("aciklama", {})
    if not isinstance(caption_data, dict):
        return str(caption_data)
    aliases = {"instagram": "ig", "facebook": "fb"}
    return str(caption_data.get(platform) or caption_data.get(aliases.get(platform, "")) or "").strip()


def validate_caption(item, platform, caption):
    """Örnek/eksik açıklamaların canlıya çıkmasını engeller."""
    normalized = caption.casefold()
    forbidden = ("ornek", "örnek", "kurulumda doldurulacak", "placeholder", "todo")
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
    }
    repo = os.environ["REPO"]
    plan = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    state = load_state()
    published = state.setdefault("published", {})

    force_ids = {x.strip() for x in os.environ.get("FORCE_IDS", "").split(",") if x.strip()}
    force_republish = os.environ.get("FORCE_REPUBLISH") == "1"
    run_date = os.environ.get("FORCE_DATE") or today()
    slot = os.environ.get("FORCE_SLOT") or current_slot()
    program = plan.get("program", [])

    if force_ids:
        jobs = [x for x in program if x.get("id") in force_ids]
    else:
        jobs = [x for x in program if x.get("tarih") == run_date and x.get("slot") == slot]

    print(f"📅 {run_date} | 🕐 {slot} | işler: {len(jobs)} | zorla: {sorted(force_ids)}")
    failures = []

    for item in jobs:
        item_id = item["id"]
        urls = [media_url(repo, name) for name in item.get("dosyalar", [])]
        if not urls:
            failures.append(f"{item_id}: medya yok")
            continue
        for platform in item.get("platformlar", []):
            key = f"{item_id}:{platform}"
            if key in published and not force_republish:
                print(f"↪️ zaten yayınlandı: {key} → {published[key].get('post_id')}")
                continue
            caption = caption_for(item, platform)
            print(f"→ {key} / {item.get('tip')}")
            try:
                validate_caption(item, platform, caption)
                if platform == "instagram":
                    post_id = instagram_post(cfg, urls, item["tip"], caption)
                elif platform == "facebook":
                    post_id = facebook_post(cfg, urls, item["tip"], caption)
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
