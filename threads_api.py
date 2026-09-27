#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Beyoğlu Nakliyat için resmi Threads API istemcisi.

Token hiçbir zaman loglanmaz. Yayınlama iki aşamalıdır: medya kapsayıcısı oluşturulur,
hazır olması beklenir ve ardından yayınlanır. Bu modül tek başına çalıştırıldığında
yalnızca salt-okunur bağlantı testi yapar; gönderi yayımlamaz.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.threads.com/v1.0"


class ThreadsAPIError(RuntimeError):
    pass


def _safe_error(raw: str, http_code: int) -> str:
    try:
        obj = json.loads(raw)
        err = obj.get("error", obj)
        message = err.get("message") or err.get("error_message") or f"HTTP {http_code}"
        code = err.get("code")
        return f"Threads API HTTP {http_code}" + (f" / kod {code}" if code else "") + f": {str(message)[:400]}"
    except Exception:
        return f"Threads API HTTP {http_code}"


def api(path: str, params: dict | None = None, method: str = "GET", tries: int = 3) -> dict:
    params = params or {}
    encoded = urllib.parse.urlencode(params).encode()
    last = ""
    for attempt in range(1, tries + 1):
        try:
            if method == "GET":
                query = encoded.decode()
                url = API + path + (("?" + query) if query else "")
                req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
            else:
                req = urllib.request.Request(
                    API + path,
                    data=encoded,
                    method=method,
                    headers={"Accept": "application/json"},
                )
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            last = _safe_error(raw, exc.code)
            if exc.code >= 500 and attempt < tries:
                time.sleep(5 * attempt)
                continue
            raise ThreadsAPIError(last)
        except Exception as exc:
            last = f"Threads bağlantı hatası: {type(exc).__name__}"
            if attempt < tries:
                time.sleep(5 * attempt)
                continue
            raise ThreadsAPIError(last)
    raise ThreadsAPIError(last or "Threads API çağrısı başarısız")


def profile(token: str) -> dict:
    return api(
        "/me",
        {
            "fields": "id,username,name,threads_biography,is_verified",
            "access_token": token,
        },
    )


def publishing_limit(token: str, user_id: str) -> dict:
    return api(
        f"/{user_id}/threads_publishing_limit",
        {
            "fields": "quota_usage,config,reply_quota_usage,reply_config",
            "access_token": token,
        },
    )


def insights(token: str, user_id: str) -> dict:
    return api(
        f"/{user_id}/threads_insights",
        {
            "metric": "views,likes,replies,reposts,quotes,clicks",
            "access_token": token,
        },
    )


def recent_posts(token: str, limit: int = 10) -> dict:
    return api(
        "/me/threads",
        {
            "fields": "id,media_type,permalink,username,text,timestamp,shortcode,is_quote_post",
            "limit": str(limit),
            "access_token": token,
        },
    )


def wait_container(token: str, container_id: str, attempts: int = 40) -> None:
    """Threads medya kapsayıcısı hazır olana kadar sınırlı süre bekler."""
    for _ in range(attempts):
        state = api(
            f"/{container_id}",
            {"fields": "status,error_message", "access_token": token},
            tries=2,
        )
        status = str(state.get("status", "")).upper()
        if status in {"FINISHED", "PUBLISHED"}:
            return
        if status in {"ERROR", "EXPIRED"}:
            raise ThreadsAPIError("Threads medya işleme hatası: " + str(state.get("error_message") or status))
        time.sleep(5)
    raise ThreadsAPIError("Threads medya işleme süresi aşıldı")


def _media_type(url: str) -> str:
    clean = urllib.parse.urlparse(url).path.casefold()
    return "VIDEO" if clean.endswith((".mp4", ".mov", ".m4v", ".webm")) else "IMAGE"


def publish(token: str, user_id: str, urls: list[str], kind: str, text: str, alt_texts: list[str] | None = None) -> str:
    """Metin, görsel, video veya carousel Threads gönderisi yayımlar."""
    if len(text.encode("utf-8")) > 500:
        raise ThreadsAPIError("Threads metni 500 UTF-8 bayt sınırını aşıyor")
    alt_texts = alt_texts or []
    base = {"access_token": token}

    if kind == "text" or not urls:
        container = api(f"/{user_id}/threads", {**base, "media_type": "TEXT", "text": text}, "POST")
    elif kind == "carousel":
        if not 2 <= len(urls) <= 20:
            raise ThreadsAPIError("Threads carousel 2–20 medya içermelidir")
        children: list[str] = []
        for index, url in enumerate(urls):
            media_type = _media_type(url)
            params = {
                **base,
                "media_type": media_type,
                "is_carousel_item": "true",
                "video_url" if media_type == "VIDEO" else "image_url": url,
            }
            if index < len(alt_texts) and alt_texts[index]:
                params["alt_text"] = alt_texts[index]
            child = api(f"/{user_id}/threads", params, "POST")
            wait_container(token, child["id"])
            children.append(str(child["id"]))
        container = api(
            f"/{user_id}/threads",
            {**base, "media_type": "CAROUSEL", "children": ",".join(children), "text": text},
            "POST",
        )
    else:
        media_type = "VIDEO" if kind in {"video", "reels"} else "IMAGE"
        params = {
            **base,
            "media_type": media_type,
            "text": text,
            "video_url" if media_type == "VIDEO" else "image_url": urls[0],
        }
        if alt_texts:
            params["alt_text"] = alt_texts[0]
        container = api(f"/{user_id}/threads", params, "POST")

    wait_container(token, str(container["id"]))
    result = api(
        f"/{user_id}/threads_publish",
        {**base, "creation_id": str(container["id"])},
        "POST",
    )
    if not result.get("id"):
        raise ThreadsAPIError("Threads yayın kimliği dönmedi")
    return str(result["id"])


def _local_read_only_test() -> None:
    root = Path(__file__).resolve().parent
    cfg = json.loads((root / "credentials" / "threads-token.json").read_text(encoding="utf-8"))
    p = profile(cfg["access_token"])
    q = publishing_limit(cfg["access_token"], cfg["user_id"])
    print(f"Bağlı Threads profili: @{p.get('username')}")
    usage = ((q.get("data") or [{}])[0]).get("quota_usage")
    print(f"Son 24 saat API yayın kullanımı: {usage}")
    print("Salt-okunur test başarılı; gönderi yayımlanmadı.")


if __name__ == "__main__":
    _local_read_only_test()
