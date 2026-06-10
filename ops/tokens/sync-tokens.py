#!/usr/bin/env python3
"""Token sync: design-tokens.ts → CSS :root (injected into index.html)."""

import os, re, sys

ROOT = '/opt/efloud-bot'
TS_FILE = f'{ROOT}/u2algo-site/brand-kit/css/design-tokens.ts'
OUT_CSS = f'{ROOT}/u2algo-site/brand-kit/css/tokens-generated.css'
HTML_FILE = f'{ROOT}/u2algo-site/index.html'

def find_brace_block(text, start):
    """Find balanced {} starting at position `start` (index of opening '{')."""
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return start, i
        i += 1
    return None, None

def extract_export(source, name):
    """Return body string of `export const <name> = { ... }` (without outer braces)."""
    pattern = re.compile(r'export\s+const\s+' + name + r'\s*=\s*\{', re.DOTALL)
    m = pattern.search(source)
    if not m:
        return None
    open_idx = m.end() - 1
    _, close_idx = find_brace_block(source, open_idx)
    if close_idx is None:
        return None
    return source[m.end():close_idx]

def kebab(s):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', s).lower()

def parse_tokens(body):
    """Parse top-level props. Nested {from,to} -> flatten to 'parent-key'."""
    out = {}
    # Find property assignments (key: value)
    i = 0
    while i < len(body):
        # Match key:
        m = re.match(r'\s*(\w+)\s*:', body[i:])
        if not m:
            i += 1
            continue
        key = m.group(1)
        val_start = i + m.end()
        # Skip whitespace
        while val_start < len(body) and body[val_start] in ' \t':
            val_start += 1
        if val_start >= len(body):
            break
        c = body[val_start]
        if c in '"\'`':
            # String value
            quote = c
            end = body.find(quote, val_start + 1)
            if end == -1:
                i = val_start + 1
                continue
            out[kebab(key)] = body[val_start+1:end]
            i = end + 1
        elif c == '{':
            # Nested object
            _, close = find_brace_block(body, val_start)
            if close is None:
                i = val_start + 1
                continue
            nested_body = body[val_start+1:close]
            # Parse nested
            for nm in re.finditer(r'(\w+)\s*:\s*["\'`]([^"\'`]+)', nested_body):
                out[f'{kebab(key)}-{kebab(nm.group(1))}'] = nm.group(2)
            i = close + 1
        elif c.isdigit() or c == '-':
            # Number with possible unit
            nm = re.match(r'-?\d+(?:\.\d+)?(?:px|rem|%|em|s)?', body[val_start:])
            if nm:
                v = nm.group(0)
                if v[-1].isdigit():
                    v += 'px'
                out[kebab(key)] = v
                i = val_start + nm.end()
            else:
                i = val_start + 1
        else:
            i = val_start + 1
    return out

def main():
    with open(TS_FILE) as f:
        ts = f.read()

    colors_raw = extract_export(ts, 'colors')
    spacing_raw = extract_export(ts, 'spacing')
    radius_raw = extract_export(ts, 'radius')
    typography_raw = extract_export(ts, 'typography')

    if not colors_raw:
        print("ERROR: could not extract 'colors'", file=sys.stderr)
        return 1

    colors = parse_tokens(colors_raw) if colors_raw else {}
    spacing = parse_tokens(spacing_raw) if spacing_raw else {}
    radius = parse_tokens(radius_raw) if radius_raw else {}
    typography = parse_tokens(typography_raw) if typography_raw else {}

    print(f'Parsed: {len(colors)} colors, {len(spacing)} spacing, {len(radius)} radius, {len(typography)} typography')

    # Generate CSS
    lines = [
        ':root {',
        '  /* Legacy aliases (used by index.html inline styles) */',
        f'  --accent: {colors.get("cyan", "#00f0ff")};',
        f'  --accent-2: {colors.get("blue", "#0080ff")};',
        f'  --accent-3: {colors.get("purple", "#a855f7")};',
        f'  --success: {colors.get("green", "#00ff88")};',
        f'  --danger: {colors.get("red", "#ff3366")};',
        f'  --warn: {colors.get("yellow", "#ffaa00")};',
        f'  --ink: {colors.get("text-primary", "#f8fafc")};',
        f'  --muted: {colors.get("text-secondary", "#94a3b8")};',
        f'  --muted-2: {colors.get("text-muted", "#64748b")};',
        f'  --bg: {colors.get("surface-base", "#000000")};',
        f'  --surface: {colors.get("card-bg", "rgba(255,255,255,0.03)")};',
        f'  --surface-2: {colors.get("card-bg-hover", "rgba(255,255,255,0.05)")};',
        f'  --border: {colors.get("border-subtle", "rgba(255,255,255,0.05)")};',
        f'  --border-2: {colors.get("border-default", "rgba(255,255,255,0.1)")};',
        f'  --accent-dim: {colors.get("surface-overlay", "rgba(0,240,255,0.12)")};',
        '',
        '  /* u2 namespaced canonical */',
    ]
    for k, v in colors.items():
        if 'gradient' in k:
            continue
        lines.append(f'  --u2-{k}: {v};')
    lines.extend([
        '  --grad: linear-gradient(135deg, var(--u2-cyan), var(--u2-blue));',
        '  --grad-cta: linear-gradient(90deg, var(--u2-cyan), var(--u2-blue));',
        '  --grad-text: linear-gradient(90deg, var(--u2-cyan), var(--u2-blue) 50%, var(--u2-purple));',
        '',
        '  /* Spacing */',
    ])
    for k, v in spacing.items():
        lines.append(f'  --sp-{k}: {v};')
    lines.append('')
    lines.append('  /* Radius */')
    for k, v in radius.items():
        lines.append(f'  --radius-{k}: {v};')
    lines.append('')
    lines.append('  /* Font families */')
    for k, v in typography.items():
        lines.append(f'  --font-{k}: {v};')
    lines.append('}')

    css_text = '\n'.join(lines)
    with open(OUT_CSS, 'w') as f:
        f.write(css_text)
    print(f'✓ wrote {OUT_CSS}')

    # Inline into index.html: replace existing :root { ... } inside first <style>
    html = open(HTML_FILE).read()
    # Find :root{ ... } (note compact form: --bg:#...; on one line)
    root_re = re.compile(r'(\s*)<style>\s*:root\s*\{[^}]*\}', re.DOTALL)
    m = root_re.search(html)
    if m:
        indent = m.group(1)
        replacement = (
            f'{indent}<style>{indent}/* tokens injected by sync-tokens.py */{indent}'
            + css_text.replace('\n', f'{indent}  ')
            .replace('  ,', ',')
        )
        new_html = html[:m.start()] + replacement + f'{indent}' + html[m.end():len(html)]
        # Actually simpler: just replace the :root{...} portion
        new_html = html[:m.start()] + f'{indent}<style>' + html[m.end():]
        # Wait — m covers `<style>:root{...}`, so replace just `:root{...}` inside
        new_html = re.sub(
            r'(<style>\s*):root\s*\{[^}]*\}',
            lambda mm: mm.group(1) + '/* tokens injected by sync-tokens.py */\n' + css_text + '\n',
            html,
            count=1,
            flags=re.DOTALL,
        )
        if new_html != html:
            open(HTML_FILE, 'w').write(new_html)
            print(f'✓ injected into {HTML_FILE}')
        else:
            print('⚠ no change (regex did not match)')
    else:
        print('⚠ :root{...} not found in <style>')
    return 0

if __name__ == '__main__':
    sys.exit(main())
