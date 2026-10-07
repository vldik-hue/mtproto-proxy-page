#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib, html, json, re, socket, time, urllib.parse, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

COUNT=200
TIMEOUT=3.0
UA="Mozilla/5.0 MTProtoProxyPage/5.0"

CONFIRMED=[
    ("m.aysghfkzcxg.info",8443,"eeNEgYdJvXrFGRMCIMJdCQ","подтверждён пользователем 04.10.2026"),
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
PREFERRED_PORTS={443,853,7443,8443,9443,2053,2083,2096,25565}
PROXYMT_LABEL="@ProxyMTProto"
PROXYMT_URL="https://t.me/s/proxymtproto"
PROXYMT_LIMIT=6
SOCKS5_COUNT=5
SOCKS5_VERIFY_LIMIT=160
SOCKS5_SOURCE=("ProxyScrape live","https://raw.githubusercontent.com/proxyscrape/free-proxy-list/main/proxies/protocols/socks5/data.txt")

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

def parse_proxymtproto_feed(text):
    """Parse recent public @ProxyMTProto channel posts from Telegram's web preview."""
    items={}
    blocks=re.split(r"""(?=<div class=["']tgme_widget_message_wrap\b)""",text,flags=re.I)
    for block in blocks:
        if "Server:" not in block or "Secret:" not in block:
            continue
        plain=re.sub(r"<br\s*/?>","\n",block,flags=re.I)
        plain=html.unescape(re.sub(r"<[^>]+>"," ",plain))
        sm=re.search(r"Server:\s*([^\s]+)",plain,re.I)
        pm=re.search(r"Port:\s*(\d{1,5})",plain,re.I)
        km=re.search(r"Secret:\s*([A-Za-z0-9_-]+)",plain,re.I)
        if not (sm and pm and km):
            continue
        server=sm.group(1).strip().rstrip(".")
        if server.lower()=="unknown":
            continue
        p=norm(server,pm.group(1),km.group(1),PROXYMT_LABEL)
        if not p:
            continue
        tm=re.search(r"""datetime=["']([^"']+)["']""",block,re.I)
        published=tm.group(1) if tm else ""
        key=(p["server"].lower(),p["port"],p["secret"])
        if key in items:
            old=items[key]
            old["repeat_count"]=old.get("repeat_count",1)+1
            if published and published>old.get("published_at",""):
                old["published_at"]=published
            continue
        p["published_at"]=published
        p["repeat_count"]=1
        p["priority"]=True
        items[key]=p
    return sorted(items.values(), key=lambda x:x.get("published_at",""), reverse=True)

def parse_socks5(text,source):
    out=[];seen=set()
    for raw in text.splitlines():
        line=raw.strip()
        if not line:continue
        if not line.lower().startswith("socks5://"):line="socks5://"+line
        try:
            u=urllib.parse.urlsplit(line)
            host=(u.hostname or "").strip().rstrip(".");port=int(u.port or 0)
            if not host or not (1<=port<=65535):continue
            user=urllib.parse.unquote(u.username or "");password=urllib.parse.unquote(u.password or "")
            k=(host.lower(),port,user,password)
            if k in seen:continue
            seen.add(k)
            out.append({"protocol":"socks5","server":host,"port":port,"user":user,"pass":password,"source":source})
        except Exception:pass
    return out

def dgroup(host):
    if re.fullmatch(r'\d+\.\d+\.\d+\.\d+',host):return host
    x=host.lower().split(".");return ".".join(x[-2:]) if len(x)>=2 else host.lower()

def collect():
    b=defaultdict(list)
    try:
        fresh=parse_proxymtproto_feed(get(PROXYMT_URL))
        b[PROXYMT_LABEL].extend(fresh[:PROXYMT_LIMIT])
    except Exception as e:
        print("source failed",PROXYMT_LABEL,e)
    for h,p,s,label in CONFIRMED:
        q=norm(h,p,s,"white-list")
        if q:q["label"]=label;b["white-list"].append(q)
    for label,url in SOURCES:
        try:b[label].extend(parse(get(url),label)[:180])
        except Exception as e:print("source failed",label,e)

    # Exact corroboration only: same server + port + secret in independent sources.
    source_keys={}
    for label,_ in SOURCES:
        source_keys[label]={
            (p["server"].lower(),p["port"],p["secret"])
            for p in b.get(label,[])
        }
    for p in b.get(PROXYMT_LABEL,[]):
        key=(p["server"].lower(),p["port"],p["secret"])
        p["corroborated_by"]=[label for label,_ in SOURCES if key in source_keys.get(label,set())]
    return b

def _recv_exact(sock,n):
    data=b""
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part:raise OSError("SOCKS5 closed connection")
        data+=part
    return data

def socks5_probe(p,target_host="149.154.167.50",target_port=443,timeout=TIMEOUT):
    started=time.perf_counter()
    try:
        with socket.create_connection((p["server"],p["port"]),timeout=timeout) as s:
            s.settimeout(timeout)
            user=str(p.get("user") or "")
            password=str(p.get("pass") or "")
            methods=b"\x00\x02" if (user or password) else b"\x00"
            s.sendall(bytes([5,len(methods)])+methods)
            ver,method=_recv_exact(s,2)
            if ver!=5 or method==0xff:return p,None
            if method==2:
                ub=user.encode("utf-8");pb=password.encode("utf-8")
                if len(ub)>255 or len(pb)>255:return p,None
                s.sendall(bytes([1,len(ub)])+ub+bytes([len(pb)])+pb)
                if _recv_exact(s,2)!=b"\x01\x00":return p,None
            elif method!=0:
                return p,None

            try:
                addr=socket.inet_aton(target_host);atyp=1
            except OSError:
                hb=target_host.encode("idna")
                if len(hb)>255:return p,None
                addr=bytes([len(hb)])+hb;atyp=3
            req=b"\x05\x01\x00"+bytes([atyp])+addr+int(target_port).to_bytes(2,"big")
            s.sendall(req)
            head=_recv_exact(s,4)
            if head[0]!=5 or head[1]!=0:return p,None
            if head[3]==1:_recv_exact(s,4)
            elif head[3]==3:_recv_exact(s,_recv_exact(s,1)[0])
            elif head[3]==4:_recv_exact(s,16)
            else:return p,None
            _recv_exact(s,2)
            return p,int((time.perf_counter()-started)*1000)
    except Exception:
        return p,None

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

def verify_socks5():
    label,url=SOCKS5_SOURCE
    try:candidates=parse_socks5(get(url),label)[:SOCKS5_VERIFY_LIMIT]
    except Exception as e:
        print("SOCKS5 source failed",e);return []
    passed=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        fs=[ex.submit(socks5_probe,p) for p in candidates]
        for f in as_completed(fs):
            p,ms=f.result()
            if ms is not None:
                q=dict(p);q["ms"]=ms;passed.append(q)
    passed.sort(key=lambda x:x["ms"])
    chosen=[];servers=set()
    for p in passed:
        if p["server"].lower() in servers:continue
        chosen.append(p);servers.add(p["server"].lower())
        if len(chosen)>=SOCKS5_COUNT:break
    return chosen

def verify(b):
    # @ProxyMTProto is intentionally not gated or reordered by GitHub TCP checks.
    # The channel itself is the primary freshness signal; GitHub probing remains
    # only for the automatic reserve from other sources.
    out=defaultdict(list)
    for p in b.get(PROXYMT_LABEL,[]):
        q=dict(p)
        q["channel_fresh"]=True
        out[PROXYMT_LABEL].append(q)

    items=[
        p for src,arr in b.items()
        if src!=PROXYMT_LABEL
        for p in arr[:120]
    ]
    passed=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        fs=[ex.submit(check,p) for p in items]
        for f in as_completed(fs):
            p,ms=f.result()
            if ms is not None:
                q=dict(p);q["ms"]=ms;passed.append(q)
    for p in passed:out[p["source"]].append(p)
    for src in out:
        if src==PROXYMT_LABEL:
            out[src].sort(key=lambda x:x.get("published_at",""),reverse=True)
        else:
            out[src].sort(key=lambda x:x["ms"])
    return out

def choose(by,count):
    chosen=[];keys=set();domains=set()

    def take(p):
        k=(p["server"].lower(),p["port"],p["secret"]);dg=dgroup(p["server"])
        if k in keys or dg in domains:return False
        chosen.append(p);keys.add(k);domains.add(dg);return True

    # Fresh curated channel candidates come first.
    for p in by.get(PROXYMT_LABEL,[]):
        take(p)
        if len(chosen)>=count:return chosen

    for p in by.get("white-list",[]):
        take(p)
        if len(chosen)>=count:return chosen

    order=[x[0] for x in SOURCES];idx=defaultdict(int)
    while len(chosen)<count:
        added=False
        for src in order:
            arr=by.get(src,[])
            while idx[src]<len(arr):
                p=arr[idx[src]];idx[src]+=1
                if take(p):added=True;break
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
def pid(p):
    if p.get("protocol")=="socks5":
        raw=f"socks5|{p['server']}|{p['port']}|{p.get('user','')}|{p.get('pass','')}"
    else:
        published=p.get("published_at","") if p.get("source")==PROXYMT_LABEL else ""
        raw=f"{p['server']}|{p['port']}|{p['secret']}|{published}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]

def main():
    chosen=choose(verify(collect()),COUNT)
    socks5=verify_socks5()

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
            "protocol":"mtproto","server":p["server"],"port":p["port"],"secret":p["secret"],
            "source":p["source"],"last_seen":datetime.now(timezone.utc).isoformat(),
            "published_at":p.get("published_at",""),"repeat_count":p.get("repeat_count",1),
            "priority":bool(p.get("priority")),"channel_fresh":bool(p.get("channel_fresh")),
            "corroborated_by":p.get("corroborated_by",[])
        }
    for p in socks5:
        x=pid(p)
        catalog["proxies"][x]={
            "protocol":"socks5","server":p["server"],"port":p["port"],"user":p.get("user",""),"pass":p.get("pass",""),
            "source":p["source"],"last_seen":datetime.now(timezone.utc).isoformat()
        }
    # Ограничиваем историю последними 500 ID.
    items=list(catalog["proxies"].items())
    if len(items)>500:
        items=sorted(items,key=lambda kv:kv[1].get("last_seen",""),reverse=True)[:500]
        catalog["proxies"]=dict(items)
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    generated_iso=datetime.now(timezone.utc).isoformat()
    now=datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M UTC+3")
    cards=[]
    priority_heading_added=False
    for i,p in enumerate(chosen,1):
        x=pid(p);typ="dd" if p["secret"].lower().startswith("dd") else ("ee" if p["secret"].lower().startswith("ee") else "other")
        is_priority=p.get("source")==PROXYMT_LABEL
        if is_priority and not priority_heading_added:
            cards.append('<div class="source-section" data-priority-section="proxymtproto"><b>🔥 Последние из @ProxyMTProto</b><br>Показываем последние 6 реальных публикаций канала как есть: без сортировки по пингу и без отсечения GitHub TCP-проверкой.</div>')
            priority_heading_added=True
        priority_attr=' data-priority-source="proxymtproto"' if is_priority else ''
        freshness=""
        if is_priority:
            pub=p.get("published_at","")
            corroborated=p.get("corroborated_by",[])
            freshness=(" · "+html.escape(pub[:16].replace("T"," ")) if pub else "")
            if corroborated:
                freshness+=" · ✓ ещё "+str(len(corroborated))+" источник"+("а" if len(corroborated) in (2,3,4) else "")
        cards.append(f'''<div class="card" data-proxy-id="{x}" data-index="{i-1}" data-source="{html.escape(p["source"],quote=True)}" data-port="{p["port"]}" data-kind="{typ}" data-server="{html.escape(p["server"],quote=True)}" data-domain="{html.escape(dgroup(p["server"]),quote=True)}" data-secret="{html.escape(p["secret"],quote=True)}" data-protocol="mtproto"{priority_attr}>
        <div class="top">
          <div class="num">#{i}</div>
          <div class="host">{html.escape(p["server"])}:{p["port"]}</div>
          <span id="status-{x}" class="status"></span>
        </div>
        <div class="meta">{("MTProto · свежий пост канала" if is_priority else "MTProto · "+typ.upper()+" · TCP доступен · "+str(p["ms"])+" мс")} · {html.escape(p["source"])}{freshness}</div>
        <div class="actions">
          <a class="btn open" data-attempt-link href="{html.escape(p["tg"],quote=True)}">▶ Проверить</a>
          <button class="btn good" onclick="markWorking('{x}')">✅ Работает</button>
        </div>
        </div>''')
    if not cards:cards=['<div class="card"><b>Сейчас кандидатов MTProto нет.</b></div>']
    for i,p in enumerate(socks5,1):
        x=pid(p)
        qs={"server":p["server"],"port":p["port"]}
        if p.get("user"):qs["user"]=p["user"]
        if p.get("pass"):qs["pass"]=p["pass"]
        link="tg://socks?"+urllib.parse.urlencode(qs)
        cards.append(f'''<div class="card" data-proxy-id="{x}" data-index="{i-1}" data-source="{html.escape(p["source"],quote=True)}" data-port="{p["port"]}" data-kind="socks5" data-server="{html.escape(p["server"],quote=True)}" data-domain="{html.escape(dgroup(p["server"]),quote=True)}" data-secret="" data-user="{html.escape(p.get("user",""),quote=True)}" data-pass="{html.escape(p.get("pass",""),quote=True)}" data-protocol="socks5">
        <div class="top">
          <div class="num">S{i}</div>
          <div class="host">{html.escape(p["server"])}:{p["port"]}</div>
          <span id="status-{x}" class="status"></span>
        </div>
        <div class="meta">SOCKS5 · handshake + Telegram CONNECT OK · {p["ms"]} мс · {html.escape(p["source"])}</div>
        <div class="actions">
          <a class="btn open" data-attempt-link href="{html.escape(link,quote=True)}">▶ Проверить</a>
          <button class="btn good" onclick="markWorking('{x}')">✅ Работает</button>
        </div>
        </div>''')
    socks_empty='<div class="card" id="socks5-empty" data-empty-transport="socks5" style="display:none"><b>SOCKS5: нет диагностических кандидатов.</b> Источник обновится автоматически.</div>'

    page=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Telegram — рабочий доступ</title><style>
    *{{box-sizing:border-box}}
    body{{font-family:Arial,sans-serif;max-width:760px;margin:auto;padding:10px 10px 108px;background:#f3f5f7;color:#202124}}
    h1{{font-size:20px;margin:2px 0 4px}}
    .lead{{color:#5f6368;line-height:1.3;font-size:12px;margin-bottom:8px}}
    .progress{{background:#fff;border-radius:10px;padding:7px 9px;margin:8px 0;font-weight:700;font-size:12px;box-shadow:0 1px 5px #0001}}
    .card{{background:#fff;border-radius:10px;padding:8px 9px;margin:6px 0;box-shadow:0 1px 6px #0001;transition:background .15s,border-color .15s}}
    .card.attempted{{background:#eef4f8;outline:1px solid #b9cfdd}}
    .top{{display:grid;grid-template-columns:30px 1fr auto;gap:5px;align-items:center}}
    .num{{font-weight:800;color:#777;font-size:12px}}
    .host{{font-weight:800;overflow-wrap:anywhere;font-size:13px;line-height:1.15}}
    .status{{font-size:10px;font-weight:800;white-space:nowrap}}
    .meta{{font-size:10px;color:#777;margin:3px 0 0 35px;overflow-wrap:anywhere;line-height:1.15}}
    .actions{{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:6px}}
    .btn{{border:0;border-radius:8px;padding:8px 7px;color:#fff;font-weight:800;text-decoration:none;cursor:pointer;text-align:center;font-size:12px;line-height:1.1}}
    .open{{background:#229ed9}} .good{{background:#2e9d53}} .badbatch{{background:#c64747}} .working{{background:#6b55c9}} .refresh{{background:#555;display:flex;align-items:center;justify-content:center}}
    .controls{{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #ddd;padding:7px 9px 8px;z-index:20;box-shadow:0 -3px 12px #0002}}
    .controls-inner{{max-width:760px;margin:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:7px}}
    .sendhint{{font-size:10px;color:#666;margin-top:5px;line-height:1.2}}
    .sourcebox{{font-size:10px;color:#666;background:#fff;border-radius:10px;padding:7px 8px;margin-top:8px;line-height:1.2}}
    .source-section{{font-size:12px;line-height:1.3;background:#eaf6ff;border:1px solid #b8ddf4;border-radius:10px;padding:9px 10px;margin:9px 0 6px}}
    .transport-tabs{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0}}
    .transport-tab{{border:0;border-radius:9px;padding:9px 5px;background:#e4e7eb;color:#3c4043;font-weight:800;font-size:12px;cursor:pointer}}
    .transport-tab.active{{background:#229ed9;color:#fff}}
    .transport-tab:disabled{{opacity:.55;cursor:not-allowed}}
    .access-hero{{background:#fff;border-radius:14px;padding:14px;margin:4px 0 14px;box-shadow:0 1px 8px #0001}}
    .access-title{{font-size:21px;font-weight:900;margin-bottom:5px}}
    .access-ok{{font-size:13px;font-weight:800;margin:8px 0;color:#1f7a43}}
    .access-steps{{font-size:12px;line-height:1.45;margin:8px 0;color:#444}}
    .download{{display:block;background:#229ed9;color:#fff;text-decoration:none;font-weight:900;text-align:center;border-radius:10px;padding:11px 10px;margin:10px 0 7px}}
    .access-note{{font-size:10px;line-height:1.35;color:#666}}
    .diag-title{{font-size:15px;font-weight:900;margin:15px 0 5px}}
    @media(max-width:520px){{
      body{{padding:8px 7px 105px}}
      h1{{font-size:18px}}
      .actions{{grid-template-columns:1fr 1fr}}
      .meta{{margin-left:0;font-size:9px}}
      .top{{grid-template-columns:28px 1fr auto}}
      .controls-inner{{grid-template-columns:repeat(3,1fr)}}
    }}
    </style></head><body>
    <section class="access-hero">
      <div class="access-title">Telegram — рабочий доступ</div>
      <div class="access-ok">✅ Рабочий маршрут: TgWsProxy → Cloudflare/WebSocket</div>
      <div class="access-steps">
        1. Установи TgWsProxy на Android.<br>
        2. Оставь основной маршрут <b>cf_proxy_ws</b>; свой Cloudflare Worker не обязателен.<br>
        3. Запусти локальный прокси и примени его в Telegram.<br>
        4. Если всё уже установлено и работает — просто запускай TgWsProxy перед Telegram.
      </div>
      <a class="download" href="https://github.com/Regstar2/tg-ws-proxy-android/releases/download/v1.11.0/TgWsProxy-Android-v1.11.0-arm64-v8a.apk">⬇ Скачать TgWsProxy для Samsung / Android</a>
      <div class="access-note">ARM64 · TgWsProxy v1.11.0 · официальный APK из GitHub Releases. Этот маршрут использует WebSocket/Cloudflare наружу; MTProto на странице ниже оставлен только как диагностика и резерв.</div>
    </section>

    <div class="diag-title">MTProto / SOCKS5 — диагностика и резерв</div>
    <div class="lead">Обновлено: {now}. Внешняя проверка MTProto означает только, что TCP-порт доступен. SOCKS5 попадает в выдачу только после handshake + CONNECT к Telegram. Реальную работу в твоей сети подтверждаешь ты.</div>
    <div class="transport-tabs">
      <button class="transport-tab" data-transport="mtproto">MTProto</button>
      <button class="transport-tab" data-transport="socks5">SOCKS5</button>
      <button class="transport-tab" data-transport="web" disabled>WEB · скоро</button>
    </div>
    <div class="progress" id="progress-summary">Открыто 0 · Работает 0 · Осталось 0</div>
    <div class="sourcebox" id="diagnostic-summary">Диагностика транспорта ещё не начата.</div>
    <div class="progress" id="progress">Загрузка...</div>
    {''.join(cards)}
    {socks_empty}
    <div class="sourcebox" id="learn-summary">Обучение: пока нет подтверждённых результатов.</div>
    <div class="sourcebox" id="source-summary">Статистика по источникам появится после первых оценок.</div>
    <div id="working-reserve" data-working-reserve style="display:none"></div>
    <div class="controls">
      <div class="controls-inner">
        <button class="btn badbatch" onclick="rejectCurrentBatch()">❌ 10 не работают</button>
        <button class="btn working" onclick="showWorking()">⭐ Рабочие</button>
        <a class="btn refresh" href="https://github.com/vldik-hue/mtproto-proxy-page/actions/workflows/update-page.yml" target="_blank" rel="noopener">🔄 Новый пул</a>
      </div>
      <div class="sendhint">Нерабочая десятка исчезнет сразу, и откроется следующая. Уже отмеченные «✅ Работает» не будут сброшены. «Новый пул сейчас» откроет GitHub Actions — там нажми Run workflow.</div>
    </div>
    <script type="module">
    import {{ loadFeedback, saveFeedback, recordFeedback, selectBatch, rejectBatch, workingReserve, poolStatus, loadInteractionState, saveInteractionState, markAttempted, isAttempted, transportProgress, activeTransport, setActiveTransport, candidatesForTransport, buildProxyLink, diagnosticStatus }} from './learning.js';

    const BATCH_SIZE=10;
    const GENERATED_AT='{generated_iso}';
    const SOCKS_FAILED_COPY='SOCKS5 не прошёл контрольный тест — не расширяем перебор; переходим к WEB.';
    const allCards=Array.from(document.querySelectorAll('[data-proxy-id]'));
    const candidates=allCards.map(card=>({{
      id:card.dataset.proxyId||'',
      server:card.dataset.server||'',
      port:card.dataset.port||'',
      source:card.dataset.source||'',
      domain:card.dataset.domain||'',
      secret:card.dataset.secret||'',
      user:card.dataset.user||'',
      pass:card.dataset.pass||'',
      kind:card.dataset.kind||'',
      protocol:card.dataset.protocol||'mtproto'
    }}));
    let feedback=loadFeedback(localStorage);
    let interaction=loadInteractionState(localStorage);
    let currentTransport=activeTransport(localStorage);
    if(currentTransport==='web') currentTransport='mtproto';

    function latestKind(id,protocol=currentTransport){{
      const e=(feedback.events||[]).find(x=>x.id===id && (x.protocol||'mtproto')===protocol);
      return e?e.kind:'';
    }}

    function scopedCandidates(){{
      return candidatesForTransport(candidates,currentTransport);
    }}

    function scopedCards(){{
      return allCards.filter(c=>(c.dataset.protocol||'mtproto')===currentTransport);
    }}

    function paintTabs(){{
      document.querySelectorAll('[data-transport]').forEach(btn=>{{
        btn.classList.toggle('active',btn.dataset.transport===currentTransport);
      }});
    }}

    let migrated=false;
    for(const card of allCards){{
      const id=card.dataset.proxyId;
      const legacy=localStorage.getItem('proxy-rating-'+id);
      if((legacy==='good'||legacy==='bad') && !latestKind(id,'mtproto')){{
        const candidate=scopedCandidates().find(x=>x.id===id);
        if(candidate){{
          feedback=recordFeedback(feedback,candidate,legacy,new Date().toISOString());
          migrated=true;
        }}
      }}
    }}
    if(migrated) saveFeedback(localStorage,feedback);

    function paint(id,v){{
      const e=document.getElementById('status-'+id);
      const card=allCards.find(c=>c.dataset.proxyId===id);
      if(!e||!card)return;
      const attempted=isAttempted(interaction,id,card.dataset.protocol||'mtproto');
      card.classList.toggle('attempted',attempted && v!=='good');
      e.textContent=v==='good'?'✓ рабочий':v==='bad'?'✕ нерабочий':attempted?'↗ Открыт':'';
      e.style.color=v==='good'?'#2e9d53':v==='bad'?'#c64747':attempted?'#386a8a':'#666';
    }}

    function markAttemptFromLink(card){{
      const id=card.dataset.proxyId;
      const protocol=card.dataset.protocol||'mtproto';
      interaction=markAttempted(interaction,id,protocol,new Date().toISOString());
      saveInteractionState(localStorage,interaction);
      paint(id,latestKind(id,protocol));
      updateProgressSummary();
    }}

    function updateProgressSummary(){{
      const p=transportProgress(candidates,feedback,interaction,currentTransport);
      const el=document.getElementById('progress-summary');
      if(el)el.textContent='Открыто '+p.attempted+' · Работает '+p.working+' · Осталось '+p.remaining;
      const d=diagnosticStatus(currentTransport,p);
      const diag=document.getElementById('diagnostic-summary');
      if(diag)diag.textContent=(currentTransport==='socks5' && d.status==='failed')?SOCKS_FAILED_COPY:d.message;
    }}

    function markWorking(id){{
      const candidate=candidates.find(x=>x.id===id);
      if(!candidate)return;
      if(latestKind(id,candidate.protocol||'mtproto')!=='good'){{
        feedback=recordFeedback(feedback,candidate,'good',new Date().toISOString());
        saveFeedback(localStorage,feedback);
      }}
      localStorage.setItem('proxy-rating-'+id,'good');
      paint(id,'good');
      renderBatch();
    }}

    function updateLearnSummary(){{
      const good=(feedback.events||[]).filter(e=>e.kind==='good' && (e.protocol||'mtproto')===currentTransport);
      const bad=(feedback.events||[]).filter(e=>e.kind==='bad' && (e.protocol||'mtproto')===currentTransport);
      const el=document.getElementById('learn-summary');
      if(!el)return;
      if(!good.length){{
        el.textContent='Обучение: подтверждённых рабочих пока нет · отбраковано '+bad.length;
        return;
      }}
      const ports={{}},sources={{}},domains={{}};
      good.forEach(e=>{{
        ports[e.port]=(ports[e.port]||0)+1;
        sources[e.source]=(sources[e.source]||0)+1;
        domains[e.domain]=(domains[e.domain]||0)+1;
      }});
      const top=o=>Object.entries(o).sort((a,b)=>b[1]-a[1])[0];
      const p=top(ports),s=top(sources),d=top(domains);
      el.innerHTML='<b>Обучение:</b> рабочих '+good.length+' · плохих '+bad.length+
        (p?' · лучший порт '+p[0]:'')+
        (s?' · источник '+s[0]:'')+
        (d?' · семья '+d[0]:'');
    }}

    function updateSourceSummary(){{
      const rows=[];
      for(const [key,stat] of Object.entries(feedback.stats||{{}})){{
        if(!key.startsWith('source:'))continue;
        rows.push([key.slice(7),stat.good||0,stat.bad||0]);
      }}
      rows.sort((a,b)=>(b[1]-b[2])-(a[1]-a[2]));
      const el=document.getElementById('source-summary');
      if(!el)return;
      if(!rows.length){{el.textContent='Статистика по источникам появится после первых оценок.';return;}}
      el.innerHTML='<b>Локально по источникам:</b> '+rows.map(r=>r[0]+': ✅ '+r[1]+' / ❌ '+r[2]).join(' · ');
    }}

    function renderBatch(){{
      const reserveBox=document.getElementById('working-reserve');
      if(reserveBox){{reserveBox.style.display='none';reserveBox.innerHTML='';}}
      const socksEmpty=document.getElementById('socks5-empty');
      if(socksEmpty)socksEmpty.style.display='none';
      allCards.forEach(c=>c.style.display='none');
      const prioritySection=document.querySelector('[data-priority-section="proxymtproto"]');
      if(prioritySection)prioritySection.style.display=currentTransport==='mtproto'?'block':'none';
      paintTabs();
      const scoped=scopedCandidates();
      const selected=selectBatch(scoped,feedback,BATCH_SIZE,Date.now(),interaction,currentTransport);
      if(!selected.length){{
        if(currentTransport==='socks5' && socksEmpty)socksEmpty.style.display='block';
        const status=poolStatus(scoped,feedback,GENERATED_AT,Date.now());
        const next=new Date(status.nextRefreshAt).toLocaleTimeString('ru-RU',{{hour:'2-digit',minute:'2-digit'}});
        const pr=document.getElementById('progress');
        if(pr)pr.textContent='Все кандидаты этого пула проверены · отбраковано '+status.rejected+' · Следующее автообновление около '+next;
        updateLearnSummary();
        updateSourceSummary();
        return;
      }}
      const ids=new Set(selected.map(x=>x.id));
      scopedCards().filter(c=>ids.has(c.dataset.proxyId)).forEach(c=>{{
        c.style.display='block';
        paint(c.dataset.proxyId,latestKind(c.dataset.proxyId,currentTransport));
      }});
      const badIds=new Set((feedback.events||[]).filter(e=>e.kind==='bad' && (e.protocol||'mtproto')===currentTransport).map(e=>e.id));
      const goodIds=new Set((feedback.events||[]).filter(e=>e.kind==='good' && (e.protocol||'mtproto')===currentTransport).map(e=>e.id));
      const pr=document.getElementById('progress');
      if(pr)pr.textContent='Сейчас '+selected.length+' · отбраковано '+badIds.size+' · рабочих '+goodIds.size+' · 8 лучших + 2 новых';
      updateLearnSummary();
      updateSourceSummary();
      updateProgressSummary();
    }}

    function rejectCurrentBatch(){{
      const visible=scopedCards().filter(c=>c.style.display!=='none');
      const ids=visible.map(c=>c.dataset.proxyId);
      feedback=rejectBatch(feedback,scopedCandidates(),ids,new Date().toISOString());
      for(const id of ids){{
        if(latestKind(id,currentTransport)==='bad' && currentTransport==='mtproto') localStorage.setItem('proxy-rating-'+id,'bad');
      }}
      saveFeedback(localStorage,feedback);
      renderBatch();
      window.scrollTo({{top:0,behavior:'smooth'}});
    }}

    function ageLabel(item){{
      if(item.ageBand==='today')return 'сегодня';
      if(item.ageBand==='yesterday')return 'вчера';
      if(item.ageBand==='recent'){{
        const days=Math.max(2,Math.floor((Date.now()-Date.parse(item.lastGoodAt))/86400000));
        return days+' дн. назад';
      }}
      return 'давно';
    }}

    function showWorking(){{
      allCards.forEach(c=>c.style.display='none');
      const box=document.getElementById('working-reserve');
      const scoped=scopedCandidates();
      const catalog=Object.fromEntries(scoped.map(x=>[x.id,x]));
      const reserve=workingReserve(feedback,catalog,Date.now(),currentTransport);
      if(!box)return;
      if(!reserve.length){{
        box.style.display='block';
        box.innerHTML='<div class="card"><b>Пока нет подтверждённых рабочих прокси.</b></div>';
        return;
      }}
      box.style.display='block';
      box.innerHTML=reserve.map(item=>{{
        const link=buildProxyLink(item);
        return '<div class="card" data-working-reserve-row>'+
          '<div class="top"><div class="num">⭐</div><div class="host">'+item.server+':'+item.port+'</div><span class="status">✓ '+item.goodCount+'×</span></div>'+
          '<div class="meta">'+item.protocol.toUpperCase()+' · '+item.source+' · работал: '+ageLabel(item)+'</div>'+
          '<div class="actions"><a class="btn open" href="'+link+'">▶ Подключить</a><button class="btn good" data-confirm-id="'+item.id+'">✅ Подтвердить</button></div>'+
          '</div>';
      }}).join('');
      box.querySelectorAll('[data-confirm-id]').forEach(btn=>{{
        btn.addEventListener('click',()=>confirmWorking(btn.dataset.confirmId));
      }});
    }}

    function confirmWorking(id){{
      const candidate=candidates.find(x=>x.id===id);
      if(!candidate)return;
      feedback=recordFeedback(feedback,candidate,'good',new Date().toISOString());
      saveFeedback(localStorage,feedback);
      localStorage.setItem('proxy-rating-'+id,'good');
      showWorking();
    }}

    document.querySelectorAll('[data-transport]:not([disabled])').forEach(btn=>{{
      btn.addEventListener('click',()=>{{
        currentTransport=btn.dataset.transport;
        setActiveTransport(localStorage,currentTransport);
        renderBatch();
      }});
    }});

    document.querySelectorAll('[data-attempt-link]').forEach(link=>{{
      link.addEventListener('click',()=>{{
        const card=link.closest('[data-proxy-id]');
        if(card) markAttemptFromLink(card);
      }});
    }});

    window.markWorking=markWorking;
    window.rejectCurrentBatch=rejectCurrentBatch;
    window.showWorking=showWorking;
    window.confirmWorking=confirmWorking;
    renderBatch();
    </script></body></html>'''
    Path("index.html").write_text(page,encoding="utf-8")

if __name__=="__main__":main()
