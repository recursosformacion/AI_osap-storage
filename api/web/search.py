from __future__ import annotations

from application.use_cases.resolve_file import Resolution
from infrastructure.config import Settings

from api.urls import build_resolution_url
from api.web.base import base_page


def search_page(query: str, results: list[Resolution], settings: Settings) -> str:
    rows = ""
    for r in results:
        available, url = build_resolution_url(r, settings)
        btn = f'<a class="dl" href="{url}">Download</a>' if available else '<span class="no">No disponible</span>'
        title = r.title or r.logical_id or ""
        composer = r.composer or ""
        rows += f"<tr><td>{title}</td><td>{composer}</td><td>{btn}</td></tr>"
    if not rows:
        rows = '<tr><td colspan="3" class="none">No se encontraron resultados.</td></tr>'

    body = f"""
<h1>Search scores</h1>
<form method="get" action="/search">
  <input type="text" name="q" value="{query}" placeholder="Composer, title or catalogue..." autofocus>
  <button type="submit">Search</button>
</form>
<table>
 <thead><tr><th>Title</th><th>Composer</th><th></th></tr></thead>
 <tbody>{rows}</tbody>
</table>"""
    style = """
 form { display:flex; gap:8px; margin:20px 0; }
 input[type=text] { flex:1; padding:12px; border-radius:8px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; }
 button { padding:12px 24px; border-radius:8px; border:0; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }
 table { width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }
 th,td { padding:10px 12px; text-align:left; border-bottom:1px solid #334155; }
 th { color:#94a3b8; font-weight:600; }
 .dl { color:#fff; background:#2563eb; padding:6px 12px; border-radius:6px; text-decoration:none; }
 .no { color:#64748b; }
 .none { text-align:center; color:#64748b; padding:24px; }
"""
    return base_page("Search", body, extra_style=style)
