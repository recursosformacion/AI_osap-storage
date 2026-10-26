"""Valida propuestas de Wikidata contra MusicBrainz y busca compositores por título.

Lee las propuestas generadas por `wikidata_persons.py` / `wikidata_works.py`:
- Personas: busca el artista por nombre, exige tipo Person y coincidencia única.
- Obras: busca work por título y, si se conoce, por compositor; devuelve candidatos.
No escribe en la base de datos. Cachea respuestas en data/musicbrainz_cache.json.

Uso:
    .venv\\Scripts\\python.exe scripts/musicbrainz_validate.py --persons-file ...
    .venv\\Scripts\\python.exe scripts/musicbrainz_validate.py --works-file ... --limit 50
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE_PATH = DATA / "musicbrainz_cache.json"
OUT_DIR = DATA / "musicbrainz"
ENDPOINT = "https://musicbrainz.org/ws/2"
USER_AGENT = "OSAP-MusicBrainz-Validator/1.0 (https://openmusicrepository.com)"
try:
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None

_last_request = 0.0
_cache: dict[str, Any] = {}
if CACHE_PATH.exists():
    try:
        _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _cache = {}


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    global _last_request
    url = f"{ENDPOINT}/{path}?{urllib.parse.urlencode({**params, 'fmt': 'json'})}"
    if url in _cache:
        return _cache[url]
    wait = 1.1 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30, context=_SSL) as response:
                payload = json.loads(response.read().decode("utf-8"))
            _last_request = time.monotonic()
            _cache[url] = payload
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"MusicBrainz no responde: {exc}") from exc
    raise RuntimeError("MusicBrainz no respondió")


def _save_cache() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")


def _latest(directory: Path, prefix: str) -> Path:
    files = list(directory.glob(f"{prefix}*.json"))
    if not files:
        raise SystemExit(f"No hay {prefix}*.json en {directory}")
    return max(files, key=lambda path: path.stat().st_mtime)


def _person(proposal: dict[str, Any]) -> dict[str, Any]:
    name = str(proposal.get("persons_name") or "").strip()
    if not name:
        return {"status": "no_name"}
    payload = _get("artist", {"query": f'artist:"{name}"', "limit": 5})
    artists = [a for a in payload.get("artists", []) if a.get("type") == "Person"]
    artists.sort(key=lambda a: int(a.get("score") or 0), reverse=True)
    if not artists:
        return {"status": "no_match"}
    top = artists[0]
    return {
        "status": "match" if int(top.get("score") or 0) >= 95 else "weak",
        "mbid": top.get("id"),
        "name": top.get("name"),
        "score": top.get("score"),
        "disambiguation": top.get("disambiguation"),
        "life_span": top.get("life-span"),
    }



def _escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _persons_batch(proposals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(proposals), 50):
        chunk = proposals[offset : offset + 50]
        query = " OR ".join(f'artist:"{_escape_lucene(str(p.get("persons_name") or ""))}"' for p in chunk)
        try:
            payload = _get("artist", {"query": query, "limit": 100})
        except Exception as exc:
            print(f"lote {offset}: {exc}", flush=True)
            for proposal in chunk:
                out[proposal["persons_id"]] = {"status": "error", "error": str(exc)}
            _save_cache()
            continue
        artists = [a for a in payload.get("artists", []) if a.get("type") == "Person"]
        print(f"lote {offset}/{len(proposals)}", flush=True)
        _save_cache()
        for proposal in chunk:
            name = str(proposal.get("persons_name") or "").strip().casefold()
            found = [a for a in artists if str(a.get("name") or "").casefold() == name]
            found.sort(key=lambda a: int(a.get("score") or 0), reverse=True)
            if not found:
                out[proposal["persons_id"]] = {"status": "no_match"}
                continue
            top = found[0]
            out[proposal["persons_id"]] = {
                "status": "match" if int(top.get("score") or 0) >= 95 else "weak",
                "mbid": top.get("id"),
                "name": top.get("name"),
                "score": top.get("score"),
                "disambiguation": top.get("disambiguation"),
                "life_span": top.get("life-span"),
                "candidate_count": len(found),
            }
    return out
def _work(proposal: dict[str, Any]) -> dict[str, Any]:
    title = str(proposal.get("current_title") or proposal.get("wikidata_label") or "").strip()
    if not title:
        return {"status": "no_title"}
    composer = str(proposal.get("composer") or "").strip()
    query = f'work:"{title}"'
    if composer:
        query += f' AND artist:"{composer}"'
    payload = _get("work", {"query": query, "limit": 5})
    works = payload.get("works", [])
    works.sort(key=lambda w: int(w.get("score") or 0), reverse=True)
    if not works:
        return {"status": "no_match"}
    top = works[0]
    return {
        "status": "match" if int(top.get("score") or 0) >= 95 else "weak",
        "mbid": top.get("id"),
        "title": top.get("title"),
        "score": top.get("score"),
        "composer": (
            (top.get("artist-relation") or [{}])[0].get("artist", {}).get("name")
            if top.get("artist-relation") else None
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persons-file", type=Path)
    ap.add_argument("--works-file", type=Path)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if not args.persons_file and not args.works_file:
        ap.error("indica --persons-file y/o --works-file")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    if args.persons_file:
        data = json.loads(args.persons_file.read_text(encoding="utf-8"))
        selected = data if args.limit == 0 else data[: args.limit]
        checked = _persons_batch(selected)
        for proposal in selected:
            results.append(
                {
                    "kind": "person",
                    **proposal,
                    "musicbrainz": checked.get(
                        proposal["persons_id"], {"status": "no_match"}
                    ),
                }
            )
    if args.works_file:
        data = json.loads(args.works_file.read_text(encoding="utf-8"))
        for proposal in (data if args.limit == 0 else data[: args.limit]):
            results.append({"kind": "work", **proposal, "musicbrainz": _work(proposal)})
    _save_cache()
    out = args.out or OUT_DIR / "validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["kind", "id", "name", "status", "mbid", "score", "details"])
        for row in results:
            mb = row.get("musicbrainz", {})
            writer.writerow([
                row.get("kind"),
                row.get("persons_id") or row.get("works_id"),
                row.get("persons_name") or row.get("current_title"),
                mb.get("status"),
                mb.get("mbid"),
                mb.get("score"),
                mb.get("composer") or mb.get("disambiguation") or "",
            ])
    print(f"validaciones={len(results)} json={out} csv={csv_path}")
    print("No se ha escrito en la BD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())





