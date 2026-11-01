#!/usr/bin/env python3
import json
from update_page import resolve_tgwsproxy_release

sample = {
    "tag_name": "v1.11.6",
    "html_url": "https://github.com/Regstar2/tg-ws-proxy-android/releases/tag/v1.11.6",
    "assets": [
        {"name":"TgWsProxy-Android-v1.11.6-arm64-v8a.apk.sha256","browser_download_url":"https://example.invalid/hash"},
        {"name":"TgWsProxy-Android-v1.11.6-arm64-v8a.apk","browser_download_url":"https://example.invalid/app.apk"},
    ],
}

def fake_get(url, timeout=25):
    assert url.endswith("/releases/latest")
    return json.dumps(sample)

info = resolve_tgwsproxy_release(fake_get)
assert info["version"] == "v1.11.6", info
assert info["apk_url"] == "https://example.invalid/app.apk", info
assert info["release_url"].endswith("/tag/v1.11.6"), info

def broken_get(url, timeout=25):
    raise OSError("network down")

fallback = resolve_tgwsproxy_release(broken_get)
assert fallback["version"] == "latest", fallback
assert fallback["apk_url"].endswith("/releases/latest"), fallback
assert fallback["release_url"].endswith("/releases/latest"), fallback

print("TgWsProxy release resolver OK")
