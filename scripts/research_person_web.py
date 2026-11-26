"""Investigación web asistida para completar fichas de personas.

Complementa a Wikidata/RISM/VIAF (que solo cubren personas con identificador) con una
búsqueda web real y extracción estructurada de fuentes:

1. Busca en DuckDuckGo HTML el nombre y, si existe, una obra/colección representativa.
2. Descarga las fuentes de referencia (Tunearch, IMSLP, Wikipedia, HMS, Highland Music
   Trust, VIAF, Wikidata, RISM...).
3. Extrae datos con Groq (`openai/gpt-oss-120b`) usando SOLO el texto descargado.
4. Genera una propuesta con evidencias y URLs; por defecto no escribe nada.

Uso:
    .venv/bin/python scripts/research_person_web.py --person-id <uuid>
    .venv/bin/python scripts/research_person_web.py --person-id <uuid> --apply --allow-prod
    .venv/bin/python scripts/research_person_web.py --hidden-with-works --min-works 100 --limit 10

Requiere `secrets/groq.prod.key` o `GROQ_API_KEY` para la extracción.
"""

from __future__ import annotations

import argparse
import asyncio
import html as html_lib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, quote_plus, urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import PROJECT_ROOT, Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
DDG = "https://html.duckduckgo.com/html/?q={query}"
SOURCE_BOOST = {
    "tunearch.org": 10,
    "imslp.org": 9,
    "wikipedia.org": 8,
    "wikidata.org": 8,
    "viaf.org": 7,
    "hms.scot": 9,
    "highlandmusictrust.org": 8,
    "rism.online": 8,
    "musicbrainz.org": 6,
    "thesession.org": 4,
    "scoretail.com": 3,
}
AUTHORITATIVE = {
    "tunearch.org",
    "imslp.org",
    "wikipedia.org",
    "wikidata.org",
    "viaf.org",
    "hms.scot",
    "highlandmusictrust.org",
    "rism.online",
}
PLACEHOLDER_NAMES = {
    "anonymous", "anon", "anon.", "trad", "trad.", "traditional", "tradicional",
    "various", "composer", "unknown", "urheber unbekannt",
}
_QUOTED_PREFIX = re.compile(r"^\s*['\"“”‘’]([^'\"“”‘’]{1,80})['\"“”‘’]\s*(?=\S)")
_DATE_RANGE = re.compile(
    r"\b(1[5-9]\d{2}|20\d{2})\s*[–—−-]\s*(1[5-9]\d{2}|20\d{2})\b"
)
_BORN = re.compile(r"\b(?:born|naci[oó]|nacido)[^\d]{0,40}(1[5-9]\d{2}|20\d{2})", re.I)
_DIED = re.compile(r"\b(?:died|falleci[oó]|muere|murió)[^\d]{0,40}(1[5-9]\d{2}|20\d{2})", re.I)


@dataclass
class Source:
    title: str
    url: str
    text: str = ""


def _clean_name(name: str) -> str:
    text = _QUOTED_PREFIX.sub("", (name or "").strip())
    return re.sub(r"\s+", " ", text).strip()


def _is_placeholder(name: str) -> bool:
    low = _clean_name(name).lower().strip(" .,'\"")
    return not low or low in PLACEHOLDER_NAMES or low.startswith("urheber unbekannt")


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()


def _decode_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    target = parse_qs(parsed.query).get("uddg")
    return target[0] if target else href


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _score(url: str) -> int:
    host = _domain(url)
    for known, score in SOURCE_BOOST.items():
        if host == known or host.endswith("." + known):
            return score
    return 0


def name_variants(name: str) -> list[str]:
    """Variantes ortográficas típicas de apellidos Mac/Mc (MacIntosh/Mackintosh...)."""
    base = _clean_name(name)
    variants: list[str] = [base]
    parts = base.split()
    for index, part in enumerate(parts):
        low = part.casefold()
        match = re.match(r"^(mac|mc)k?(.+)$", low)
        if not match:
            continue
        rest = match.group(2)
        for prefix in ("Mac", "Mack", "Mc"):
            for suffix in (rest, rest.lower()):
                candidate = list(parts)
                candidate[index] = prefix + suffix
                variants.append(" ".join(candidate))
    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        key = variant.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(variant)
    return unique[:6]


def _name_tokens(name: str) -> list[str]:
    stop = {"composer", "compositor", "composer/a", "mrs", "miss", "sir", "dr"}
    return [
        token
        for token in re.findall(r"[^\W\d_]{3,}", _clean_name(name).casefold())
        if token not in stop
    ]


def _get_json(url: str, params: dict[str, str]) -> dict[str, Any] | None:
    try:
        response = httpx.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en,es;q=0.8"},
            timeout=25,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            return None
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


def _get_text(url: str) -> str:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en,es;q=0.8"},
            timeout=25,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            return ""
        return response.text
    except httpx.HTTPError:
        return ""


def imslp_sources(name: str) -> list[Source]:
    data = _get_json(
        "https://imslp.org/api.php",
        {"action": "query", "list": "search", "srsearch": name, "format": "json", "srlimit": "10"},
    )
    tokens = _name_tokens(name)
    found: dict[str, Source] = {}
    for item in (data or {}).get("query", {}).get("search", []):
        title = str(item.get("title") or "")
        match = re.search(r"\(([^,()]+),\s*([^()]+)\)$", title)
        if not match:
            continue
        surname, given = match.group(1).strip(), match.group(2).strip()
        haystack = f"{given} {surname}".casefold()
        if tokens and not any(token in haystack for token in tokens):
            continue
        category = f"Category:{surname}, {given}"
        url = "https://imslp.org/wiki/" + quote(category.replace(" ", "_"), safe="/,:()'")
        found[url] = Source(f"IMSLP {category}", url)
    return list(found.values())[:3]


def wikipedia_sources(name: str) -> list[Source]:
    data = _get_json(
        "https://en.wikipedia.org/w/api.php",
        {"action": "query", "list": "search", "srsearch": name, "format": "json", "srlimit": "5"},
    )
    tokens = _name_tokens(name)
    found: dict[str, Source] = {}
    for item in (data or {}).get("query", {}).get("search", []):
        title = str(item.get("title") or "")
        snippet = _strip_html(str(item.get("snippet") or ""))
        haystack = f"{title} {snippet}".casefold()
        if not tokens or not any(token in haystack for token in tokens):
            continue
        url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="/,:()'")
        found[url] = Source(title, url)
    return list(found.values())[:3]


def wikidata_sources(name: str) -> list[Source]:
    data = _get_json(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "uselang": "en",
            "format": "json",
            "limit": "5",
        },
    )
    tokens = _name_tokens(name)
    found: dict[str, Source] = {}
    for item in (data or {}).get("search", []):
        label = str(item.get("label") or "")
        description = str(item.get("description") or "")
        haystack = f"{label} {description}".casefold()
        if not tokens or not any(token in haystack for token in tokens):
            continue
        qid = str(item.get("id") or "")
        url = f"https://www.wikidata.org/wiki/{qid}"
        found[url] = Source(f"Wikidata {qid} — {label}", url, f"{label}: {description}")
    return list(found.values())[:3]


def highland_sources(name: str) -> list[Source]:
    surname = (_name_tokens(name) or [""])[-1]
    html = _get_text(f"https://www.highlandmusictrust.org/?s={quote_plus(name)}")
    if not html:
        return []
    found: dict[str, Source] = {}
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        if "highlandmusictrust.org" not in href and not href.startswith("/"):
            continue
        if surname and surname not in href.casefold() and surname not in _strip_html(text).casefold():
            continue
        url = str(httpx.URL("https://www.highlandmusictrust.org/").join(href))
        found[url] = Source(_strip_html(text) or url, url)
    return list(found.values())[:3]


def discover_sources(name: str) -> list[Source]:
    discovered: list[Source] = []
    for collector in (imslp_sources, wikipedia_sources, wikidata_sources, highland_sources):
        try:
            found = collector(name)
        except Exception as exc:  # una fuente caída no debe tumbar la investigación
            print(f"  {collector.__name__}: {exc}")
            continue
        if found:
            print(f"  {collector.__name__}: {len(found)} fuentes")
        discovered.extend(found)
    return discovered


def search_web(query: str, *, limit: int = 10) -> list[Source]:
    try:
        response = httpx.get(
            DDG.format(query=quote_plus(query)),
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es,en;q=0.8"},
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  búsqueda fallida: {exc}")
        return []
    results: list[Source] = []
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S
    )
    for href, title in pattern.findall(response.text):
        url = _decode_ddg(href)
        domain = _domain(url)
        if not url.startswith("http") or "openmusicrepository.com" in domain:
            continue
        results.append(Source(title=_strip_html(title), url=url))
        if len(results) >= limit:
            break
    return results


def fetch_sources(results: list[Source], *, max_pages: int = 5) -> list[Source]:
    ranked = sorted(results, key=lambda r: (-_score(r.url), r.url))
    fetched: list[Source] = []
    seen_domains: set[str] = set()
    for result in ranked:
        domain = _domain(result.url)
        if domain in seen_domains or result.url.lower().endswith(".pdf"):
            continue
        seen_domains.add(domain)
        if result.text:
            fetched.append(result)
            if len(fetched) >= max_pages:
                break
            continue
        try:
            response = httpx.get(
                result.url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "es,en;q=0.8"},
                timeout=25,
                follow_redirects=True,
            )
            if response.status_code >= 400:
                continue
            text = _strip_html(response.text)
            if len(text) < 200:
                continue
            fetched.append(Source(result.title, result.url, text[:12000]))
        except httpx.HTTPError:
            continue
        if len(fetched) >= max_pages:
            break
        time.sleep(0.5)
    return fetched


def _load_groq_key() -> str:
    env = os.environ.get("GROQ_API_KEY", "").strip()
    if env:
        return env
    key_file = PROJECT_ROOT / "secrets" / "groq.prod.key"
    if not key_file.exists():
        return ""
    for line in key_file.read_text(encoding="utf-8").splitlines():
        value = line.split("=", 1)[-1].strip() if "=" in line else line.strip()
        if value:
            return value
    return ""


def extract_with_groq(person: dict[str, Any], sources: list[Source], snippets: list[Source]) -> dict[str, Any]:
    key = _load_groq_key()
    if not key:
        raise RuntimeError("falta GROQ_API_KEY o secrets/groq.prod.key")
    corpus = []
    for source in sources:
        corpus.append(f"URL: {source.url}\nTITLE: {source.title}\nTEXT: {source.text[:6000]}")
    for snippet in snippets[:10]:
        corpus.append(f"RESULTADO: {snippet.title}\nURL: {snippet.url}")
    prompt = (
        "Eres un extractor de datos musicológicos. Usa SOLO el texto y las URLs "
        "proporcionados. No inventes. Devuelve JSON válido con las claves: "
        "birth_year (string de 4 dígitos o null), death_year (string de 4 dígitos o null), "
        "nationality (string corto o null), summary_es (2-4 frases en español, 120-600 caracteres), "
        "places (lista), publishers (lista), collections (lista), confidence (0-1), "
        "notes (string), evidence (lista de {fact, quote, url}). "
        "Si las fuentes discrepan en un dato, elige el valor de la fuente más autoritativa "
        "y explica la discrepancia en notes. Incluye la URL exacta en cada evidencia. "
        f"Persona: {json.dumps(person, ensure_ascii=False)}\n\n" + "\n\n".join(corpus)
    )
    body = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "Devuelve exclusivamente un objeto JSON válido."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1600,
        "response_format": {"type": "json_object"},
    }
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        json=body,
        timeout=90,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)


_NATIONALITY_ES = {
    "scottish": "Escocia",
    "english": "Inglaterra",
    "british": "Reino Unido",
    "irish": "Irlanda",
    "welsh": "Gales",
    "german": "Alemania",
    "austrian": "Austria",
    "french": "Francia",
    "italian": "Italia",
    "spanish": "España",
    "portuguese": "Portugal",
    "dutch": "Países Bajos",
    "belgian": "Bélgica",
    "russian": "Rusia",
    "polish": "Polonia",
    "czech": "Chequia",
    "hungarian": "Hungría",
    "american": "Estados Unidos",
    "united states": "Estados Unidos",
    "canadian": "Canadá",
}


def _nationality_es(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or len(text) > 60:
        return None
    return _NATIONALITY_ES.get(text.casefold(), text)


def _valid_year(value: Any) -> str | None:
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", str(value or ""))
    if not match:
        return None
    year = int(match.group(1))
    return str(year) if 1500 <= year <= datetime.now(UTC).year + 1 else None


def _valid_url(url: str, allowed: set[str]) -> bool:
    return url.startswith("http") and _domain(url) in allowed


def _existing_references(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, list):
        return [r if isinstance(r, dict) else {"source": str(r)} for r in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [r if isinstance(r, dict) else {"source": str(r)} for r in parsed]
        return [{"source": part.strip()} for part in re.split(r"[;\n]+", raw) if part.strip()]
    return []


def _merge_references(raw: Any, sources: list[Source]) -> str:
    refs = _existing_references(raw)
    seen = {str(r.get("url") or r.get("source") or "").lower() for r in refs}
    for source in sources:
        key = source.url.lower()
        if key in seen:
            continue
        refs.append({"source": f"{source.title} ({_domain(source.url)})", "url": source.url})
        seen.add(key)
    return json.dumps(refs, ensure_ascii=False)


async def load_person(db: Database, person_id: str) -> dict[str, Any] | None:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name, persons_visible, persons_birth_year, "
            "persons_death_year, persons_nationality, persons_biography_summary, "
            "persons_biography_nationality, persons_biography_references, persons_source_system, "
            "(SELECT COUNT(*) FROM works_person_roles r WHERE "
            "r.works_person_roles_person_id=p.persons_id AND r.works_person_roles_role_id=1) AS works "
            "FROM persons p WHERE persons_id=%s",
            (person_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        person = dict(row)
        await cur.execute(
            "SELECT DISTINCT w.works_title FROM works_person_roles r JOIN works w "
            "ON w.id=r.works_person_roles_work_id WHERE r.works_person_roles_person_id=%s "
            "AND r.works_person_roles_role_id=1 AND w.works_title IS NOT NULL LIMIT 8",
            (person_id,),
        )
        person["works_titles"] = [r["works_title"] for r in await cur.fetchall()]
        return person


async def list_hidden_with_works(db: Database, min_works: int, limit: int) -> list[dict[str, Any]]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT p.persons_id, p.persons_name, COUNT(DISTINCT r.works_person_roles_work_id) AS works "
            "FROM persons p JOIN works_person_roles r ON "
            "r.works_person_roles_person_id=p.persons_id AND r.works_person_roles_role_id=1 "
            "WHERE p.persons_visible=0 GROUP BY p.persons_id "
            "HAVING works >= %s ORDER BY works DESC LIMIT %s",
            (min_works, limit),
        )
        return [dict(r) for r in await cur.fetchall() if not _is_placeholder(r["persons_name"])]


def build_queries(person: dict[str, Any], name: str | None = None) -> list[str]:
    person_name = name or _clean_name(person["persons_name"])
    queries = [f'"{person_name}" composer']
    for title in person.get("works_titles", [])[:1]:
        if title:
            queries.append(f'"{person_name}" "{title}"')
    return queries


def research(person: dict[str, Any], *, verbose: bool = True) -> dict[str, Any] | None:
    name = _clean_name(person["persons_name"])
    if verbose:
        print(f"\n== {name} ({person['persons_id']}) — {person.get('works', 0)} obras")
    variants = name_variants(name)
    if verbose and len(variants) > 1:
        print(f"  variantes: {variants}")
    snippets: list[Source] = []
    for variant in variants:
        snippets.extend(discover_sources(variant))
        for query in build_queries(person, variant):
            results = search_web(query)
            if verbose:
                print(f"  query: {query} -> {len(results)} resultados")
            snippets.extend(results)
            if len(results) >= 5:
                break
            time.sleep(1.5)
        if any(_domain(source.url) in AUTHORITATIVE for source in snippets):
            break
    if not snippets:
        return None
    snippets = list({source.url: source for source in snippets}.values())
    pages = fetch_sources(snippets)
    if verbose:
        for page in pages:
            print(f"  fuente: {page.url} ({len(page.text)} chars)")
    try:
        extraction = extract_with_groq(
            {
                "name": name,
                "birth_year": person.get("persons_birth_year"),
                "death_year": person.get("persons_death_year"),
                "nationality": person.get("persons_nationality"),
                "works_titles": person.get("works_titles", []),
            },
            pages,
            snippets,
        )
    except Exception as exc:
        print(f"  extracción fallida: {exc}")
        return None
    allowed = {_domain(s.url) for s in pages} | {_domain(s.url) for s in snippets}
    birth = _valid_year(extraction.get("birth_year"))
    death = _valid_year(extraction.get("death_year"))
    if birth and death and int(birth) > int(death):
        birth = death = None
    evidence = [
        e for e in extraction.get("evidence", [])
        if isinstance(e, dict) and _valid_url(str(e.get("url") or ""), allowed)
    ]
    source_candidates = [*pages, *snippets]
    sources_by_url: dict[str, Source] = {}
    for candidate in source_candidates:
        if any(_domain(candidate.url) == _domain(str(e.get("url") or "")) for e in evidence):
            sources_by_url.setdefault(candidate.url, candidate)
    sources = list(sources_by_url.values())
    authoritative = any(_domain(s.url) in AUTHORITATIVE for s in sources)
    confidence = float(extraction.get("confidence") or 0)
    proposal = {
        "person_id": person["persons_id"],
        "name": name,
        "current": {
            "birth_year": person.get("persons_birth_year"),
            "death_year": person.get("persons_death_year"),
            "nationality": person.get("persons_nationality"),
            "summary": person.get("persons_biography_summary"),
        },
        "proposed": {
            "birth_year": birth,
            "death_year": death,
            "nationality": _nationality_es(extraction.get("nationality")),
            "summary": str(extraction.get("summary_es") or "").strip() or None,
            "places": extraction.get("places") or [],
            "publishers": extraction.get("publishers") or [],
            "collections": extraction.get("collections") or [],
        },
        "confidence": round(confidence, 3),
        "authoritative": authoritative,
        "notes": extraction.get("notes"),
        "sources": [{"title": s.title, "url": s.url} for s in sources],
        "evidence": evidence,
    }
    if verbose:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))
    return proposal


async def apply_proposal(db: Database, proposal: dict[str, Any], *, show: bool) -> bool:
    if proposal["confidence"] < 0.6 or not proposal["authoritative"]:
        print("  no se aplica: confianza insuficiente o sin fuente autoritativa")
        return False
    person_id = proposal["person_id"]
    current = proposal["current"]
    proposed = proposal["proposed"]
    updates: list[str] = []
    params: list[Any] = []
    birth = proposed["birth_year"] if not current["birth_year"] else None
    death = proposed["death_year"] if not current["death_year"] else None
    nationality = proposed["nationality"] if not current["nationality"] else None
    current_summary = str(current["summary"] or "")
    new_summary = proposed["summary"]
    summary = None
    if new_summary and (
        not current_summary
        or len(current_summary) < 120
        or (
            len(new_summary) > len(current_summary) + 60
            and re.search(r"\b1[5-9]\d{2}\b", new_summary)
            and not re.search(r"\b1[5-9]\d{2}\b", current_summary)
        )
    ):
        summary = new_summary
    if birth:
        updates.append("persons_birth_year=%s")
        params.append(birth)
    if death:
        updates.append("persons_death_year=%s")
        params.append(death)
    if nationality:
        updates.append("persons_nationality=%s")
        params.append(nationality)
        updates.append("persons_biography_nationality=%s")
        params.append(nationality)
    if summary:
        updates.append("persons_biography_summary=%s")
        params.append(summary)
    references = _merge_references(
        proposal.get("current_references"), [Source(s["title"], s["url"]) for s in proposal["sources"]]
    )
    updates.extend(["persons_biography_references=%s", "persons_updated_at=NOW(6)"])
    params.append(references)
    if show:
        updates.append("persons_visible=1")
    if not updates:
        print("  sin campos vacíos que completar")
        return False
    sql = f"UPDATE persons SET {', '.join(updates)} WHERE persons_id=%s"
    params.append(person_id)
    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        first_source = proposal["sources"][0] if proposal["sources"] else {"url": ""}
        await cur.execute(
            "INSERT INTO persons_evidence (persons_id, persons_evidence_rule, "
            "persons_evidence_decision, persons_evidence_reason, persons_evidence_anchor_type, "
            "persons_evidence_anchor_value, persons_evidence_channels, "
            "persons_evidence_identifiers_used, persons_evidence_matcher_version) "
            "VALUES (%s,'web-research','update','web_sources','url',%s,%s,%s,'web-research-v1')",
            (
                person_id,
                first_source["url"],
                json.dumps([s["url"] for s in proposal["sources"]], ensure_ascii=False),
                json.dumps(proposal["evidence"], ensure_ascii=False),
            ),
        )
        for source in proposal["sources"]:
            if _domain(source["url"]) == "imslp.org" and "/wiki/Category:" in source["url"]:
                value = source["url"].split("/wiki/", 1)[1]
                await cur.execute(
                    "INSERT IGNORE INTO persons_identity (persons_id, identity_name, "
                    "identity_name_norm, identity_type, identity_value, identity_source, "
                    "identity_is_anchor, identity_confidence, identity_retrieved_at) "
                    "VALUES (%s,%s,%s,'imslp',%s,'web-research',0,%s,NOW(6))",
                    (
                        person_id,
                        proposal["name"],
                        proposal["name"].casefold(),
                        value,
                        proposal["confidence"],
                    ),
                )
    print("  aplicado")
    return True


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()
    db = Database(settings.model_copy(update={"db_name": args.db}))
    await db.connect()
    if args.hidden_with_works:
        people = await list_hidden_with_works(db, args.min_works, args.limit)
    else:
        people = []
        for person_id in args.person_id or []:
            person = await load_person(db, person_id)
            if person:
                people.append(person)
    proposals = []
    for person in people:
        proposal = research(person)
        if proposal is None:
            continue
        if args.apply:
            if not args.allow_prod:
                print("  --apply requiere --allow-prod")
                continue
            proposal["current_references"] = person.get("persons_biography_references")
            await apply_proposal(db, proposal, show=args.show)
        proposals.append(proposal)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"propuestas: {path}")
    await db.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person-id", action="append", help="UUID de persona (repetible)")
    parser.add_argument("--hidden-with-works", action="store_true")
    parser.add_argument("--min-works", type=int, default=100)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--db", default="osap_storage")
    parser.add_argument("--json-out")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-prod", action="store_true")
    parser.add_argument("--show", action="store_true", help="Hacer visible la persona si se aplica")
    args = parser.parse_args()
    if not args.person_id and not args.hidden_with_works:
        parser.error("indica --person-id o --hidden-with-works")
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()


