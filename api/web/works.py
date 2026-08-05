from __future__ import annotations

from application.use_cases.works import WorkDetail
from domain.entities.work import Work
from infrastructure.config import Settings

from api.urls import build_resource_url
from api.web.base import base_page

_SEARCH_STYLE = """
 form { display:flex; gap:8px; margin:20px 0; }
 input[type=text] { flex:1; padding:12px; border-radius:8px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; }
 button { padding:12px 24px; border-radius:8px; border:0; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }
 table { width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }
 th,td { padding:10px 12px; text-align:left; border-bottom:1px solid #334155; }
 th { color:#94a3b8; font-weight:600; }
 .dl { color:#fff; background:#2563eb; padding:6px 12px; border-radius:6px; text-decoration:none; }
 .mono { font-family:ui-monospace,monospace; font-size:.85rem; color:#94a3b8; }
 .none { text-align:center; color:#64748b; padding:24px; }
 .no { color:#64748b; }
"""


def works_page(query: str, works: list[Work]) -> str:
    rows = ""
    for w in works:
        rows += (
            f"<tr><td><a href=\"/works/{w.id}\">{w.title or w.work_key or ''}</a></td>"
            f"<td>{w.composer or ''}</td><td>{w.catalogue or ''}</td></tr>"
        )
    if not rows:
        rows = '<tr><td colspan="3" class="none">No se encontraron obras.</td></tr>'
    body = f"""
<h1>Search works</h1>
<form method="get" action="/works">
  <input type="text" name="q" value="{query}" placeholder="Composer or title..." autofocus>
  <button type="submit">Search</button>
</form>
<table>
 <thead><tr><th>Title</th><th>Composer</th><th>Catalogue</th></tr></thead>
 <tbody>{rows}</tbody>
</table>"""
    return base_page("Works", body, extra_style=_SEARCH_STYLE)


def work_detail_page(detail: WorkDetail, settings: Settings) -> str:
    w = detail.work
    resources = ""
    for r in detail.resources:
        url, available = build_resource_url(r.relative_path, r.file_id, settings)
        btn = f'<a class="dl" href="{url}">Download</a>' if available else '<span class="no">No disponible</span>'
        resources += f"<tr><td>{r.format or ''}</td><td class='mono'>{r.relative_path}</td><td>{btn}</td></tr>"
    if not resources:
        resources = '<tr><td colspan="3" class="none">Sin representaciones.</td></tr>'
    meta = [
        ("Composer", w.composer),
        ("Genre", w.genre),
        ("Opus", w.opus),
        ("Catalogue", w.catalogue),
        ("Key", w.musical_key),
        ("Year", w.year),
        ("Instrumentation", w.instrumentation),
    ]
    meta_rows = "".join(f"<tr><td>{label}</td><td>{value or '—'}</td></tr>" for label, value in meta)
    body = f"""
<p><a href="/works">← Search works</a></p>
<h1>{w.title or w.work_key or 'Untitled'}</h1>
<h2>Representations</h2>
<table>
 <thead><tr><th>Format</th><th>Path</th><th></th></tr></thead>
 <tbody>{resources}</tbody>
</table>
<h2>Metadata</h2>
<table>
 <tbody>{meta_rows}</tbody>
</table>"""
    return base_page("Work", body, extra_style=_SEARCH_STYLE)
