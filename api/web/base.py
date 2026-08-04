from __future__ import annotations

BASE_STYLE = """
 body { font-family:system-ui, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
 .wrap { max-width:920px; margin:0 auto; padding:32px 20px; }
 h1 { font-size:1.9rem; }
 h2 { color:#f1f5f9; margin-top:28px; }
 a { color:#38bdf8; }
 a.back { color:#38bdf8; text-decoration:none; }
 code { background:#1e293b; padding:2px 6px; border-radius:6px; color:#93c5fd; font-size:.92em; }
 pre { background:#1e293b; padding:14px; border-radius:10px; overflow-x:auto; color:#93c5fd; }
 .muted { color:#94a3b8; }
 li { line-height:1.7; }
 footer { margin-top:36px; color:#64748b; font-size:.9rem; }
"""


def base_page(title: str, body: str, extra_style: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Open Music Repository</title>
<style>{BASE_STYLE}{extra_style}</style></head>
<body><div class="wrap">
 <p><a class="back" href="/">← Open Music Repository</a></p>
 {body}
</div></body></html>"""
