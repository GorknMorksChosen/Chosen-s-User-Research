# -*- coding: utf-8 -*-
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _ROOT / "docs"
p = _DOCS / "wjxspss_extracted.txt"
s = p.read_text(encoding="utf-8")

# 找正文叙述句：较长且含句号，避免纯目录
sentences = re.split(r'[。！？\n]', s)
out = []
for sent in sentences:
    sent = re.sub(r'\s+', ' ', sent).strip()
    if len(sent) < 40 or len(sent) > 350:
        continue
    # 含流程/原则/条件相关表述
    if any(k in sent for k in [
        '先对数据', '先进行', '首先', '然后再', '再对数据', '适用条件', '满足',
        '正态分布', '方差齐性', '数据类型', '分析方法选择', '定类', '定量',
        '探索', '清理', '探索分析', '数据特征', '分布情况', '分析步骤', '一般步骤'
    ]) and '章' not in sent[:20] and not re.search(r'^\d+', sent):
        out.append(sent)
# 去重并限制数量
seen = set()
lines = []
for t in out:
    key = t[:80]
    if key in seen:
        continue
    seen.add(key)
    lines.append(t)
out_path = _DOCS / "wjxspss_principle_snippets.txt"
out_path.write_text('\n---\n'.join(lines[:35]), encoding='utf-8')
print('Wrote', len(lines), 'snippets to', out_path.name)
