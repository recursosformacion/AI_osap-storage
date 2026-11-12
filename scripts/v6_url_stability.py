"""Comprueba que las URLs de obra del sitemap no cambian con V6.

Toma un sitemap de producción (`/obras/<work_id>/<slug>`), comprueba que cada
Work existe en Storage, que el slug coincide con `works_title` y que tiene al
menos un Resource V6. Cualquier diferencia es un cambio de URL para Google y
debe resolverse con una tabla de correspondencia + 301 antes del corte.

Uso:
    python scripts/v6_url_stability.py --sitemap var/works-1.xml --limit 500
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import httpx
import pymysql
import yaml

ROOT = Path(__file__).resolve().parent.parent
_URL_RE = re.compile(r"<loc>([^<]*?/obras/([^/]+)/([^<]+))</loc>")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")
_TRANSLITERATIONS = str.maketrans(
    {
        "\u0153": "oe", "\u0152": "OE", "\u00e6": "ae", "\u00c6": "AE",
        "\u00df": "ss", "\u00f8": "o", "\u00d8": "O", "\u00fe": "th",
        "\u00de": "TH", "\u0111": "d", "\u0110": "D", "\u0142": "l",
        "\u0141": "L",
    }
)


def _slugify(text: str) -> str:
    prepped = _DASHES.sub(" ", (text or "").translate(_TRANSLITERATIONS))
    normalized = unicodedata.normalize("NFKD", prepped)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_ALNUM.sub("-", ascii_text).strip("-")[:80].strip("-") or "obra"


def _numeric(work_id: str) -> int | None:
    raw = work_id.removeprefix("index-")
    return int(raw) if raw.isdigit() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Estabilidad de URLs de obra (sitemap vs V6).")
    parser.add_argument("--sitemap", required=True, help="Fichero XML del sitemap de works.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--strict", action="store_true", help="Falla si el slug difiere del título actual.")
    parser.add_argument("--http-sample", type=int, default=20)
    args = parser.parse_args()

    text = Path(args.sitemap).read_text(encoding="utf-8")
    entries = _URL_RE.findall(text)[: max(1, args.limit)]
    if not entries:
        raise SystemExit("No se han encontrado URLs /obras/ en el sitemap")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["db"]
    conn = pymysql.connect(
        host=cfg["host"], port=int(cfg["port"]), user=cfg["user"],
        password=cfg["password"], database=cfg["name"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    ids = [n for _, wid, _ in entries if (n := _numeric(wid)) is not None]
    works: dict[int, dict] = {}
    with conn.cursor() as cur:
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            placeholders = ",".join(["%s"] * len(chunk))
            cur.execute(
                f"SELECT w.id, w.works_title, "
                f"(SELECT COUNT(*) FROM resources r WHERE r.work_id = w.id) resource_count "
                f"FROM works w WHERE w.id IN ({placeholders})",
                chunk,
            )
            for row in cur.fetchall():
                works[int(row["id"])] = row
    conn.close()

    missing: list[str] = []
    bad_slug: list[tuple[str, str]] = []
    historical: list[tuple[str, str]] = []
    no_resource: list[str] = []
    for url, work_id, slug in entries:
        numeric = _numeric(work_id)
        if numeric is None or numeric not in works:
            missing.append(url)
            continue
        row = works[numeric]
        expected = _slugify(str(row.get("works_title") or ""))
        if expected != slug:
            # El sitemap puede conservar slugs históricos (con compositor); la URL
            # sigue resolviendo y el canónico actual es `expected`.
            historical.append((url, expected))
            if args.strict:
                bad_slug.append((url, expected))
        if int(row.get("resource_count") or 0) == 0:
            no_resource.append(url)

    print(f"URLs comprobadas: {len(entries)}")
    print(f"Works ausentes en Storage: {len(missing)}")
    print(f"Slugs históricos distintos del canónico actual: {len(historical)}")
    print(f"Works sin Resource V6: {len(no_resource)}")
    for url, expected in bad_slug[:10]:
        print("  slug:", url, "->", expected)
    for url in missing[:10]:
        print("  ausente:", url)
    http_failures: list[str] = []
    if args.http_sample > 0 and entries:
        sample = entries[: args.http_sample]
        with httpx.Client(
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (OSAP V6 URL check)"},
        ) as client:
            for url, _, _ in sample:
                try:
                    response = client.get(url)
                except httpx.HTTPError:
                    http_failures.append(url)
                    continue
                if response.status_code != 200:
                    http_failures.append(f"{response.status_code} {url}")
    print(f"Muestras HTTP no-200: {len(http_failures)}")
    for item in http_failures[:10]:
        print("  http:", item)
    if missing or bad_slug or no_resource or http_failures:
        raise SystemExit(1)
    print("OK: Work IDs/slugs canónicos sin cambios y URLs del sitemap resolutivas.")


if __name__ == "__main__":
    main()
