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

CONFIRMED=[
    ("nngo.cc",443,"ddf390d9757cb92d87826bcef28a6e75ed","подтверждён раньше"),
    ("nnmm.me",443,"ddf390d9757cb92d87826bcef28a6e75ed","та же рабочая семья"),
    ("85.192.35.94",443,"ddf390d9757cb92d87826bcef28a6e75ed","та же рабочая семья"),
]
SOURCES=[
    # Практический список именно для обхода блокировок в РФ.
    ("Prihs RU curated","https://raw.githubusercontent.com/vpnsvpns/Prihs/main/README.md"),
    # Реальная MTProto/FakeTLS-проверка, обновление каждый час.
    ("tgmtproxy handshake","https://raw.githubusercontent.com/tgmtproxy/telegram-mtproto-proxy-list/main/proxies.txt"),
    # Реальная MTProto handshake-проверка, отдельный независимый проект.
    ("dubblebyte handshake","https://raw.githubusercontent.com/dubblebyte/free-mtproto-proxies/main/all_proxies.txt"),
    # Российский агрегатор: публикует только подтверждённые соединения.
    ("aviamasters RU verified","https://raw.githubusercontent.com/aviamastersgh/mtproto-free-russia/main/verified_proxies.txt"),
    # Список с проверкой из России через внешние точки и FakeTLS handshake.
    ("zakky RU resilient","https://zakky8.github.io/mtproto-proxy-pro/censorship_resistant.txt"),
]
PREFERRED_PORTS={443,853,8443,9443,2053,2083,2096,25565}

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
        <div class="top">
          <div class="num">#{i}</div>
          <div class="host">{html.escape(p["server"])}:{p["port"]}</div>
          <span id="status-{x}" class="status"></span>
        </div>
        <div class="meta">{typ.upper()} · {p["ms"]} мс · {html.escape(p["source"])}</div>
        <div class="actions">
          <a class="btn open" href="{html.escape(p["tg"],quote=True)}">▶ Проверить</a>
          <button class="btn good" onclick="markWorking('{x}')">✅ Работает</button>
        </div>
        </div>''')
    if not cards:cards=['<div class="card"><b>Сейчас кандидатов нет.</b> Ни один из пяти источников не прошёл локальную двойную проверку.</div>']

    page=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>MTProto — быстрый перебор</title><style>
    *{{box-sizing:border-box}}
    body{{font-family:Arial,sans-serif;max-width:760px;margin:auto;padding:16px 16px 120px;background:#f3f5f7;color:#202124}}
    h1{{font-size:26px;margin:4px 0 6px}}
    .lead{{color:#5f6368;line-height:1.45;font-size:14px;margin-bottom:12px}}
    .progress{{background:#fff;border-radius:12px;padding:11px 13px;margin:12px 0;font-weight:700;box-shadow:0 1px 6px #0001}}
    .card{{background:#fff;border-radius:14px;padding:13px 14px;margin:10px 0;box-shadow:0 2px 10px #0001}}
    .top{{display:grid;grid-template-columns:44px 1fr auto;gap:8px;align-items:center}}
    .num{{font-weight:800;color:#777}}
    .host{{font-weight:800;overflow-wrap:anywhere}}
    .status{{font-size:12px;font-weight:800;white-space:nowrap}}
    .meta{{font-size:12px;color:#777;margin:6px 0 0 52px;overflow-wrap:anywhere}}
    .actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:11px}}
    .btn{{border:0;border-radius:10px;padding:12px 10px;color:#fff;font-weight:800;text-decoration:none;cursor:pointer;text-align:center;font-size:14px}}
    .open{{background:#229ed9}} .good{{background:#2e9d53}} .badbatch{{background:#c64747}} .working{{background:#6b55c9}}
    .controls{{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #ddd;padding:10px 12px 12px;z-index:20;box-shadow:0 -4px 18px #0002}}
    .controls-inner{{max-width:760px;margin:auto;display:grid;grid-template-columns:2fr 1fr;gap:8px}}
    .sendhint{{font-size:12px;color:#666;margin-top:8px;line-height:1.35}}
    .sourcebox{{font-size:12px;color:#666;background:#fff;border-radius:12px;padding:10px 12px;margin-top:12px;line-height:1.4}}
    @media(max-width:520px){{
      body{{padding:12px 10px 125px}}
      h1{{font-size:22px}}
      .actions{{grid-template-columns:1fr 1fr}}
      .meta{{margin-left:0}}
      .top{{grid-template-columns:36px 1fr auto}}
      .controls-inner{{grid-template-columns:1fr}}
    }}
    </style></head><body>
    <h1>MTProto — быстрый перебор</h1>
    <div class="lead">Обновлено: {now}. Показывается по 10 вариантов. Проверяй только кнопку «▶ Проверить». Если вся десятка мёртвая — одним нажатием отправляем её в брак. Если один заработал — нажми «✅ Работает» только на нём.</div>
    <div class="progress" id="progress">Загрузка...</div>
    {''.join(cards)}
    <div class="sourcebox" id="source-summary">Статистика по источникам появится после первых оценок.</div>
    <div class="controls">
      <div class="controls-inner">
        <button class="btn badbatch" onclick="rejectCurrentBatch()">❌ Вся десятка не работает</button>
        <button class="btn working" onclick="showWorking()">⭐ Рабочие</button>
      </div>
      <div class="sendhint">Нерабочая десятка исчезнет сразу, и откроется следующая. Уже отмеченные «✅ Работает» не будут сброшены. Всё запоминается на этом устройстве.</div>
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
      try{{return JSON.parse(localStorage.getItem(sourceKey(source))||'{{"good":0,"bad":0}}');}}
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
      if(!eligible.length){{
        const pr=document.getElementById('progress');
        if(pr) pr.textContent='Все загруженные прокси отбракованы. Ждём новый пул.';
        return;
      }}
      if(batchStart>=eligible.length) batchStart=0;
      eligible.slice(batchStart,batchStart+BATCH_SIZE).forEach(c=>{{
        c.style.display='block';
        paint(c.dataset.proxyId,localStorage.getItem('proxy-rating-'+c.dataset.proxyId)||'');
      }});
      localStorage.setItem('proxy-batch-start',String(batchStart));
      const badCount=all.filter(c=>localStorage.getItem('proxy-rating-'+c.dataset.proxyId)==='bad').length;
      const goodCount=all.filter(c=>localStorage.getItem('proxy-rating-'+c.dataset.proxyId)==='good').length;
      const shown=Math.min(BATCH_SIZE,Math.max(0,eligible.length-batchStart));
      const batchNo=Math.floor(batchStart/BATCH_SIZE)+1;
      const totalBatches=Math.max(1,Math.ceil(eligible.length/BATCH_SIZE));
      const pr=document.getElementById('progress');
      if(pr) pr.textContent='Пачка '+batchNo+' из '+totalBatches+' · сейчас '+shown+' · отбраковано '+badCount+' · рабочих '+goodCount;
      updateSourceSummary();
    }}
    function rejectCurrentBatch(){{
      const visible=Array.from(document.querySelectorAll('[data-proxy-id]')).filter(c=>c.style.display!=='none');
      if(!visible.length) return;
      visible.forEach(c=>{{
        const id=c.dataset.proxyId;
        const prev=localStorage.getItem('proxy-rating-'+id);
        // Никогда не перезаписываем уже подтверждённый рабочий прокси.
        if(prev==='good') return;
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
