#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html
import re
import socket
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

COUNT = 5
TIMEOUT = 2.5
UA = "Mozilla/5.0 MTProtoProxyPage/1.0"

SOURCES = [
    "https://raw.githubusercontent.com/aviamastersgh/mtproto-free-russia/main/verified_proxies.txt",
    "https://raw.githubusercontent.com/tgmtproxy/telegram-mtproto-proxy-list/main/proxies.txt",
]

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def normalize_proxy_url(url):
    url = url.strip().rstrip(".,);]>'\"")
    if url.startswith("tg://proxy?"):
        return "https://t.me/proxy?" + urllib.parse.urlsplit(url).query
    if url.startswith("https://t.me/proxy?") or url.startswith("http://t.me/proxy?"):
        return "https://t.me/proxy?" + urllib.parse.urlsplit(url).query
    return None

def extract_links(text):
    pats = [
        r'https?://t\.me/proxy\?[^\s<>"\']+',
        r'tg://proxy\?[^\s<>"\']+',
    ]
    out, seen = [], set()
    for pat in pats:
        for m in re.finditer(pat, text, re.I):
            url = normalize_proxy_url(m.group(0))
            if not url:
                continue
            try:
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                server = q.get("server", [""])[0]
                port = int(q.get("port", ["0"])[0])
                secret = q.get("secret", [""])[0]
                if not server or not port or not secret:
                    continue
                key = (server.lower(), port, secret)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"url": url, "server": server, "port": port})
            except Exception:
                pass
    return out

def check(p):
    start = time.perf_counter()
    try:
        with socket.create_connection((p["server"], p["port"]), timeout=TIMEOUT):
            return p, int((time.perf_counter() - start) * 1000)
    except Exception:
        return p, None

def main():
    items, seen = [], set()
    for src in SOURCES:
        try:
            txt = http_get(src)
            for p in extract_links(txt):
                key = (p["server"].lower(), p["port"], p["url"])
                if key not in seen:
                    seen.add(key)
                    items.append(p)
        except Exception as e:
            print("source failed:", src, e)

    alive = []
    with ThreadPoolExecutor(max_workers=24) as ex:
        futures = [ex.submit(check, p) for p in items[:200]]
        for f in as_completed(futures):
            p, ms = f.result()
            if ms is not None:
                alive.append((ms, p))

    alive.sort(key=lambda x: x[0])
    chosen = alive[:COUNT]

    tz = timezone(timedelta(hours=3))
    updated = datetime.now(tz).strftime("%d.%m.%Y %H:%M UTC+3")

    cards = []
    for i, (ms, p) in enumerate(chosen, 1):
        cards.append(f"""
        <div class="card">
          <div><b>Прокси {i}</b></div>
          <div class="small">{html.escape(p['server'])}:{p['port']} · {ms} мс</div>
          <a class="btn" href="{html.escape(p['url'], quote=True)}">Подключить в Telegram</a>
        </div>
        """)

    if not cards:
        cards = ['<div class="card">Сейчас не удалось найти рабочие прокси. Попробуй позже.</div>']

    page = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Свежие MTProto прокси</title>
  <style>
    body{{font-family:Arial,sans-serif;max-width:720px;margin:0 auto;padding:24px;background:#f5f5f5;color:#222}}
    h1{{font-size:28px;margin-bottom:8px}}
    .meta{{color:#666;margin-bottom:20px}}
    .card{{background:#fff;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
    .btn{{display:inline-block;margin-top:10px;padding:12px 16px;border-radius:10px;background:#229ed9;color:#fff;text-decoration:none;font-weight:700}}
    .small{{font-size:14px;color:#666}}
  </style>
</head>
<body>
  <h1>Свежие MTProto-прокси</h1>
  <div class="meta">Обновлено: {updated}</div>
  {''.join(cards)}
  <div class="small" style="margin-top:20px">Публичные прокси могут перестать работать в любой момент. Страница обновляется ежедневно.</div>
</body>
</html>"""

    Path("index.html").write_text(page, encoding="utf-8")

if __name__ == "__main__":
    main()
