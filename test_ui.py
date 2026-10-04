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
