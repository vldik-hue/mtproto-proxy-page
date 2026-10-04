#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib, html, json, re, socket, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

COUNT=5
TIMEOUT=3.0
UA="Mozilla/5.0 MTProtoProxyPage/4.0"

CONFIRMED=[
    {"server":"nngo.cc","port":443,"secret":"ddf390d9757cb92d87826bcef28a6e75ed","score":10000,"label":"подтверждено на телефоне"}
]
JSON_SOURCE="https://zakky8.github.io/mtproto-proxy-pro/proxies.json"
TEXT_SOURCES=[
    "https://zakky8.github.io/mtproto-proxy-pro/all_proxies.txt",
    "https://raw.githubusercontent.com/aviamastersgh/mtproto-free-russia/main/verified_proxies.txt",
    "https://raw.githubusercontent.com/tgmtproxy/telegram-mtproto-proxy-list/main/proxies.txt",
]

def http_get(url,timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8",errors="replace")

def normalize(server,port,secret,**extra):
    server=str(server or "").strip(); secret=str(secret or "").strip()
    try: port=int(port)
    except Exception: return None
    if not server or not port or not secret:return None
    p={"server":server,"port":port,"secret":secret}; p.update(extra)
    q=urllib.parse.urlencode({"server":server,"port":port,"secret":secret})
    p["tg_url"]="tg://proxy?"+q
    return p

def parse_text(text):
    out=[]; seen=set()
    for pat in [r'https?://t\.me/proxy\?[^\s<>"\']+',r'tg://proxy\?[^\s<>"\']+']:
        for m in re.finditer(pat,text,re.I):
            try:
                q=urllib.parse.parse_qs(urllib.parse.urlsplit(m.group(0)).query)
                p=normalize(q.get("server",[""])[0],q.get("port",["0"])[0],q.get("secret",[""])[0])
                if not p:continue
                k=(p["server"].lower(),p["port"],p["secret"])
                if k not in seen:seen.add(k);out.append(p)
            except Exception:pass
    return out

def collect():
    merged=[];seen=set()
    for p in CONFIRMED:
        q=normalize(p["server"],p["port"],p["secret"],score=p["score"],label=p["label"])
        k=(q["server"].lower(),q["port"],q["secret"]);seen.add(k);merged.append(q)
    try:
        raw=json.loads(http_get(JSON_SOURCE)); rows=raw.get("proxies") if isinstance(raw,dict) else raw
        if isinstance(rows,list):
            for row in rows:
                if not isinstance(row,dict):continue
                p=normalize(row.get("server"),row.get("port"),row.get("secret"))
                if not p or p["port"]!=443:continue
                st=str(row.get("status") or "").lower(); typ=str(row.get("type") or "").lower()
                reachable=row.get("reachable_from") or []
                if isinstance(reachable,str):reachable=[reachable]
                reachable=[str(x).upper() for x in reachable]
                try:uptime=float(row.get("uptime_pct") or 0)
                except Exception:uptime=0
                try:lat=float(row.get("latency_ms") or 999999)
                except Exception:lat=999999
                if st not in ("handshake_ok","reachable","ok","alive"):continue
                score=(500 if "RU" in reachable else 0)+(250 if st=="handshake_ok" else 0)
                score+=(120 if p["secret"].lower().startswith("dd") else 0)
                score+=(100 if p["secret"].lower().startswith("ee") or "faketls" in typ else 0)
                score+=min(uptime,100)*3-min(lat,1000)/20
                p.update(score=score,label=("RU-проверка" if "RU" in reachable else "источник"),uptime=uptime)
                k=(p["server"].lower(),p["port"],p["secret"])
                if k not in seen:seen.add(k);merged.append(p)
    except Exception as e:print("json source failed",e)

    for src in TEXT_SOURCES:
        try:
            for p in parse_text(http_get(src)):
                if p["port"]!=443:continue
                k=(p["server"].lower(),p["port"],p["secret"])
                if k in seen:continue
                seen.add(k);p.update(score=25,label="резерв",uptime=0);merged.append(p)
        except Exception as e:print("text source failed",src,e)
    merged.sort(key=lambda p:p.get("score",0),reverse=True)
    return merged

def check_twice(p):
    vals=[]
    for n in range(2):
        st=time.perf_counter()
        try:
            with socket.create_connection((p["server"],p["port"]),timeout=TIMEOUT):
                vals.append(int((time.perf_counter()-st)*1000))
        except Exception:return p,None
        if n==0:time.sleep(.4)
    return p,round(sum(vals)/len(vals))

def pid(p):
    return hashlib.sha256(f"{p['server']}|{p['port']}|{p['secret']}".encode()).hexdigest()[:8]

def main():
    items=collect(); probe=items[:80]; passed={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs={ex.submit(check_twice,p):i for i,p in enumerate(probe)}
        for f in as_completed(fs):
            i=fs[f];p,ms=f.result()
            if ms is not None:passed[i]=(p,ms)
    chosen=[passed[i] for i in range(len(probe)) if i in passed][:COUNT]

    now=datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M UTC+3")
    cards=[]
    for i,(p,ms) in enumerate(chosen,1):
        x=pid(p); star="⭐ " if p["server"]=="nngo.cc" else ""
        cards.append(f'''<div class="card" data-proxy-id="{x}">
        <div class="top"><b>{star}Прокси {i}</b><span id="status-{x}" class="status"></span></div>
        <div class="small">{html.escape(p["server"])}:{p["port"]} · {ms} мс</div>
        <div class="quality">{html.escape(p.get("label","источник"))}</div>
        <div class="actions">
        <a class="btn open" href="{html.escape(p["tg_url"],quote=True)}">Открыть в Telegram</a>
        <button class="btn good" onclick="rate('{x}','good')">✅ Работает</button>
        <button class="btn bad" onclick="rate('{x}','bad')">❌ Не работает</button>
        </div></div>''')
    if not cards:cards=['<div class="card">Сейчас нет кандидатов, прошедших двойную проверку.</div>']

    page=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>MTProto прокси</title><style>
    body{{font-family:Arial,sans-serif;max-width:720px;margin:auto;padding:24px;background:#f5f5f5;color:#222}}
    .card{{background:#fff;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 2px 10px #0001}}
    .top{{display:flex;justify-content:space-between}} .small{{color:#666;margin-top:5px}} .quality{{font-size:13px;margin-top:6px}}
    .actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}} .btn{{border:0;border-radius:10px;padding:11px 14px;color:white;font-weight:700;text-decoration:none}}
    .open{{background:#229ed9}} .good{{background:#2e9d53}} .bad{{background:#c64747}} .status{{font-size:12px;font-weight:700}}
    </style></head><body>
    <h1>Свежие MTProto-прокси</h1><div>Обновлено: {now}</div>
    <p>Приоритет: подтверждённые у тебя → RU/handshake/uptime → резерв. Разрешены и dd, и ee. Повторы разрешены.</p>
    {''.join(cards)}
    <script>
    function rate(id,v){{localStorage.setItem('proxy-rating-'+id,v);paint(id,v)}}
    function paint(id,v){{let e=document.getElementById('status-'+id);if(!e)return;e.textContent=v==='good'?'✓ рабочий':'✕ нерабочий';e.style.color=v==='good'?'#2e9d53':'#c64747'}}
    document.querySelectorAll('[data-proxy-id]').forEach(c=>{{let id=c.dataset.proxyId,v=localStorage.getItem('proxy-rating-'+id);if(v)paint(id,v)}})
    </script></body></html>'''
    Path("index.html").write_text(page,encoding="utf-8")

if __name__=="__main__":main()
