#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import html
import json
import socket
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

COUNT = 5
TIMEOUT = 3.0
MIN_UPTIME = 60.0
UA = "Mozilla/5.0 MTProtoProxyPage/3.0"
JSON_SOURCE = "https://zakky8.github.io/mtproto-proxy-pro/proxies.json"


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def normalize_row(row):
    server = str(row.get("server") or "").strip()
    try:
        port = int(row.get("port") or 0)
    except Exception:
        port = 0
    secret = str(row.get("secret") or "").strip()
    if not server or not port or not secret:
        return None

    reachable = row.get("reachable_from") or []
    if isinstance(reachable, str):
        reachable = [reachable]
    reachable = [str(x).upper() for x in reachable]

    status = str(row.get("status") or "").lower()
    ptype = str(row.get("type") or "").lower()

    try:
        uptime = float(row.get("uptime_pct") or 0)
    except Exception:
        uptime = 0.0
    try:
        latency = float(row.get("latency_ms") or 999999)
    except Exception:
        latency = 999999.0

    qs = urllib.parse.urlencode({"server": server, "port": port, "secret": secret})
    return {
        "server": server,
        "port": port,
        "secret": secret,
        "reachable_from": reachable,
        "status": status,
        "type": ptype,
        "uptime": uptime,
        "source_latency": latency,
        "tg_url": "tg://proxy?" + qs,
    }


def get_strict_candidates():
    raw = json.loads(http_get(JSON_SOURCE))
    rows = raw.get("proxies") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected proxies.json format")

    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        p = normalize_row(row)
        if not p:
            continue
        if (
            p["port"] == 443
            and (p["secret"].lower().startswith("ee") or "faketls" in p["type"])
            and p["status"] == "handshake_ok"
            and "RU" in p["reachable_from"]
            and p["uptime"] >= MIN_UPTIME
        ):
            items.append(p)

    items.sort(key=lambda p: (-p["uptime"], p["source_latency"]))
    return items


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
            time.sleep(0.4)
    return p, round(sum(timings) / len(timings))


def proxy_id(p):
    raw = f"{p['server'].lower()}|{p['port']}|{p['secret']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def main():
    try:
        items = get_strict_candidates()
    except Exception as e:
        print("strict source failed:", e)
        items = []

    probe = items[:40]
    results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
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
        cards.append(f"""
        <div class="card" data-proxy-id="{pid}">
          <div class="topline">
            <div><b>Прокси {i}</b> <span class="code">#{pid}</span></div>
            <div class="vote-status" id="status-{pid}"></div>
          </div>
          <div class="small">{html.escape(p['server'])}:{p['port']}</div>
          <div class="quality">RU ✓ · handshake ✓ · uptime {p['uptime']:.0f}% · повторный ping {ms} мс</div>
          <div class="actions">
            <a class="btn connect" href="{html.escape(p['tg_url'], quote=True)}">Открыть в Telegram</a>
            <button class="btn good" onclick="rateProxy('{pid}','good')">✅ Работает</button>
            <button class="btn bad" onclick="rateProxy('{pid}','bad')">❌ Не работает</button>
          </div>
        </div>
        """)

    if not cards:
        cards = ['<div class="card warning"><b>Строгих прокси сейчас нет.</b><br>Слабые варианты страница специально не показывает.</div>']

    page = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Свежие MTProto прокси</title>
  <style>
    body{{font-family:Arial,sans-serif;max-width:720px;margin:0 auto;padding:24px;background:#f5f5f5;color:#222}}
    h1{{font-size:28px;margin-bottom:8px}}
    .meta{{color:#666;margin-bottom:8px}}
    .rule{{font-size:13px;color:#555;margin-bottom:20px;line-height:1.45}}
    .card{{background:#fff;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
    .warning{{line-height:1.5}}
    .topline{{display:flex;justify-content:space-between;gap:12px;align-items:center}}
    .code{{font-size:12px;color:#777;font-weight:400}}
    .small{{font-size:14px;color:#666;margin-top:5px}}
    .quality{{font-size:13px;margin-top:7px}}
    .actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
    .btn{{border:0;display:inline-block;padding:11px 14px;border-radius:10px;color:#fff;text-decoration:none;font-weight:700;font-size:14px;cursor:pointer}}
    .connect{{background:#229ed9}} .good{{background:#2e9d53}} .bad{{background:#c64747}}
    .vote-status{{font-size:12px;font-weight:700;white-space:nowrap}}
    .saved-good{{color:#2e9d53}} .saved-bad{{color:#c64747}}
    .note{{font-size:13px;color:#666;margin-top:20px;line-height:1.4}}
  </style>
</head>
<body>
  <h1>Свежие MTProto-прокси</h1>
  <div class="meta">Обновлено: {updated}</div>
  <div class="rule">Показываются только кандидаты, прошедшие строгий фильтр: FakeTLS · порт 443 · handshake_ok · проверка доступности из RU · uptime ≥ 60% · двойная проверка перед публикацией.</div>
  {''.join(cards)}
  <div class="note">Если строгих вариантов меньше пяти, страница покажет меньше пяти. Лучше 1–2 сильных кандидата, чем пять формально доступных, но бесполезных.</div>
<script>
function keyFor(id) {{ return 'proxy-rating-' + id; }}
function paint(id,value) {{
  const el=document.getElementById('status-'+id); if(!el)return;
  if(value==='good'){{el.textContent='✓ отмечен рабочим';el.className='vote-status saved-good';}}
  else if(value==='bad'){{el.textContent='✕ отмечен нерабочим';el.className='vote-status saved-bad';}}
}}
function rateProxy(id,value) {{
  localStorage.setItem(keyFor(id),JSON.stringify({{proxy_id:id,result:value,saved_at:new Date().toISOString()}}));
  paint(id,value);
}}
document.querySelectorAll('[data-proxy-id]').forEach(card=>{{
  const id=card.dataset.proxyId;
  try{{const raw=localStorage.getItem(keyFor(id));if(raw){{paint(id,JSON.parse(raw).result);}}}}catch(e){{}}
}});
</script>
</body>
</html>"""

    Path("index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
