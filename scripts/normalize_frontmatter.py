# scripts/normalize_frontmatter.py
# Usage:
#   python scripts/normalize_frontmatter.py --write      # écrit les corrections
#   python scripts/normalize_frontmatter.py              # dry-run (aperçu)

import re, os, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INLINE_LIST_KEYS = {"tags","districts","dirigeants","ressources"}
FRONTMATTER_RE = re.compile(r'^---\r?\n(.*?)\r?\n---\r?\n', re.DOTALL)

def to_block_list(items):
    out = []
    for it in items:
        it = it.strip().strip('"').strip("'")
        # préserve les liens Obsidian tels quels
        if it.startswith('[[') and it.endswith(']]'):
            out.append(f"  - '[[{it[2:-2]}]]'")
        else:
            out.append(f"  - {it}")
    return "\n".join(out)

def fix_inline_lists(yaml):
    # ex: "tags: [a, b, '[[Link]]']"
    def repl(m):
        key = m.group(1)
        body = m.group(2)
        # essaie de parser comme JSON light
        try:
            arr = json.loads("["+body+"]")
            items = []
            for v in arr:
                s = str(v)
                if isinstance(v, str):
                    s = v
                items.append(s)
        except Exception:
            # fallback split simple
            items = [x.strip() for x in body.split(",")]
        return f"{key}:\n{to_block_list(items)}"
    # applique sur toutes les clés inline
    for key in INLINE_LIST_KEYS:
        yaml = re.sub(
            rf'^({re.escape(key)}):\s*\[(.*?)\]\s*$', repl,
            yaml, flags=re.MULTILINE)
    return yaml

def fix_liens(json_like):
    """
    Convertit liens: {...} ou liens: { key:[...], key:'...' } vers block-style
    """
    # retire { } externes
    inner = json_like.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    # split virgules de premier niveau (cas simples attendus ici)
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    mapping = {}
    for p in parts:
        if ":" not in p: 
            continue
        k, v = p.split(":", 1)
        key = k.strip().strip('"').strip("'")
        val = v.strip()
        # liste JSON ?
        if val.startswith("["):
            try:
                arr = json.loads(val)
            except Exception:
                arr = [val]
            mapping[key] = [str(x) for x in arr]
        else:
            val = val.strip('"').strip("'")
            mapping[key] = [val]  # on normalise tout en liste
    # reconstruit block-style
    lines = ["liens:"]
    for k, arr in mapping.items():
        lines.append(f"  {k}:")
        for it in arr:
            s = str(it)
            # si c'est déjà [[...]], garde tel quel
            if s.startswith('[[') and s.endswith(']]'):
                lines.append(f"    - '{s}'")
            else:
                lines.append(f"    - {s}")
    return "\n".join(lines)

def normalize_yaml_block(fm_text):
    # 1) corrige listes inline
    fm_text = fix_inline_lists(fm_text)

    # 2) corrige liens JSON-like sur une seule ligne: liens: {...}
    fm_text = re.sub(
        r'^liens:\s*\{(.*)\}\s*$',
        lambda m: fix_liens("{"+m.group(1)+"}"),
        fm_text, flags=re.MULTILINE)

    # 3) corrige sous-listes inline dans liens (ex: "ville: [".."]")
    def fix_nested_inline(m):
        key = m.group(1)
        body = m.group(2)
        try:
            arr = json.loads("["+body+"]")
            items = [str(x) for x in arr]
        except Exception:
            items = [x.strip() for x in body.split(",")]
        return f"  {key}:\n" + "\n".join(f"    - '{i}'" if i.startswith('[[') else f"    - {i}" for i in items)

    fm_text = re.sub(
        r'^\s{0,2}(\w+):\s*\[(.*?)\]\s*$',
        fix_nested_inline, fm_text, flags=re.MULTILINE)

    return fm_text

def process_file(p: Path, write=False):
    t = p.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.search(t)
    if not m: 
        return False, "no-frontmatter"
    fm = m.group(1)
    newfm = normalize_yaml_block(fm)
    if newfm == fm:
        return False, "ok"
    new_text = t[:m.start()] + "---\n" + newfm + "\n---\n" + t[m.end():]
    if write:
        p.write_text(new_text, encoding="utf-8")
    return True, "changed"

def main():
    write = "--write" in sys.argv
    changed = 0
    for p in ROOT.rglob("*.md"):
        if ".obsidian" in p.parts:
            continue
        did, status = process_file(p, write=write)
        if did:
            changed += 1
            print(f"[fix] {p}")
    print(f"\nDone. Files changed: {changed}. Mode: {'write' if write else 'dry-run'}")

if __name__ == "__main__":
    main()
