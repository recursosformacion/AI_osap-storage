from __future__ import annotations

from api.web.base import base_page


def statistics_page(stats) -> str:
    rows = [
        ("Archives", stats.archives),
        ("Archive entries", stats.entries),
        ("Files indexed", stats.files),
        ("Downloaded mirrors", stats.downloaded_tar),
        ("Materialized", stats.materialized),
        ("Pending", stats.pending),
        ("Bytes", f"{stats.bytes:,}"),
        ("Repository size", f"{stats.bytes / 1e9:.1f} GB" if stats.bytes else "—"),
    ]
    table = "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in rows)
    body = f"""
<h1>Statistics</h1>
<table>
 <thead><tr><th>Metric</th><th>Value</th></tr></thead>
 <tbody>{table}</tbody>
</table>"""
    style = """
 table { width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }
 th,td { padding:10px 14px; text-align:left; border-bottom:1px solid #334155; }
 th { color:#94a3b8; font-weight:600; }
"""
    return base_page("Statistics", body, extra_style=style)
