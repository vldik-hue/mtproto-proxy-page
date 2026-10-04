#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib, html, json, re, socket, time, urllib.parse, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

COUNT=50
TIMEOUT=3.0
UA="Mozilla/5.0 MTProtoProxyPage/5.0"

CONFIRMED=[("nngo.cc",443,"ddf390d9757cb92d87826bcef28a6e75ed","подтверждён раньше")]
SOURCES=[
    ("tgmtproxy hourly","https://raw.githubusercontent.com/tgmtproxy/telegram-mtproto-proxy-list/main/proxies.txt"),
    ("shablin 4h","https://raw.githubusercontent.com/shablin/mtproto-proxy/main/data/valid_proxy.txt"),
    ("Grim 12h","https://raw.githubusercontent.com/Grim1313/mtproto-for-telegram/master/all_proxies.txt"),
    ("aviamasters RU","https://raw.githubusercontent.com/aviamastersgh/mtproto-free-russia/main/verified_proxies.txt"),
    ("zakky RU","https://zakky8.github.io/mtproto-proxy-pro/censorship_resistant.txt"),
]
PREFERRED_PORTS={443,8443,2053,2083,2096}

def get(url,timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read().decode("utf-8",errors="replace")

def norm(server,port,secret,source):
    server=str(server or "").strip().rstrip(".");secret=str(secret or "").strip()
    try:port=int(port)
    except Exception:return None
    if not server or not secret or port not in PREFERRED_PORTS:return None
    qs=urllib.parse.urlencode({"server":server,"port":port,"secret":secret})
    return {"server":server,"port":port,"secret":secret,"source":source,"tg":"tg://proxy?"+qs}

def parse(text,source):
    out=[];seen=set()
    for m in re.finditer(r'(?:https?://t\.me/proxy|tg://proxy)\?[^\s<>"\']+',text,re.I):
        try:
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(m.group(0)).query)
            p=norm(q.get("server",[""])[0],q.get("port",["0"])[0],q.get("secret",[""])[0],source)
            if not p:continue
            k=(p["server"].lower(),p["port"],p["secret"])
            if k not in seen:seen.add(k);out.append(p)
        except Exception:pass
    return out

def dgroup(host):
    if re.fullmatch(r'\d+\.\d+\.\d+\.\d+',host):return host
    x=host.lower().split(".");return ".".join(x[-2:]) if len(x)>=2 else host.lower()

def collect():
    b=defaultdict(list)
    for h,p,s,label in CONFIRMED:
        q=norm(h,p,s,"white-list")
        if q:q["label"]=label;b["white-list"].append(q)
    for label,url in SOURCES:
        try:b[label].extend(parse(get(url),label)[:180])
        except Exception as e:print("source failed",label,e)
    return b

def check(p):
    vals=[]
    for n in range(2):
        t=time.perf_counter()
        try:
            with socket.create_connection((p["server"],p["port"]),timeout=TIMEOUT):
                vals.append(int((time.perf_counter()-t)*1000))
        except Exception:return p,None
        if n==0:time.sleep(.35)
    return p,round(sum(vals)/len(vals))

def verify(b):
    items=[p for arr in b.values() for p in arr[:120]]
    passed=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        fs=[ex.submit(check,p) for p in items]
        for f in as_completed(fs):
            p,ms=f.result()
            if ms is not None:
                p=dict(p);p["ms"]=ms;passed.append(p)
    out=defaultdict(list)
    for p in passed:out[p["source"]].append(p)
    for src in out:out[src].sort(key=lambda x:x["ms"])
    return out

def choose(by,count):
    chosen=[];keys=set();domains=set()
    for p in by.get("white-list",[]):
        k=(p["server"].lower(),p["port"],p["secret"])
        if k not in keys:chosen.append(p);keys.add(k);domains.add(dgroup(p["server"]))
        if len(chosen)>=count:return chosen
    order=[x[0] for x in SOURCES];idx=defaultdict(int)
    while len(chosen)<count:
        added=False
        for src in order:
            arr=by.get(src,[])
            while idx[src]<len(arr):
                p=arr[idx[src]];idx[src]+=1
                k=(p["server"].lower(),p["port"],p["secret"]);dg=dgroup(p["server"])
                if k in keys or dg in domains:continue
                chosen.append(p);keys.add(k);domains.add(dg);added=True;break
            if len(chosen)>=count:break
        if not added:break
    if len(chosen)<count:
        rest=[p for arr in by.values() for p in arr];rest.sort(key=lambda x:x["ms"])
        for p in rest:
            k=(p["server"].lower(),p["port"],p["secret"])
            if k in keys:continue
            chosen.append(p);keys.add(k)
            if len(chosen)>=count:break
    return chosen

def pid(p):return hashlib.sha256(f"{p['server']}|{p['port']}|{p['secret']}".encode()).hexdigest()[:8]

def main():
    chosen=choose(verify(collect()),COUNT)

    # Каталог нужен сборщику обратной связи: ID -> конкретный прокси.
    catalog_path=Path("proxy_catalog.json")
    try:
        catalog=json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {"proxies":{}}
    except Exception:
        catalog={"proxies":{}}
    if not isinstance(catalog,dict): catalog={"proxies":{}}
    catalog.setdefault("proxies",{})
    for p in chosen:
        x=pid(p)
        catalog["proxies"][x]={
            "server":p["server"],"port":p["port"],"secret":p["secret"],
            "source":p["source"],"last_seen":datetime.now(timezone.utc).isoformat()
        }
    # Ограничиваем историю последними 500 ID.
    items=list(catalog["proxies"].items())
    if len(items)>500:
        items=sorted(items,key=lambda kv:kv[1].get("last_seen",""),reverse=True)[:500]
        catalog["proxies"]=dict(items)
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    now=datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M UTC+3")
    cards=[]
    for i,p in enumerate(chosen,1):
        x=pid(p);typ="dd" if p["secret"].lower().startswith("dd") else ("ee" if p["secret"].lower().startswith("ee") else "other")
        cards.append(f'''<div class="card" data-proxy-id="{x}" data-index="{i-1}" data-source="{html.escape(p["source"],quote=True)}">
        <div class="top"><b>Прокси {i}</b><span id="status-{x}" class="status"></span></div>
        <div class="host">{html.escape(p["server"])}:{p["port"]}</div>
        <div class="meta">тип {typ} · {p["ms"]} мс · {html.escape(p["source"])}</div>
        <div class="actions">
        <a class="btn open" href="{html.escape(p["tg"],quote=True)}">Открыть в Telegram</a>
        <button class="btn good" onclick="markWorking('{x}')">✅ Работает</button>
        </div></div>''')
    if not cards:cards=['<div class="card"><b>Сейчас кандидатов нет.</b> Ни один из пяти источников не прошёл локальную двойную проверку.</div>']

    page=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>MTProto прокси</title><style>
    body{{font-family:Arial,sans-serif;max-width:760px;margin:auto;padding:22px;background:#f5f5f5;color:#222}}
    h1{{margin-bottom:8px}} .lead{{color:#555;line-height:1.45}}
    .card{{background:white;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 2px 10px #0001}}
    .top{{display:flex;justify-content:space-between}} .host{{margin-top:6px;font-weight:700}} .meta{{font-size:13px;color:#666;margin-top:5px}}
    .actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}} .btn{{border:0;border-radius:10px;padding:11px 14px;color:#fff;font-weight:700;text-decoration:none;cursor:pointer}}
    .open{{background:#229ed9}} .good{{background:#2e9d53}} .bad{{background:#c64747}} .status{{font-size:12px;font-weight:700}}
    </style></head><body><h1>MTProto — тест разных источников</h1>
    <div class="lead">Обновлено: {now}<br>Страница работает автономно, даже когда Telegram не подключается. Проверяй текущую десятку: если никто не заработал — одним нажатием помечай всю десятку нерабочей и сразу переходи дальше. Если один заработал — нажми «✅ Работает» только напротив него.</div>
    {''.join(cards)}
    <div class="sendbox">
      <button class="btn badbatch" onclick="rejectCurrentBatch()">❌ Вся десятка не работает</button>
      <button class="btn sendall" onclick="showWorking()">⭐ Показать рабочие</button>
      <div class="sendhint">Если ни один не заработал — один раз нажми «Вся десятка не работает». Если какой-то заработал — нажми только «✅ Работает» напротив него.</div>
      <div class="sendhint" id="source-summary"></div>
    </div>
    <script>
    let batchStart=parseInt(localStorage.getItem('proxy-batch-start')||'0',10);
    const BATCH_SIZE=10;
    function markWorking(id){{
      const card=document.querySelector('[data-proxy-id="'+id+'"]');
      const prev=localStorage.getItem('proxy-rating-'+id);
      if(prev!=='good' && card) bumpSource(card.dataset.source||'','good');
      localStorage.setItem('proxy-rating-'+id,'good');
      paint(id,'good');
    }}
    function paint(id,v){{
      let e=document.getElementById('status-'+id);if(!e)return;
      e.textContent=v==='good'?'✓ рабочий':v==='bad'?'✕ нерабочий':'';
      e.style.color=v==='good'?'#2e9d53':v==='bad'?'#c64747':'#666';
    }}
    function sourceKey(source){{return 'proxy-source-stats-'+source;}}
    function getSourceStats(source){{
      try{{return JSON.parse(localStorage.getItem(sourceKey(source))||'{"good":0,"bad":0}');}}
      catch(e){{return {{good:0,bad:0}};}}
    }}
    function bumpSource(source,kind){{
      const s=getSourceStats(source);
      s[kind]=(s[kind]||0)+1;
      localStorage.setItem(sourceKey(source),JSON.stringify(s));
    }}
    function sourceScore(card){{
      const s=getSourceStats(card.dataset.source||'');
      const total=(s.good||0)+(s.bad||0);
      if(!total) return 0;
      return ((s.good||0)-(s.bad||0))/total;
    }}
    function eligibleCards(){{
      return Array.from(document.querySelectorAll('[data-proxy-id]'))
        .filter(c=>localStorage.getItem('proxy-rating-'+c.dataset.proxyId)!=='bad')
        .sort((a,b)=>sourceScore(b)-sourceScore(a));
    }}
    function updateSourceSummary(){{
      const sources=[...new Set(Array.from(document.querySelectorAll('[data-proxy-id]')).map(c=>c.dataset.source||''))];
      const rows=sources.map(src=>{{const s=getSourceStats(src);return [src,s.good||0,s.bad||0];}})
        .filter(r=>r[1]+r[2]>0)
        .sort((a,b)=>(b[2]-b[1])-(a[2]-a[1]));
      const el=document.getElementById('source-summary');
      if(!el) return;
      if(!rows.length){{el.textContent='Статистика по источникам появится после первых оценок.';return;}}
      el.innerHTML='<b>Локально по источникам:</b> '+rows.map(r=>r[0]+': ✅ '+r[1]+' / ❌ '+r[2]).join(' · ');
    }}
    function renderBatch(){{
      const all=Array.from(document.querySelectorAll('[data-proxy-id]'));
      all.forEach(c=>c.style.display='none');
      const eligible=eligibleCards();
      if(!eligible.length){{alert('Все загруженные прокси отмечены нерабочими. Нужен новый пул.');return;}}
      if(batchStart>=eligible.length) batchStart=0;
      eligible.slice(batchStart,batchStart+BATCH_SIZE).forEach(c=>{{
        c.style.display='block';
        paint(c.dataset.proxyId,localStorage.getItem('proxy-rating-'+c.dataset.proxyId)||'');
      }});
      localStorage.setItem('proxy-batch-start',String(batchStart));
      updateSourceSummary();
    }}
    function rejectCurrentBatch(){{
      const visible=Array.from(document.querySelectorAll('[data-proxy-id]')).filter(c=>c.style.display!=='none');
      if(!visible.length) return;
      visible.forEach(c=>{{
        const id=c.dataset.proxyId;
        const prev=localStorage.getItem('proxy-rating-'+id);
        if(prev!=='bad') bumpSource(c.dataset.source||'','bad');
        localStorage.setItem('proxy-rating-'+id,'bad');
      }});
      const eligible=eligibleCards();
      if(!eligible.length){{
        renderBatch();
        return;
      }}
      if(batchStart>=eligible.length) batchStart=0;
      renderBatch();
      window.scrollTo({{top:0,behavior:'smooth'}});
    }}
    function showWorking(){{
      const all=Array.from(document.querySelectorAll('[data-proxy-id]'));
      all.forEach(c=>c.style.display='none');
      const goods=all.filter(c=>localStorage.getItem('proxy-rating-'+c.dataset.proxyId)==='good');
      if(!goods.length){{alert('Пока ни один прокси не отмечен рабочим.');renderBatch();return;}}
      goods.forEach(c=>{{c.style.display='block';paint(c.dataset.proxyId,'good');}});
    }}
    renderBatch();
    </script></body></html>'''
    Path("index.html").write_text(page,encoding="utf-8")

if __name__=="__main__":main()
