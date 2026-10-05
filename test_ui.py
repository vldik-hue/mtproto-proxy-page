#!/usr/bin/env python3
from pathlib import Path
import re

html = Path("index.html").read_text(encoding="utf-8")

m = re.search(r'<div class="controls-inner">(.*?)</div>', html, re.S)
assert m, "controls-inner block not found"
controls = m.group(1)

for label in ("❌ 10 не работают", "⭐ Рабочие", "🔄 Новый пул"):
    assert label in controls, f"missing compact control: {label}"

assert controls.count('class="btn ') == 3, "bottom panel must have exactly three equal controls in one row"
assert 'class="btn refresh"' not in html.replace(controls, ""), "refresh control must live inside controls-inner"

print("UI control layout OK")


assert 'id="working-reserve"' in html, "working reserve container must exist"
assert 'data-working-reserve' in html, "working reserve rows need a stable hook"
print("working reserve UI hooks OK")


assert 'Все кандидаты этого пула проверены' in html, "stable exhausted-pool copy must exist"
assert 'Следующее автообновление' in html, "exhausted state must show next refresh guidance"
print("exhausted pool UI copy OK")


assert "confirmWorking(''+item.id+'')" not in html, "generated reserve button quoting must not be malformed"
assert 'data-confirm-id' in html, "reserve confirmation must use data attribute hook"
print("working reserve confirm hook OK")


assert 'data-attempt-link' in html, "primary proxy action must expose an attempt hook"
assert '↗ Открыт' in html, "attempted badge copy must exist"
assert '.attempted' in html, "attempted card styling must exist"
assert 'Открыто ' in html and 'Работает ' in html and 'Осталось ' in html, "progress summary copy must exist"
print("attempted/progress UI hooks OK")


assert 'data-transport="mtproto"' in html, "MTProto tab must exist"
assert 'data-transport="socks5"' in html, "SOCKS5 tab must exist"
assert 'data-transport="web"' in html, "WEB tab must exist"
assert 'WEB · скоро' in html, "WEB tab must be visibly disabled/pending"
print("transport tabs UI hooks OK")


socks_count = len(re.findall(r'data-protocol="socks5"', html))
assert socks_count <= 10, f"SOCKS5 diagnostic pool must be capped at 10, got {socks_count}"
assert ('tg://socks?' in html) or ('SOCKS5: нет диагностических кандидатов' in html), "SOCKS5 mode must provide candidates or explicit empty state"
assert 'TCP доступен' in html, "external reachability must be labeled as TCP only"
print("SOCKS5 diagnostic UI constraints OK")


assert 'buildProxyLink(item)' in html, "working reserve must build transport-specific reconnect links"
assert "item.protocol.toUpperCase()" in html, "working reserve must show protocol label"
print("transport-aware working reserve UI OK")


assert 'id="diagnostic-summary"' in html, "transport diagnostic summary must exist"
assert 'SOCKS5 не прошёл контрольный тест' in html, "failed SOCKS5 diagnostic guidance must be wired into UI"
print("diagnostic decision UI OK")
