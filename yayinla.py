#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zamanlanmış yayıncı: schedule.json'da bugüne ve bu saate ait işleri yayınlar.
Sadece standart kütüphane kullanır. Sırlar ortam değişkenlerinden okunur."""
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

API = "https://graph.facebook.com/v21.0"
IST = timezone(timedelta(hours=3))

def api(path, params, method="POST", tries=3):
    enc = urllib.parse.urlencode(params).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(API + path, data=enc if method == "POST" else None, method=method)
            url = API + path
            if method == "GET":
                req = urllib.request.Request(url + "?" + enc.decode(), method="GET")
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            print(f"  ⚠️ deneme {t+1}: {e.read().decode()[:200]}")
            time.sleep(15)
    raise SystemExit("API 3 denemede başarısız.")

def slot_bul():
    h = datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60
    # cron saatlerine en yakın slot: 6.0=sabah, 9.5=ogle, 16.5=aksam
    aday = [("sabah", 6.0), ("ogle", 9.5), ("aksam", 16.5)]
    return min(aday, key=lambda x: abs(x[1] - h))[0]

def bugun():
    return datetime.now(IST).strftime("%Y-%m-%d")

def ig_post(cfg, medya, tip, aciklama):
    base = {"access_token": cfg["UT"]}
    if tip == "reels":
        m = api(f"/{cfg['IG']}/media", {**base, "media_type": "REELS", "video_url": medya, "share_to_feed": "true", "caption": aciklama})
        for _ in range(20):
            st = api(f"/{m['id']}/media", {"fields": "status_code", **base}, "GET")
            if st.get("status_code") == "FINISHED":
                break
            time.sleep(15)
        return api(f"/{cfg['IG']}/media_publish", {"creation_id": m["id"], **base})["id"]
    if tip == "story":
        m = api(f"/{cfg['IG']}/media", {**base, "image_url": medya, "media_type": "STORIES"})
        return api(f"/{cfg['IG']}/media_publish", {"creation_id": m["id"], **base})["id"]
    if tip == "carousel":
        ids = [api(f"/{cfg['IG']}/media", {**base, "image_url": u, "is_carousel_item": "true"})["id"] for u in medya]
        m = api(f"/{cfg['IG']}/media", {**base, "media_type": "CAROUSEL", "children": ",".join(ids), "caption": aciklama})
        return api(f"/{cfg['IG']}/media_publish", {"creation_id": m["id"], **base})["id"]
    m = api(f"/{cfg['IG']}/media", {**base, "image_url": medya, "caption": aciklama})
    return api(f"/{cfg['IG']}/media_publish", {"creation_id": m["id"], **base})["id"]

def fb_post(cfg, medya, tip, aciklama):
    base = {"access_token": cfg["PT"]}
    if tip == "reels":
        return api(f"/{cfg['PG']}/videos", {**base, "file_url": medya, "description": aciklama}).get("id")
    if tip == "carousel":
        fbids = [{"media_fbid": api(f"/{cfg['PG']}/photos", {**base, "url": u, "published": "false"})["id"]} for u in medya]
        return api(f"/{cfg['PG']}/feed", {**base, "message": aciklama, "attached_media": json.dumps(fbids)}).get("id")
    return api(f"/{cfg['PG']}/photos", {**base, "url": medya, "caption": aciklama}).get("id")

def main():
    cfg = {"UT": os.environ["META_USER_TOKEN"], "PT": os.environ["META_PAGE_TOKEN"],
           "PG": os.environ["META_PAGE_ID"], "IG": os.environ["META_IG_ID"]}
    repo = os.environ["REPO"]
    gun, slot = bugun(), slot_bul()
    print(f"📅 {gun} | 🕐 slot: {slot}")
    plan = json.load(open("schedule.json", encoding="utf-8"))
    isler = [i for i in plan.get("items", []) if i.get("tarih") == gun and i.get("slot") == slot]
    print(f"Yapılacak iş: {len(isler)}")
    for k in isler:
        med = k["medya"]
        urls = [f"https://cdn.jsdelivr.net/gh/{repo}@main/{m}" for m in (med if isinstance(med, list) else [med])]
        tek = urls[0] if not isinstance(med, list) else urls
        print(f"→ {k['platform']} / {k['tip']}: {k.get('baslik','')}")
        try:
            if k["platform"] == "instagram":
                pid = ig_post(cfg, tek, k["tip"], k["aciklama"])
            else:
                pid = fb_post(cfg, tek, k["tip"], k["aciklama"])
            print(f"  ✅ yayında: {pid}")
        except SystemExit as e:
            print(f"  ❌ başarısız: {e}")
    print("Bitti.")

if __name__ == "__main__":
    main()
