from __future__ import annotations

from api.web.base import base_page


def about_page() -> str:
    body = """
<h1>Open Music Repository</h1>
<p>Open Music Repository is an open infrastructure for discovering, preserving and distributing
MusicXML resources.</p>
<p>It provides reliable access to public-domain and openly licensed musical scores through a stable
HTTP API designed for software developers, educators, researchers and musicians.</p>

<h2>Why it exists</h2>
<p>Finding editable musical scores in MusicXML format is often more difficult than finding PDFs or
scanned documents.</p>
<p>Although many repositories contain valuable collections, they usually focus on a single source or
provide limited programmatic access.</p>
<p>Open Music Repository brings these resources together behind a single, stable interface, making
MusicXML files easy to discover and use.</p>

<h2>What it offers</h2>
<ul>
  <li>A verified mirror of the PDMX collection containing 254,035 MusicXML scores.</li>
  <li>A stable HTTP API for searching, resolving and downloading resources.</li>
  <li>Direct access to MusicXML, PDF and MIDI files.</li>
  <li>Fast worldwide delivery through a CDN.</li>
  <li>Stable resource identifiers designed for long-term applications.</li>
</ul>

<h2>Philosophy</h2>
<p>Open Music Repository is built around a few simple principles:</p>
<ul>
  <li>Respect original licenses and copyright information.</li>
  <li>Preserve public-domain and openly licensed collections.</li>
  <li>Use open standards and documented APIs.</li>
  <li>Provide long-term stability for applications that depend on MusicXML resources.</li>
  <li>Remain independent of any specific software vendor or platform.</li>
</ul>

<h2>Relationship with OSAP</h2>
<p>Open Music Repository is the public repository and distribution service.</p>
<p>OSAP is an intelligent client that uses this repository to discover and obtain musical resources.</p>
<p>Although OSAP is one consumer of the service, any application can use the API directly.</p>

<h2>Technology</h2>
<p>Open Music Repository is powered by <strong>OSAP Storage</strong>, a storage engine specifically
designed to manage, index and distribute large MusicXML collections efficiently.</p>

<footer><strong>OSAP Storage</strong> — the storage engine behind Open Music Repository.</footer>
"""
    return base_page("About", body)
