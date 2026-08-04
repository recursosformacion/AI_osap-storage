from __future__ import annotations

from api.web.base import base_page


def api_page() -> str:
    body = """
<h1>API</h1>
<p>Open Music Repository provides a simple HTTP API for discovering and retrieving MusicXML
resources.</p>

<h2>Typical workflow: Search → Resolve → Download</h2>

<h3>1. Search</h3>
<pre>GET /api/v1/search?q=mozart</pre>
<p class="muted">Searches the repository by title, composer or keywords.</p>
<p class="muted">The response contains the matching works together with their metadata and
resource identifiers.</p>

<h3>2. Resolve a resource</h3>
<pre>GET /api/v1/entries/resolve?relative_path=mxl/1/30/QmbL2idE5ykZoHvUMVzTdEWQvmyPqgHA5C4UWET1tkjqUk.mxl</pre>
<p class="muted">Checks whether a resource is available and returns its metadata together with
the public download URL.</p>

<h3>3. Download</h3>
<pre>GET /api/v1/files/{id}/content</pre>
<p class="muted">Downloads the MusicXML file using a human-readable filename.</p>

<h2>Try the API</h2>
<p>
 <a href="/api/v1/search?q=mozart">Search for Mozart</a> ·
 <a href="/api/v1/entries/resolve?relative_path=./mxl/1/11/QmbbGKtZ9G6DkWxvSeU516c1ktWiFJmEbHGmR3JFtLAPyC.mxl">Resolve an example resource</a> ·
 <a href="/api/v1/statistics">View repository statistics</a>
</p>

<h2>Documentation</h2>
<p>Interactive API documentation: <a href="/docs">/docs</a></p>
<p>OpenAPI specification: <a href="/openapi.json">/openapi.json</a></p>

<footer><strong>OSAP Storage</strong> — the storage engine behind Open Music Repository.</footer>
"""
    return base_page("API", body)
