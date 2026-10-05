#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meta User Access Token'ını loglamadan uzun ömürlü tokene çevirir."""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.facebook.com/v26.0"


def get(path, params):
    url = API + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            error = (json.loads(raw).get("error") or {})
            message = error.get("message") or f"HTTP {exc.code}"
            code = error.get("code")
            subcode = error.get("error_subcode")
            raise RuntimeError(f"Meta token yenileme başarısız: HTTP {exc.code}, kod {code}/{subcode}: {message[:300]}")
        except json.JSONDecodeError:
            raise RuntimeError(f"Meta token yenileme başarısız: HTTP {exc.code}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    short_token = os.environ["META_USER_TOKEN"].strip()
    app_id = os.environ["META_APP_ID"].strip()
    app_secret = os.environ["META_APP_SECRET"].strip()
    result = get(
        "/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    token = str(result.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Meta uzun ömürlü token döndürmedi")
    # Salt-okunur doğrulama; token hiçbir zaman ekrana yazılmaz.
    profile = get("/me", {"fields": "id,name", "access_token": token})
    if not profile.get("id"):
        raise RuntimeError("Yenilenen Meta tokenı doğrulanamadı")
    out = Path(args.output)
    out.write_text(token, encoding="utf-8")
    os.chmod(out, 0o600)
    expires = result.get("expires_in")
    print(f"Meta token güvenli biçimde yenilendi; expires_in={expires}.")


if __name__ == "__main__":
    main()
