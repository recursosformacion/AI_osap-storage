from __future__ import annotations

# Hecho verificado del repositorio oficial (no depende del índice).
MIRROR_GB = "54 GB"

_LANDING_STYLE = """
 .tagline { color:#38bdf8; font-size:1.3rem; font-weight:600; }
 .sub { color:#94a3b8; font-size:1.1rem; max-width:640px; }
 .stats { display:flex; gap:20px; flex-wrap:wrap; margin:32px 0; }
 .stat { background:#1e293b; border-radius:12px; padding:22px; flex:1; min-width:170px; }
 .stat .num { font-size:1.8rem; font-weight:700; color:#38bdf8; }
 .stat .lbl { color:#94a3b8; font-size:.95rem; }
 .btn { display:inline-block; background:#2563eb; color:#fff; padding:14px 30px; border-radius:8px;
        text-decoration:none; margin:8px 10px 0 0; font-weight:600; }
 .btn.alt { background:#1e293b; border:1px solid #334155; }
 .search { margin:28px 0; max-width:640px; }
 .search form { display:flex; gap:10px; }
 .search input { flex:1; padding:16px 18px; border-radius:10px; border:1px solid #334155;
                 background:#1e293b; color:#e2e8f0; font-size:1.05rem; }
 .search button { padding:16px 32px; border-radius:10px; border:0; background:#2563eb;
                  color:#fff; font-weight:700; font-size:1.05rem; cursor:pointer; }
 .arch { text-align:center; background:#1e293b; border-radius:12px; padding:24px; }
 .layer { display:inline-block; background:#0f172a; border:1px solid #334155; border-radius:8px;
          padding:10px 22px; font-weight:600; }
 .arrow { color:#64748b; margin:6px 0; }
 .feat { columns:2; padding-left:18px; line-height:1.9; color:#cbd5e1; }
"""


def landing_page(*, musicxml: int, archives: int, sample_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open Music Repository</title>
<style>
 body {{ font-family: system-ui, -apple-system, sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }}
 .wrap {{ max-width: 920px; margin: 0 auto; padding: 48px 24px; }}
 h1 {{ font-size: 2.8rem; margin-bottom:.4rem; line-height:1.05; }}
{_LANDING_STYLE}
</style></head>
<body><div class="wrap">
  <h1>The Open Music Repository</h1>
  <p class="tagline">A permanent home for open MusicXML resources.</p>
  <p class="sub">Open Music Repository preserves and distributes public-domain and openly licensed
  musical scores through a stable API designed for software, education and research.</p>

  <div class="search">
    <form method="get" action="/search">
      <input type="text" name="q" placeholder="Search by composer, title or catalogue..." autofocus>
      <button type="submit">Search</button>
    </form>
  </div>

  <div>
    <a class="btn" href="/docs">API Documentation</a>
    <a class="btn alt" href="/statistics">Statistics</a>
  </div>

  <div class="stats">
    <div class="stat"><div class="num">{musicxml:,}</div><div class="lbl">MusicXML resources</div></div>
    <div class="stat"><div class="num">{archives}</div><div class="lbl">Collections</div></div>
    <div class="stat"><div class="num">{MIRROR_GB}</div><div class="lbl">Repository size</div></div>
    <div class="stat"><div class="num">Online</div><div class="lbl">API availability</div></div>
  </div>

  <h2>Architecture</h2>
  <div class="arch">
    <div class="layer">Clients</div>
    <div class="arrow">↓</div>
    <div class="layer">Open Music Repository API</div>
    <div class="arrow">↓</div>
    <div class="layer">Verified Repository</div>
  </div>

  <h2>Features</h2>
  <ul class="feat">
    <li>✓ HTTP API</li>
    <li>✓ Stable URLs</li>
    <li>✓ MusicXML</li>
    <li>✓ PDF</li>
    <li>✓ MIDI</li>
    <li>✓ Public domain resources</li>
    <li>✓ Open source</li>
  </ul>

  <p><a href="/about">About</a> · <a href="/api">API examples</a> · <a href="/api/v1/health">API status</a> ·
  <a href="/api/v1/statistics">Statistics</a> · <a href="/openapi.json">OpenAPI</a></p>

  <footer>
    <div><strong>OSAP Storage</strong> — the storage engine behind Open Music Repository.</div>
    <div>Version 1.0 · <a href="/api/v1/health">API status</a> · <a href="/docs">Documentation</a> ·
    Scores respect their original licenses.</div>
  </footer>
</div></body></html>"""
