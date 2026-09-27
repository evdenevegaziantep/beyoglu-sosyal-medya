#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Threads uzun süreli tokenini yeniler; tokeni ekrana yazmaz."""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Yeni tokenin yazılacağı geçici dosya")
    args = parser.parse_args()
    token = os.environ["THREADS_ACCESS_TOKEN"].strip()
    query = urllib.parse.urlencode({"grant_type": "th_refresh_token", "access_token": token})
    req = urllib.request.Request(
        "https://graph.threads.com/refresh_access_token?" + query,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            obj = json.loads(raw)
            err = obj.get("error", obj)
            message = err.get("message") or err.get("error_message") or f"HTTP {exc.code}"
        except Exception:
            message = f"HTTP {exc.code}"
        raise SystemExit("Threads token yenileme başarısız: " + str(message)[:300])

    new_token = result.get("access_token")
    if not new_token:
        raise SystemExit("Threads yenileme yanıtında token bulunamadı")
    output = Path(args.output)
    output.write_text(new_token, encoding="utf-8")
    output.chmod(0o600)
    print("Threads tokeni başarıyla yenilendi; hassas değer loglanmadı.")
    print("expires_in=" + str(result.get("expires_in", "bilinmiyor")))


if __name__ == "__main__":
    main()
