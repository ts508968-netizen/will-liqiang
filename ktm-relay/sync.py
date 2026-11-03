import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml


HOSTS = ("ktm01.com", "ktmcloud.cc")
PROBE_URL = "https://www.youtube.com/generate_204"
DOMESTIC = re.compile(
    r"香港|中国|澳门|澳門|台湾|臺灣|🇭🇰|🇨🇳|🇲🇴|🇹🇼|"
    r"hong[ -]?kong|mainland|macau|macao|taiwan|"
    r"(?<![a-z])(?:hk|hkg|cn|chn|mo|mac|tw|twn)(?![a-z0-9])",
    re.IGNORECASE,
)


def request(url, *, data=None, headers=None, limit=2_000_000):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=25) as response:
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("response_too_large")
        return response.status, body


def fetch_subscription(email, password):
    for host in HOSTS:
        try:
            payload = urllib.parse.urlencode({"email": email, "password": password}).encode()
            _, body = request(
                f"https://{host}/api/v1/passport/auth/login",
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0",
                },
            )
            auth = json.loads(body).get("data", {}).get("auth_data")
            if not isinstance(auth, str) or not auth:
                print(f"{host}: login response invalid")
                continue
            _, body = request(
                f"https://{host}/api/v1/user/getSubscribe",
                headers={"Authorization": auth, "User-Agent": "Mozilla/5.0"},
            )
            subscription_url = json.loads(body).get("data", {}).get("subscribe_url")
            if not isinstance(subscription_url, str) or not subscription_url.startswith("https://"):
                print(f"{host}: subscription URL unavailable")
                continue
            _, body = request(subscription_url, headers={"User-Agent": "Clash.Meta"})
            print(f"{host}: subscription downloaded")
            return body
        except Exception as error:
            print(f"{host}: {type(error).__name__}")
    raise RuntimeError("all KTM hosts failed")


def build_config(body):
    source = yaml.safe_load(body)
    if not isinstance(source, dict) or not isinstance(source.get("proxies"), list):
        raise ValueError("subscription is not a Clash proxy list")
    if source.get("proxy-providers"):
        raise ValueError("proxy providers require separate filtering")
    original = source["proxies"]
    kept = [
        proxy
        for proxy in original
        if isinstance(proxy, dict)
        and isinstance(proxy.get("name"), str)
        and not DOMESTIC.search(proxy["name"])
    ]
    if not kept:
        raise ValueError("no eligible foreign nodes")
    names = [proxy["name"] for proxy in kept]
    if len(names) != len(set(names)):
        raise ValueError("duplicate proxy names")
    config = {
        "proxies": kept,
        "proxy-groups": [
            {
                "name": "Auto-Foreign",
                "type": "url-test",
                "proxies": names,
                "url": PROBE_URL,
                "interval": 300,
                "tolerance": 100,
                "lazy": False,
            }
        ],
        "rules": ["MATCH,Auto-Foreign"],
    }
    output = yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode()
    print(f"nodes_total={len(original)} nodes_kept={len(kept)} nodes_removed={len(original)-len(kept)}")
    return output


def main():
    email = os.environ["KTM_EMAIL"]
    password = os.environ["KTM_PASSWORD"]
    relay_url = os.environ["KTM_RELAY_URL"].rstrip("/") + "/subscription"
    write_token = os.environ["KTM_WRITE_TOKEN"]
    body = build_config(fetch_subscription(email, password))
    status, _ = request(
        relay_url,
        data=body,
        headers={
            "Authorization": f"Bearer {write_token}",
            "Content-Type": "text/yaml",
        },
    )
    if status != 200:
        raise RuntimeError("relay rejected update")
    print("relay_update_ok=True")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"sync_failed={type(error).__name__}", file=sys.stderr)
        sys.exit(1)
