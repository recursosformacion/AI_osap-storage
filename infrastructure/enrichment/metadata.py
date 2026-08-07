"""Pipeline de enriquecimiento de metadata (CSV PDMX + JSON MuseScore)."""
from __future__ import annotations

import ast
import csv
import json
import os

from application.use_cases.enrich_metadata import WorkEnrichment


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("na", "nan", "null", "none", "-"):
        return None
    return text


def _to_int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _list(value: object) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            items = ast.literal_eval(text)
            return [str(x) for x in items if x]
        except (ValueError, SyntaxError):
            pass
    return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]


def load_csv_index(csv_path: str) -> dict[str, dict]:
    """hash PDMX -> (metadatos del CSV + ruta del JSON de metadata)."""
    index: dict[str, dict] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            mxl = (rec.get("mxl") or "").strip()
            if not mxl:
                continue
            key = os.path.splitext(os.path.basename(mxl))[0]
            index[key] = {
                "composer": _clean(rec.get("composer_name")),
                "title": _clean(rec.get("title")),
                "subtitle": _clean(rec.get("subtitle")),
                "artist": _clean(rec.get("artist_name")),
                "song_name": _clean(rec.get("song_name")),
                "genres": _list(rec.get("genres")),
                "tags": _list(rec.get("tags")),
                "license": _clean(rec.get("license")),
                "complexity": _to_int(rec.get("complexity")),
                "metadata_path": _clean(rec.get("metadata")),
            }
    return index


def parse_metadata_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return extract_metadata(data)


def extract_metadata(data: dict) -> dict:
    """Extrae los campos relevantes de un JSON de metadata (MuseScore) ya parseado."""
    score = ((data.get("data") or {}).get("score") or {})
    instruments = [i.get("name") for i in (score.get("instruments") or []) if i.get("name")]
    genres = [g.get("name") for g in (data.get("genres") or []) if g.get("name")] or _list(data.get("genres"))
    thumbnails = score.get("thumbnails")
    return {
        "musical_key": _clean(score.get("keysig")),
        "instruments": instruments,
        "parts_names": score.get("parts_names") or [],
        "parts": _to_int(score.get("parts")),
        "pages": _to_int(score.get("pages_count")),
        "measures": _to_int(score.get("measures")),
        "duration": _clean(score.get("duration")),
        "license": _clean(score.get("license")),
        "public_domain": bool(score.get("is_public_domain")),
        "description": _clean(score.get("description")) or _clean(score.get("truncated_description")),
        "thumbnails": json.dumps(thumbnails) if thumbnails else None,
        "tags": score.get("tags") or [],
        "genres": genres,
    }


def build_enrichment(csv_meta: dict | None, json_meta: dict | None) -> WorkEnrichment:
    csv_meta = csv_meta or {}
    json_meta = json_meta or {}
    return WorkEnrichment(
        composer=csv_meta.get("composer") or json_meta.get("composer"),
        title=csv_meta.get("title") or json_meta.get("title"),
        subtitle=csv_meta.get("subtitle"),
        artist=csv_meta.get("artist"),
        song_name=csv_meta.get("song_name"),
        musical_key=json_meta.get("musical_key"),
        duration=json_meta.get("duration"),
        measures=json_meta.get("measures"),
        pages=json_meta.get("pages"),
        parts=json_meta.get("parts"),
        complexity=csv_meta.get("complexity"),
        license=csv_meta.get("license") or json_meta.get("license"),
        public_domain=json_meta.get("public_domain"),
        description=json_meta.get("description"),
        thumbnails=json_meta.get("thumbnails"),
        tags=csv_meta.get("tags") or json_meta.get("tags"),
        genres=csv_meta.get("genres") or json_meta.get("genres"),
        instruments=json_meta.get("instruments"),
        parts_names=json_meta.get("parts_names"),
    )
