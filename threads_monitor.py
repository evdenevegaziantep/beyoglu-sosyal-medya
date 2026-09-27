#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Threads profilini, gönderileri, yanıtları ve içgörüleri salt-okunur izler."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.threads.com/v1.0"
ROOT = Path(__file__).resolve().parent


def api(path, params):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(API + path + "?" + query, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            error = json.loads(raw).get("error", {})
            message = error.get("message") or error.get("error_message") or f"HTTP {exc.code}"
        except Exception:
            message = f"HTTP {exc.code}"
        return {"error": {"http": exc.code, "message": str(message)[:300]}}


def value_for(insight):
    if "total_value" in insight:
        return insight["total_value"].get("value", 0)
    if "values" in insight:
        return sum(x.get("value", 0) or 0 for x in insight["values"])
    return insight.get("link_total_values", [])


def main():
    token = os.environ["THREADS_ACCESS_TOKEN"]
    user_id = os.environ["THREADS_USER_ID"]
    profile = api("/me", {"fields": "id,username,name,threads_biography,is_verified", "access_token": token})
    posts = api(
        "/me/threads",
        {
            "fields": "id,media_type,permalink,username,text,timestamp,shortcode",
            "limit": "20",
            "access_token": token,
        },
    )
    account_insights = api(
        f"/{user_id}/threads_insights",
        {"metric": "views,likes,replies,reposts,quotes,clicks,followers_count", "access_token": token},
    )
    quota = api(
        f"/{user_id}/threads_publishing_limit",
        {"fields": "quota_usage,config,reply_quota_usage,reply_config", "access_token": token},
    )

    post_reports = []
    total_replies = 0
    for post in posts.get("data", []):
        post_id = post["id"]
        post_insights = api(
            f"/{post_id}/insights",
            {"metric": "views,likes,replies,reposts,quotes,shares", "access_token": token},
        )
        replies = api(
            f"/{post_id}/replies",
            {
                "fields": "id,username,text,timestamp,hide_status,is_reply",
                "limit": "50",
                "access_token": token,
            },
        )
        reply_data = replies.get("data", [])
        total_replies += len(reply_data)
        post_reports.append(
            {
                **post,
                "metrics": {x.get("name"): value_for(x) for x in post_insights.get("data", [])},
                "replies": reply_data,
                "replies_error": replies.get("error"),
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "account_metrics": {x.get("name"): value_for(x) for x in account_insights.get("data", [])},
        "publishing_limit": quota.get("data", []),
        "post_count_read": len(post_reports),
        "reply_count_read": total_replies,
        "posts": post_reports,
        "errors": {
            "posts": posts.get("error"),
            "account_insights": account_insights.get("error"),
            "quota": quota.get("error"),
        },
    }
    output = Path(os.environ.get("THREADS_REPORT_PATH", str(ROOT / "raporlar" / "threads-son-durum.json")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Threads izleme tamamlandı: {len(post_reports)} gönderi, {total_replies} yanıt.")
    print("Hassas token rapora veya loga yazılmadı.")


if __name__ == "__main__":
    main()
