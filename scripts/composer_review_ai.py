"""
Script de revisión y enriquecimiento de compositores por IA.

Fases:
  1. Test en desarrollo (N registros) -> genera JSON para validación
  2. Ejecución completa en desarrollo (ignora review_status, crea biografía si corresponde)
  3. Ejecución completa en producción

Uso:
  python scripts/composer_review_ai.py phase1 --limit 50
  python scripts/composer_review_ai.py phase2
  python scripts/composer_review_ai.py phase3 --config config.production.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiomysql
import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent


def load_config(config_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    db = data.get("db") or {}
    if not db:
        raise ValueError(f"No se encontró la sección [db] en {config_path}")
    return db


def get_connection(db_config: dict[str, Any]):
    return aiomysql.connect(
        host=db_config.get("host", "127.0.0.1"),
        port=int(db_config.get("port", 3306)),
        user=db_config.get("user", ""),
        password=db_config.get("password", ""),
        db=db_config.get("name", ""),
        charset="utf8mb4",
        cursorclass=aiomysql.DictCursor,
        autocommit=True,
    )


CREATE_BIO_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS composer_biographies (
    composer_id CHAR(36) PRIMARY KEY,
    biography_summary TEXT,
    biography_era TEXT,
    biography_nationality TEXT,
    biography_key_works JSON,
    biography_key_fact TEXT,
    biography_references JSON,
    biography_updated_at VARCHAR(64),
    CONSTRAINT fk_composer_bio FOREIGN KEY (composer_id) REFERENCES composers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

ALTER_BIO_TABLE_SQL = """
ALTER TABLE composer_biographies
    MODIFY biography_summary TEXT,
    MODIFY biography_era TEXT,
    MODIFY biography_nationality TEXT,
    MODIFY biography_key_fact TEXT,
    ADD COLUMN biography_references JSON NULL
"""


async def ensure_bio_table(conn: aiomysql.Connection) -> None:
    async with conn.cursor() as cur:
        await cur.execute(CREATE_BIO_TABLE_SQL)
        # Amplía columnas de la tabla ya existente (versiones anteriores usaban
        # VARCHAR(64)/VARCHAR(255) y las descriptions de Wikidata los desbordan).
        with contextlib.suppress(Exception):
            await cur.execute(ALTER_BIO_TABLE_SQL)


async def count_pending(conn: aiomysql.Connection) -> int:
    query = """
        SELECT COUNT(*) as total
        FROM composers c
        WHERE c.status IN ('active', 'candidate')
          AND NOT EXISTS (
              SELECT 1 FROM composer_biographies b WHERE b.composer_id = c.id
          )
    """
    async with conn.cursor() as cur:
        await cur.execute(query)
        row = await cur.fetchone()
        return int(row["total"]) if row else 0


async def fetch_pending_composers(
    conn: aiomysql.Connection,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Obtiene compositores (active + candidate) sin biografía, ignorando review_status."""
    query = """
        SELECT c.id, c.name, c.review_status, c.review_reason, c.status
        FROM composers c
        WHERE c.status IN ('active', 'candidate')
          AND NOT EXISTS (
              SELECT 1 FROM composer_biographies b WHERE b.composer_id = c.id
          )
        ORDER BY c.id
        LIMIT %s OFFSET %s
    """
    async with conn.cursor() as cur:
        await cur.execute(query, (limit, offset))
        return await cur.fetchall()


async def update_composer_review(
    conn: aiomysql.Connection,
    composer_id: str,
    review_status: str,
    review_reason: str | None,
    reviewed_at: str | None,
) -> None:
    if review_status == "review_required":
        query = """
            UPDATE composers
            SET review_status = %s,
                reviewed_at = NULL
            WHERE id = %s
        """
        params = (review_status, composer_id)
    else:
        query = """
            UPDATE composers
            SET review_status = %s,
                review_reason = %s,
                reviewed_at = %s
            WHERE id = %s
        """
        params = (review_status, review_reason, reviewed_at, composer_id)
    async with conn.cursor() as cur:
        await cur.execute(query, params)


async def _set_active(conn: aiomysql.Connection, composer_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE composers SET status = 'active' WHERE id = %s",
            (composer_id,),
        )


async def upsert_biography(
    conn: aiomysql.Connection,
    composer_id: str,
    bio: dict[str, Any] | None,
) -> None:
    import json as _json
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    if bio is None:
        return

    query = """
        INSERT INTO composer_biographies
            (composer_id, biography_summary, biography_era, biography_nationality,
             biography_key_works, biography_key_fact, biography_references, biography_updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            biography_summary = VALUES(biography_summary),
            biography_era = VALUES(biography_era),
            biography_nationality = VALUES(biography_nationality),
            biography_key_works = VALUES(biography_key_works),
            biography_key_fact = VALUES(biography_key_fact),
            biography_references = VALUES(biography_references),
            biography_updated_at = VALUES(biography_updated_at)
    """
    params = (
        composer_id,
        bio.get("summary"),
        bio.get("era"),
        bio.get("nationality"),
        _json.dumps(bio.get("key_works", []), ensure_ascii=False),
        bio.get("key_fact"),
        _json.dumps(bio.get("references", []), ensure_ascii=False),
        now_str,
    )
    async with conn.cursor() as cur:
        await cur.execute(query, params)


WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_UA = {"User-Agent": "OSAP-Composer-Review/1.0 (https://openmusicrepository.com; admin@openmusicrepository.com)"}
CACHE_PATH = SCRIPT_DIR / "composer_search_cache.json"


def _load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        # Descarta entradas vacías (None): no deben bloquear reintentos futuros.
        return {k: v for k, v in data.items() if v}
    except Exception:
        return {}


def _save_cache(cache: dict[str, dict[str, Any]]) -> None:
    with contextlib.suppress(Exception):
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


_search_cache: dict[str, dict[str, Any]] = _load_cache()


def _format_life_span(life_span: dict[str, Any] | None) -> str:
    begin = (life_span or {}).get("begin", "?")
    end = (life_span or {}).get("end", "")
    if end:
        return f"{begin} - {end}"
    return str(begin)


async def _search_musicbrainz(name: str, delay: float = 1.0) -> dict[str, Any] | None:
    cache_key = f"mb:{name.lower()}"
    if cache_key in _search_cache:
        return _search_cache[cache_key] or None

    await asyncio.sleep(delay)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"{MUSICBRAINZ_API}/artist",
                params={"query": f'artist:"{name}"', "fmt": "json", "limit": "5"},
                headers=_UA,
            )
            resp.raise_for_status()
            data = resp.json()
            artists = data.get("artists", [])
            if not artists:
                return None

            artist = artists[0]
            if artist.get("type") not in {"Person", "Group", None}:
                return None

            relations = artist.get("relations", [])
            is_composer = any(
                r.get("type") == "composer" for r in relations
            ) or "composer" in (artist.get("disambiguation", "") or "").lower()

            if not is_composer and artist.get("type") != "Person":
                return None

            result = {
                "musicbrainz_id": artist.get("id"),
                "url": f"https://musicbrainz.org/artist/{artist.get('id')}",
                "name": artist.get("name", name),
                "type": artist.get("type"),
                "gender": artist.get("gender"),
                "country": artist.get("country"),
                "life_span": _format_life_span(artist.get("life-span")),
                "is_composer_hint": is_composer,
            }
            _search_cache[cache_key] = result
            _save_cache(_search_cache)
            return result
        except Exception:
            return None


async def _search_wikidata(name: str, delay: float = 1.0) -> dict[str, Any] | None:
    cache_key = f"wd:{name.lower()}"
    if cache_key in _search_cache:
        return _search_cache[cache_key] or None

    await asyncio.sleep(delay)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            search_params = {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "format": "json",
                "limit": "1",
            }
            resp = await client.get(WIKIDATA_API, params=search_params, headers=_UA)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("search", [])
            if not results:
                return None

            entity = results[0]
            entity_id = entity.get("id")
            if not entity_id:
                return None

            entity_params = {
                "action": "wbgetentities",
                "ids": entity_id,
                "languages": "en",
                "format": "json",
            }
            entity_resp = await client.get(WIKIDATA_API, params=entity_params, headers=_UA)
            entity_resp.raise_for_status()
            entity_data = entity_resp.json()
            entity_info = entity_data.get("entities", {}).get(entity_id, {})

            claims = entity_info.get("claims", {})

            def get_claim(prop: str) -> str | None:
                vals = claims.get(prop, [])
                if not vals:
                    return None
                main = vals[0].get("mainsnak", {})
                datavalue = main.get("datavalue", {})
                if datavalue.get("type") == "wikibase-entityid":
                    qid = datavalue.get("value", {}).get("id", "")
                    return qid
                return datavalue.get("value")

            occupation_claims = claims.get("P106", [])
            occupations = []
            for occ in occupation_claims:
                main = occ.get("mainsnak", {})
                dv = main.get("datavalue", {})
                if dv.get("type") == "wikibase-entityid":
                    occupations.append(dv.get("value", {}).get("id", ""))

            is_composer = "Q36834" in occupations

            country = get_claim("P27")
            country_label = None
            if country:
                country_resp = await client.get(
                    WIKIDATA_API,
                    params={
                        "action": "wbgetentities",
                        "ids": country,
                        "languages": "en",
                        "format": "json",
                        "props": "labels",
                    },
                    headers=_UA,
                )
                country_resp.raise_for_status()
                country_data = country_resp.json()
                country_label = (
                    country_data.get("entities", {})
                    .get(country, {})
                    .get("labels", {})
                    .get("en", {})
                    .get("value")
                )

            birth_date = get_claim("P569")
            birth_str = None
            if isinstance(birth_date, dict):
                birth_str = birth_date.get("time", "").lstrip("+").split("T")[0]
            elif isinstance(birth_date, str):
                birth_str = birth_date

            death_date = get_claim("P570")
            death_str = None
            if isinstance(death_date, dict):
                death_str = death_date.get("time", "").lstrip("+").split("T")[0]
            elif isinstance(death_date, str):
                death_str = death_date

            result = {
                "entity_id": entity_id,
                "url": f"https://www.wikidata.org/wiki/{entity_id}",
                "description": entity.get("description", ""),
                "is_composer": is_composer,
                "country": country_label,
                "birth_date": birth_str,
                "death_date": death_str,
                "occupations": occupations[:5],
            }
            _search_cache[cache_key] = result
            _save_cache(_search_cache)
            return result
        except Exception:
            return None


async def _search_wikipedia(name: str, delay: float = 1.0) -> dict[str, Any] | None:
    cache_key = f"wiki:{name.lower()}"
    if cache_key in _search_cache:
        return _search_cache[cache_key] or None

    await asyncio.sleep(delay)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": name,
                "format": "json",
                "srlimit": 1,
                "srprop": "snippet",
            }
            resp = await client.get(WIKI_SEARCH_URL, params=search_params, headers=_UA)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("query", {}).get("search", [])
            if not results:
                return None

            title = results[0]["title"]
            summary_resp = await client.get(f"{WIKI_SUMMARY_URL}/{urllib.parse.quote(title)}", headers=_UA)
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()

            extract = summary_data.get("extract", "")
            if not extract:
                return None

            description = summary_data.get("description", "")
            lower_extract = extract.lower()
            composer_keywords = [
                "composer", "compositor", "musician", "pianist", "conductor",
                "orchestra", "opera", "symphony", "classical", "baroque",
                "romantic", "renaissance", "medieval", "jazz", "soundtrack",
            ]
            if not any(kw in lower_extract for kw in composer_keywords):
                return None

            result = {
                "summary": extract,
                "era": description or "N/A",
                "nationality": summary_data.get("description", "N/A") or "N/A",
                "url": (
                    (summary_data.get("content_urls") or {}).get("desktop") or {}
                ).get("page") or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                "key_works": [],
                "key_fact": description or "",
            }
            _search_cache[cache_key] = result
            _save_cache(_search_cache)
            return result
        except Exception:
            return None


# ============================================================================
# MEJORA DE CALIDAD DE BIOGRAFÍAS (heurísticas deterministas, sin llamadas extra)
# ============================================================================

# Época musical según año de nacimiento (aproximación estándar).
_ERA_BY_YEAR: list[tuple[int, str]] = [
    (1945, "Contemporáneo"),
    (1900, "Moderno"),
    (1810, "Romántico"),
    (1750, "Clásico"),
    (1600, "Barroco"),
    (1400, "Renacimiento"),
    (0, "Medieval"),
]

# Palabras en la descripción de Wikidata/Wikipedia que delatan la época.
_ERA_DESCRIPTION_MAP: dict[str, str] = {
    "baroque": "Barroco",
    "romantic": "Romántico",
    "renaissance": "Renacimiento",
    "classical": "Clásico",
    "medieval": "Medieval",
    "contemporary": "Contemporáneo",
    "modernist": "Moderno",
    "20th-century": "Moderno",
    "21st-century": "Contemporáneo",
    "avant-garde": "Moderno",
    "barroco": "Barroco",
    "romantico": "Romántico",
    "renacimiento": "Renacimiento",
    "clasico": "Clásico",
    "contemporaneo": "Contemporáneo",
}

# Código de país ISO 3166-1 alpha-2 -> nombre legible.
_COUNTRY_NAMES: dict[str, str] = {
    "DE": "Alemania", "AT": "Austria", "CH": "Suiza", "IT": "Italia",
    "FR": "Francia", "ES": "España", "PT": "Portugal", "GB": "Reino Unido",
    "US": "Estados Unidos", "CA": "Canadá", "MX": "México", "AR": "Argentina",
    "BR": "Brasil", "CL": "Chile", "CO": "Colombia", "PE": "Perú", "UY": "Uruguay",
    "CU": "Cuba", "VE": "Venezuela", "EC": "Ecuador", "BO": "Bolivia",
    "PY": "Paraguay", "CR": "Costa Rica", "PA": "Panamá", "DO": "República Dominicana",
    "JP": "Japón", "CN": "China", "KR": "Corea del Sur", "IN": "India",
    "RU": "Rusia", "UA": "Ucrania", "PL": "Polonia", "CZ": "República Checa",
    "HU": "Hungría", "RO": "Rumanía", "BG": "Bulgaria", "GR": "Grecia",
    "NO": "Noruega", "SE": "Suecia", "DK": "Dinamarca", "FI": "Finlandia",
    "NL": "Países Bajos", "BE": "Bélgica", "IE": "Irlanda", "IS": "Islandia",
    "TR": "Turquía", "IL": "Israel", "EG": "Egipto", "AU": "Australia",
    "NZ": "Nueva Zelanda", "ZA": "Sudáfrica", "HR": "Croacia", "RS": "Serbia",
    "SI": "Eslovenia", "SK": "Eslovaquia", "LT": "Lituania", "LV": "Letonia",
    "EE": "Estonia", "GE": "Georgia", "AM": "Armenia", "AZ": "Azerbaiyán",
    "KZ": "Kazajistán", "UZ": "Uzbekistán", "IR": "Irán", "IQ": "Irak",
}


def _year_from_date(date_str: str | None) -> int | None:
    """Extrae el año de una fecha (YYYY-MM-DD o YYYY)."""
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return None


def _infer_era(birth_date: str | None) -> str | None:
    year = _year_from_date(birth_date)
    if year is None:
        return None
    for start, era in _ERA_BY_YEAR:
        if year >= start:
            return era
    return None


def _era_from_description(description: str | None) -> str | None:
    if not description:
        return None
    lower = description.lower()
    for kw, era in _ERA_DESCRIPTION_MAP.items():
        if kw in lower:
            return era
    return None


def _readable_country(country: str | None) -> str | None:
    """Convierte un código ISO alpha-2 o nombre a un nombre legible en español."""
    if not country:
        return None
    code = country.strip().upper()
    if len(code) == 2 and code in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[code]
    # Ya es un nombre (p. ej. 'Spain', 'Czech Republic', 'Germany') -> traducir lo común.
    lower = country.strip().lower()
    common = {
        "germany": "Alemania", "austria": "Austria", "switzerland": "Suiza",
        "italy": "Italia", "france": "Francia", "spain": "España", "portugal": "Portugal",
        "united kingdom": "Reino Unido", "great britain": "Reino Unido",
        "england": "Inglaterra", "scotland": "Escocia", "wales": "Gales",
        "united states": "Estados Unidos", "united states of america": "Estados Unidos",
        "usa": "Estados Unidos", "canada": "Canadá", "mexico": "México",
        "argentina": "Argentina", "brazil": "Brasil", "chile": "Chile",
        "colombia": "Colombia", "peru": "Perú", "uruguay": "Uruguay",
        "cuba": "Cuba", "japan": "Japón", "china": "China", "russia": "Rusia",
        "poland": "Polonia", "czech republic": "República Checa", "czechia": "República Checa",
        "hungary": "Hungría", "romania": "Rumanía", "bulgaria": "Bulgaria",
        "greece": "Grecia", "norway": "Noruega", "sweden": "Suecia",
        "denmark": "Dinamarca", "finland": "Finlandia", "netherlands": "Países Bajos",
        "belgium": "Bélgica", "ireland": "Irlanda", "turkey": "Turquía",
        "ukraine": "Ucrania", "croatia": "Croacia", "lithuania": "Lituania",
        "india": "India", "south korea": "Corea del Sur",
        # Históricos / otros comunes en Wikidata.
        "archduchy of austria": "Austria", "kingdom of italy": "Italia",
        "grand duchy of tuscany": "Italia", "duchy of milan": "Italia",
        "republic of venice": "Italia", "papal states": "Estados Pontificios",
        "kingdom of prussia": "Prusia", "holy roman empire": "Sacro Imperio Romano Germánico",
        "russian empire": "Imperio Ruso", "austrian empire": "Imperio Austriaco",
        "austro-hungarian empire": "Austria-Hungría", "ottoman empire": "Imperio Otomano",
        "kingdom of france": "Francia", "kingdom of spain": "España",
        "first french republic": "Francia", "french republic": "Francia",
        "weimar republic": "Alemania", "west germany": "Alemania",
        "german empire": "Imperio Alemán", "kingdom of bavaria": "Baviera",
        "kingdom of saxony": "Sajonia", "czechoslovakia": "Checoslovaquia",
        "yugoslavia": "Yugoslavia", "soviet union": "Unión Soviética",
        "united kingdom of great britain and ireland": "Reino Unido",
        "southern netherlands": "Países Bajos", "low countries": "Países Bajos",
        "habsburg monarchy": "Monarquía Habsburgo",
    }
    return common.get(lower, country.strip())


def _build_key_fact(description: str | None, wd_info: dict[str, Any] | None) -> str | None:
    """Dato destacable: descripción breve de Wikidata (qué era), o genérico."""
    if description and len(description) < 255:
        return description.capitalize()
    if wd_info and wd_info.get("is_composer"):
        return "Confirmado como compositor en Wikidata"
    return None


# ============================================================================
# ANÁLISIS DE COMPOSITORES
# ============================================================================


def _is_mojibake(name: str) -> bool:
    s = name or ""
    if "\ufffd" in s:
        return True
    hard = "\u00d0\u00c3"
    markers = "\u00d0\u00c3\u00c5\u00e3\u00e5\u00e7\u00ea\u00eb\u00ee\u00ed\u00ec"
    if any(ch in hard for ch in s):
        return True
    return sum(1 for ch in s if ch in markers) >= 2


def _has_noise(name: str) -> bool:
    noise_patterns = (
        "arranged from", "arranged by", "arranged", "attributed to", "attrib.", "attr.",
        "arr.", "arr ", " by ", "by ", "written by", "music by", "original music",
        "tune is", " page ", "tome", "feat", "solo ", "&", "/",
    )
    lower = name.lower()
    if any(p in lower for p in noise_patterns):
        return True
    return "[" in name


async def analyze_composer_async(name: str) -> dict[str, Any]:
    cleaned = name.strip()

    if not cleaned or len(cleaned) < 2:
        return {
            "is_composer": False,
            "biography": None,
            "confidence": "low",
            "review_reason": "El nombre está vacío o es demasiado corto.",
        }

    if _is_mojibake(cleaned):
        return {
            "is_composer": False,
            "biography": None,
            "confidence": "low",
            "review_reason": "El nombre parece corrupto (mojibake) o no corresponde a un compositor conocido.",
        }

    if _has_noise(cleaned):
        return {
            "is_composer": False,
            "biography": None,
            "confidence": "low",
            "review_reason": "El nombre contiene ruido y no corresponde a un compositor conocido.",
        }

    if cleaned.isdigit():
        return {
            "is_composer": False,
            "biography": None,
            "confidence": "low",
            "review_reason": "El nombre es numérico y no corresponde a un compositor.",
        }

    tokens = cleaned.split()
    if len(tokens) == 1:
        return {
            "is_composer": True,
            "biography": None,
            "confidence": "low",
            "review_reason": "Nombre único: posible compositor pero requiere verificación manual.",
        }

    wiki_bio = await _search_wikipedia(cleaned, delay=2.0)
    if not wiki_bio:
        await asyncio.sleep(2.0)
    mb_info = await _search_musicbrainz(cleaned, delay=2.0)
    if not mb_info:
        await asyncio.sleep(2.0)
    wd_info = await _search_wikidata(cleaned, delay=2.0)

    if wiki_bio or mb_info or wd_info:
        bio = wiki_bio or {}
        if mb_info:
            bio.setdefault("summary", "")
            if mb_info.get("life_span"):
                bio["summary"] = f"{bio.get('summary', '')} ({mb_info['life_span']})".strip()
            # MusicBrainz devuelve el país como código ISO; preferir nombre legible.
            if mb_info.get("country") and not bio.get("nationality"):
                bio["nationality"] = _readable_country(mb_info["country"])
        if wd_info:
            if wd_info.get("country") and not bio.get("nationality"):
                bio["nationality"] = _readable_country(wd_info["country"])
            dates = []
            if wd_info.get("birth_date"):
                dates.append(f"n. {wd_info['birth_date']}")
            if wd_info.get("death_date"):
                dates.append(f"f. {wd_info['death_date']}")
            if dates:
                bio["summary"] = f"{bio.get('summary', '')} ({', '.join(dates)})".strip()
            if wd_info.get("description"):
                bio.setdefault("key_fact", _build_key_fact(wd_info["description"], wd_info))

        # Época: 1) inferida del año de nacimiento, 2) por palabras en la descripción,
        # 3) tipo de MusicBrainz (Person/Group) como último recurso.
        era = _infer_era(wd_info.get("birth_date") if wd_info else None)
        if era is None:
            era = _era_from_description(wd_info.get("description") if wd_info else None)
        if era is None:
            era = _era_from_description(wiki_bio.get("key_fact") if wiki_bio else None)
        if era is None and mb_info and mb_info.get("type"):
            era = mb_info["type"]
        if era:
            bio["era"] = era

        if not bio.get("summary"):
            parts = [cleaned]
            if wd_info:
                if wd_info.get("description"):
                    parts.append(wd_info["description"])
                dates = []
                if wd_info.get("birth_date"):
                    dates.append(f"n. {wd_info['birth_date']}")
                if wd_info.get("death_date"):
                    dates.append(f"f. {wd_info['death_date']}")
                if dates:
                    parts.append(f"({', '.join(dates)})")
            if mb_info and mb_info.get("life_span") and not wd_info:
                parts.append(f"({mb_info['life_span']})")
            if mb_info and mb_info.get("name"):
                parts.append("- MusicBrainz record.")
            bio["summary"] = " ".join(parts) if len(parts) > 1 else cleaned

        # Normalizar la nacionalidad final (si quedó un código ISO de alguna fuente).
        if bio.get("nationality"):
            bio["nationality"] = _readable_country(bio["nationality"])

        # Referencias bibliográficas (URLs de consulta) de las fuentes usadas.
        references: list[dict[str, str]] = []
        if wiki_bio and wiki_bio.get("url"):
            references.append({"source": "Wikipedia", "url": wiki_bio["url"]})
        if wd_info and wd_info.get("url"):
            references.append({"source": "Wikidata", "url": wd_info["url"]})
        if mb_info and mb_info.get("url"):
            references.append({"source": "MusicBrainz", "url": mb_info["url"]})
        if references:
            bio["references"] = references

        return {
            "is_composer": True,
            "biography": bio if bio.get("summary") else None,
            "confidence": "medium",
            "review_reason": "Revisado por IA - DeepSeek V4",
        }

    return {
        "is_composer": True,
        "biography": None,
        "confidence": "low",
        "review_reason": "Nombre válido pero no verificado en base de conocimientos local; requiere revisión manual.",
    }


async def run_phase1(db_config: dict[str, Any], limit: int, output_path: Path) -> dict[str, Any]:
    """Fase 1: Procesa N compositores y guarda resultados en JSON para validación."""
    print(f"Conectando a BD: {db_config['name']}@{db_config['host']}:{db_config['port']}")
    conn = await get_connection(db_config)
    try:
        await ensure_bio_table(conn)
        total_pending = await count_pending(conn)
        print(f"Total pendientes sin biografía en BD: {total_pending}")

        composers = await fetch_pending_composers(conn, limit=limit, offset=0)
        print(f"Procesando {len(composers)} compositores (Fase 1 - TEST)...")

        results = []
        for c in composers:
            analysis = await analyze_composer_async(c["name"])
            result = {
                "composer_id": c["id"],
                "name": c["name"],
                "is_composer": analysis["is_composer"],
                "biography": analysis["biography"],
                "confidence": analysis["confidence"],
                "review_reason": analysis["review_reason"],
            }
            results.append(result)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Resultados guardados en: {output_path}")

        total = len(results)
        reales = sum(1 for r in results if r["is_composer"])
        dudosos = total - reales
        report = {
            "total_procesados": total,
            "identificados_como_reales": reales,
            "dudosos_o_no_identificados": dudosos,
            "ejemplos_reales": [r for r in results if r["is_composer"]][:5],
            "ejemplos_dudosos": [r for r in results if not r["is_composer"]][:5],
        }
        report_path = output_path.with_suffix(".report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Informe guardado en: {report_path}")
        return report
    finally:
        conn.close()


async def run_phase2_or_3(db_config: dict[str, Any], phase: str) -> dict[str, Any]:
    """Fase 2/3: Procesa TODOS los compositores activos sin biografía y actualiza BD."""
    env_label = "DESARROLLO" if phase == "phase2" else "PRODUCCIÓN"
    print(f"=== Fase {phase[-1]} ({env_label}) ===")
    print(f"Conectando a BD: {db_config['name']}@{db_config['host']}:{db_config['port']}")

    conn = await get_connection(db_config)
    try:
        await ensure_bio_table(conn)
        total_pending = await count_pending(conn)
        print(f"Total activos sin biografía en BD: {total_pending}")

        if total_pending == 0:
            print("No hay compositores pendientes sin biografía. Nada que hacer.")
            return {"total": 0, "updated": 0}

        offset = 0
        batch_size = 100
        processed = 0
        updated_reviewed = 0
        updated_review_required = 0
        errors = 0

        while True:
            composers = await fetch_pending_composers(conn, limit=batch_size, offset=offset)
            if not composers:
                break

            for c in composers:
                try:
                    analysis = await analyze_composer_async(c["name"])
                    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

                    if analysis["is_composer"] and analysis["biography"]:
                        await update_composer_review(
                            conn,
                            c["id"],
                            "reviewed",
                            "Revisado por IA - DeepSeek V4",
                            now_str,
                        )
                        await upsert_biography(conn, c["id"], analysis["biography"])
                        await _set_active(conn, c["id"])
                        updated_reviewed += 1
                    elif analysis["is_composer"]:
                        # Es compositor pero no se generó biografía (Wikidata sin summary
                        # o fallback). NO marcar reviewed: sigue pendiente para reintentar.
                        await update_composer_review(
                            conn,
                            c["id"],
                            "review_required",
                            "Sin biografía generada (requiere reintento)",
                            None,
                        )
                        updated_review_required += 1
                    else:
                        await update_composer_review(
                            conn,
                            c["id"],
                            "review_required",
                            analysis["review_reason"],
                            None,
                        )
                        updated_review_required += 1

                    processed += 1
                except Exception as exc:
                    print(f"Error procesando {c['id']}: {exc}", file=sys.stderr)
                    errors += 1

            offset += batch_size
            print(f"  Procesados: {processed}/{total_pending}")

        report = {
            "ambiente": env_label,
            "total_pendientes": total_pending,
            "procesados": processed,
            "marcados_reviewed": updated_reviewed,
            "marcados_review_required": updated_review_required,
            "errores": errors,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    finally:
        conn.close()


def main() -> None:
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Revisión de compositores por IA")
    parser.add_argument(
        "phase",
        choices=["phase1", "phase2", "phase3"],
        help="Fase: phase1 (test), phase2 (dev completo), phase3 (prod completo)",
    )
    parser.add_argument("--config", type=Path, default=None, help="Ruta a config.yaml")
    parser.add_argument("--limit", type=int, default=50, help="Límite para Fase 1")
    parser.add_argument("--output", type=Path, default=None, help="Ruta de salida JSON para Fase 1")
    args = parser.parse_args()

    if args.config is None:
        args.config = PROJECT_ROOT / "config.yaml"

    if not args.config.exists():
        print(f"ERROR: No se encontró {args.config}", file=sys.stderr)
        sys.exit(1)

    db_config = load_config(args.config)
    print(f"Config cargada desde: {args.config}")
    print(f"  DB: {db_config.get('name')}@{db_config.get('host')}:{db_config.get('port')}")

    if args.phase == "phase1":
        output = args.output or (PROJECT_ROOT / "test_results.json")
        report = asyncio.run(run_phase1(db_config, args.limit, output))
        print("\n=== Informe Fase 1 ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.phase == "phase2":
        asyncio.run(run_phase2_or_3(db_config, "phase2"))
    elif args.phase == "phase3":
        asyncio.run(run_phase2_or_3(db_config, "phase3"))


if __name__ == "__main__":
    main()
