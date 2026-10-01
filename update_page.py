#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
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
TIMEOUT = 3.0
UA = "Mozilla/5.0 MTProtoProxyPage/2.1"

PRIMARY_SOURCE = "https://zakky8.github.io/mtproto-proxy-pro/censorship_resistant.txt"
FALLBACK_SOURCES = [
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
                out.append({
                    "url": url,
                    "tg_url": "tg://proxy?" + urllib.parse.urlsplit(url).query,
                    "server": server,
                    "port": port,
                    "secret": secret,
                })
            except Exception:
                pass
    return out

def check_twice(p):
    timings = []
    for attempt in range(2):
        start = time.perf_counter()
        try:
            with socket.create_connection((p["server"], p["port"]), timeout=TIMEOUT):
                timings.append(int((time.perf_counter() - start) * 1000))
        except Exception:
            return p, None
        if attempt == 0:
            time.sleep(0.35)
    return p, round(sum(timings) / len(timings))

def get_candidates():
    try:
        primary = extract_links(http_get(PRIMARY_SOURCE))
        strict = [p for p in primary if p["port"] == 443 and p["secret"].lower().startswith("ee")]
        if strict:
            return strict, "FakeTLS / 443"
        if primary:
            return primary, "основной список"
    except Exception as e:
        print("primary source failed:", e)

    merged, seen = [], set()
    for src in FALLBACK_SOURCES:
        try:
            for p in extract_links(http_get(src)):
                key = (p["server"].lower(), p["port"], p["secret"])
                if key not in seen:
                    seen.add(key)
                    merged.append(p)
        except Exception as e:
            print("fallback source failed:", src, e)
    return merged, "резервный список"

def proxy_id(p):
    raw = f"{p['server'].lower()}|{p['port']}|{p['secret']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]

def short_name(server):
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", server):
        parts = server.split(".")
        return ".".join(parts[-2:])
    return server[:24]

def main():
    items, mode = get_candidates()

    probe = items[:60]
    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(check_twice, p): i for i, p in enumerate(probe)}
        for f in as_completed(futures):
            idx = futures[f]
            p, ms = f.result()
            if ms is not None:
                results[idx] = (p, ms)

    chosen = [results[i] for i in range(len(probe)) if i in results][:COUNT]

    tz = timezone(timedelta(hours=3))
    updated = datetime.now(tz).strftime("%d.%m.%Y %H:%M UTC+3")

    cards = []
    for i, (p, ms) in enumerate(chosen, 1):
        pid = proxy_id(p)
        label = short_name(p["server"])
        cards.append(f"""
        <div class="card" data-proxy-id="{pid}">
          <div class="topline">
            <div><b>Прокси {i}</b> <span class="code">#{pid}</span></div>
            <div class="vote-status" id="status-{pid}"></div>
          </div>
          <div class="small">{html.escape(p['server'])}:{p['port']} · повторная проверка {ms} мс</div>
          <div class="actions">
            <a class="btn connect" href="{html.escape(p['tg_url'], quote=True)}">Открыть в Telegram</a>
            <button class="btn good" onclick="rateProxy('{pid}','good','{html.escape(label, quote=True)}')">✅ Работает</button>
            <button class="btn bad" onclick="rateProxy('{pid}','bad','{html.escape(label, quote=True)}')">❌ Не работает</button>
          </div>
        </div>
        """)

    if not cards:
        cards = ['<div class="card">Сейчас не удалось найти прокси, прошедшие повторную проверку. Попробуй позже.</div>']

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
    .topline{{display:flex;justify-content:space-between;gap:12px;align-items:center}}
    .code{{font-size:12px;color:#777;font-weight:400}}
    .actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
    .btn{{border:0;display:inline-block;padding:11px 14px;border-radius:10px;color:#fff;text-decoration:none;font-weight:700;font-size:14px;cursor:pointer}}
    .connect{{background:#229ed9}}
    .good{{background:#2e9d53}}
    .bad{{background:#c64747}}
    .small{{font-size:14px;color:#666;margin-top:5px}}
    .vote-status{{font-size:12px;font-weight:700;white-space:nowrap}}
    .saved-good{{color:#2e9d53}}
    .saved-bad{{color:#c64747}}
    .note{{font-size:13px;color:#666;margin-top:20px;line-height:1.4}}
  </style>
</head>
<body>
  <h1>Свежие MTProto-прокси</h1>
  <div class="meta">Обновлено: {updated} · режим: {html.escape(mode)}</div>
  {''.join(cards)}
  <div class="note">Тестовый режим: кнопки «Работает / Не работает» сохраняют твою оценку прямо в браузере на этом устройстве. Позже подключим общую историю, чтобы рейтинг влиял на будущий отбор прокси.</div>

<script>
function keyFor(id) {{ return 'proxy-rating-' + id; }}

function paint(id, value) {{
  const el = document.getElementById('status-' + id);
  if (!el) return;
  if (value === 'good') {{
    el.textContent = '✓ отмечен рабочим';
    el.className = 'vote-status saved-good';
  }} else if (value === 'bad') {{
    el.textContent = '✕ отмечен нерабочим';
    el.className = 'vote-status saved-bad';
  }} else {{
    el.textContent = '';
    el.className = 'vote-status';
  }}
}}

function rateProxy(id, value, label) {{
  const item = {{
    proxy_id: id,
    result: value,
    label: label,
    saved_at: new Date().toISOString()
  }};
  localStorage.setItem(keyFor(id), JSON.stringify(item));
  paint(id, value);
}}

document.querySelectorAll('[data-proxy-id]').forEach(card => {{
  const id = card.dataset.proxyId;
  try {{
    const raw = localStorage.getItem(keyFor(id));
    if (raw) {{
      const item = JSON.parse(raw);
      paint(id, item.result);
    }}
  }} catch (e) {{}}
}});
</script>
</body>
</html>"""

    Path("index.html").write_text(page, encoding="utf-8")

if __name__ == "__main__":
    main()
