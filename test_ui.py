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
