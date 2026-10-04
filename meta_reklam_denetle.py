#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meta reklam hesabının salt-okunur, sırsız canlı durum raporu."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://graph.facebook.com/v26.0"
ACCOUNT = "act_1075711764208044"
IST = timezone(timedelta(hours=3))
TOKEN = os.environ["META_USER_TOKEN"]


def get(path, **params):
    params["access_token"] = TOKEN
    url = API + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            error = json.loads(raw).get("error", {})
        except Exception:
            error = {}
        return {
            "_error": {
                "http": exc.code,
                "code": error.get("code"),
                "subcode": error.get("error_subcode"),
                "type": error.get("type"),
                "message": error.get("message") or raw[:300],
            }
        }


def main():
    permissions_raw = get("/me/permissions")
    permissions = sorted(
        item.get("permission")
        for item in permissions_raw.get("data", [])
        if item.get("status") == "granted" and item.get("permission")
    )
    report = {
        "at": datetime.now(IST).isoformat(),
        "account_id": ACCOUNT,
        "granted_permissions": permissions,
        "account": get(
            f"/{ACCOUNT}",
            fields="id,name,account_status,disable_reason,currency,timezone_name,amount_spent,spend_cap,balance",
        ),
        "campaigns": get(
            f"/{ACCOUNT}/campaigns",
            fields="id,name,status,effective_status,objective,daily_budget,lifetime_budget,start_time,stop_time,updated_time",
            limit=100,
        ),
        "adsets": get(
            f"/{ACCOUNT}/adsets",
            fields="id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget,budget_remaining,start_time,end_time,updated_time",
            limit=100,
        ),
        "ads": get(
            f"/{ACCOUNT}/ads",
            fields="id,name,adset_id,campaign_id,status,effective_status,updated_time",
            limit=100,
        ),
        "rules": get(
            f"/{ACCOUNT}/adrules_library",
            fields="id,name,status,schedule_spec,evaluation_spec,execution_spec,created_time,updated_time",
            limit=100,
        ),
        "today_by_campaign": get(
            f"/{ACCOUNT}/insights",
            fields="campaign_id,campaign_name,spend,impressions,reach,clicks,inline_link_clicks,actions,cost_per_action_type",
            date_preset="today",
            level="campaign",
            limit=100,
        ),
        "last_7d_by_campaign": get(
            f"/{ACCOUNT}/insights",
            fields="campaign_id,campaign_name,spend,impressions,reach,clicks,inline_link_clicks,actions,cost_per_action_type",
            date_preset="last_7d",
            level="campaign",
            limit=100,
        ),
    }
    print("META_AD_AUDIT_BEGIN")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("META_AD_AUDIT_END")
    if report["account"].get("_error"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
