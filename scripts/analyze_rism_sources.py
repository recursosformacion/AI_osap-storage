"""Fase 2A: extracción dirigida de `source-latest.xml.gz` + contrato de evidencia RISM.

Read-only. Escanea el dump de FUENTES de RISM (MARCXML) y, solo para las obras nuestras con
candidato y match de persona, comprueba si una fuente RISM conecta la obra con esa persona y con
qué fiabilidad de autoría (`100 $j`).

Matching endurecido (2A.1):
- conexión fuerte = título uniforme `240` OR >=2 tokens significativos coincidentes (+ persona);
- se excluyen títulos de un solo token significativo y tokens genéricos (Gavotte, Air, Mass…).

Contrato `$j` → estado de evidencia del resolver (2A.2):
    Verified            -> resolved
    Ascertained         -> inferred
    Conjectural         -> ambiguous
    Alleged             -> ambiguous
    Doubtful            -> ambiguous
    (sin $j)            -> unclassified
    solo_nominal        -> unclassified

    .venv\\Scripts\\python.exe scripts/analyze_rism_sources.py
    .venv\\Scripts\\python.exe scripts/analyze_rism_sources.py --out docsNew/analisis-fuentes-rism.md
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.composer_quality import validar_nombre_compositor  # noqa: E402

NS = "{http://www.loc.gov/MARC21/slim}"

# Palabras funcionales y términos musicales genéricos que NO cuentan como evidencia por sí solos.
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "from", "by",
    "de", "la", "el", "los", "las", "le", "les", "du", "des", "un", "une", "et", "en",
    "sur", "avec", "von", "der", "die", "das", "und", "il", "lo", "gli", "con", "per", "su",
    "del", "della", "di", "al", "alla", "nel", "nella", "se", "no", "op", "bwv", "k", "wab",
}
GENERIC = {
    "gavotte", "gavottes", "air", "aire", "aires", "aria", "arias", "mass", "masses", "messe",
    "missa", "messas", "africa", "dance", "dances", "sonata", "sonatas", "sonate", "allegro",
    "adagio", "andante", "prelude", "preludes", "waltz", "waltzes", "march", "marches", "hymn",
    "hymns", "song", "songs", "motet", "motets", "madrigal", "madrigals", "allemande",
    "courante", "sarabande", "gigue", "menuet", "minuet", "fugue", "fugues", "toccata",
    "canzona", "ricercar", "theme", "themes", "variations", "var", "excerpts", "excerpt",
}

STATE_BY_J = {
    "verified": "resolved",
    "ascertained": "inferred",
    "conjectural": "ambiguous",
    "alleged": "ambiguous",
    "doubtful": "ambiguous",
}


def _tokens(text: str | None) -> set[str]:
    return set(norm(text).split())


def _significant(text: str | None) -> set[str]:
    return {t for t in _tokens(text) if len(t) >= 3 and t not in STOPWORDS and t not in GENERIC}


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(_tokens(name)))


def _valid_person(text: str | None) -> bool:
    return bool(text) and bool(validar_nombre_compositor(text)[0])


def _strong_match(work_sig: set[str], record: dict) -> str | None:
    """Devuelve '240'/'245' si hay conexión fuerte; None si no."""
    if len(work_sig) < 2:
        return None  # título de un solo token significativo: excluido de la automática
    for title in record["uniform"]:
        tsig = _significant(title)
        if work_sig == tsig or len(work_sig & tsig) >= 2:
            return "240"
    for title in record["transcribed"]:
        if len(work_sig & _significant(title)) >= 2:
            return "245"
    return None


def _weak_overlap(work_sig: set[str], record: dict) -> bool:
    return any(
        work_sig & _significant(title)
        for title in (*record["uniform"], *record["transcribed"])
    )


def _load_targets(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT rism_person_id, rism_person_names_matchkey k FROM rism_person_names")
        rism_by_key: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            if r["k"]:
                rism_by_key[r["k"]].add(r["rism_person_id"])
        cur.execute("SELECT id, works_title, works_attribution_note FROM works")
        works = cur.fetchall()
        cur.execute(
            "SELECT r.works_person_roles_work_id wid, p.persons_name name FROM works_person_roles r "
            "JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
            "WHERE r.works_person_roles_role_id=1"
        )
        composer_by_work = {r["wid"]: r["name"] for r in cur.fetchall()}
    titles_with_composer: dict[str, set[str]] = defaultdict(set)
    for w in works:
        name = composer_by_work.get(w["id"])
        if name:
            titles_with_composer[norm(w["works_title"])].add(name)

    targets: list[dict] = []
    for w in works:
        if composer_by_work.get(w["id"]):
            continue
        candidates: set[str] = set()
        title = w["works_title"] or ""
        if " - " in title:
            suffix = title.rsplit(" - ", 1)[-1].strip()
            if _valid_person(suffix):
                candidates.add(suffix)
        elif _valid_person(w["works_attribution_note"]):
            candidates.add(w["works_attribution_note"])
        candidates |= titles_with_composer.get(norm(title), set())
        if not candidates:
            continue
        matched: set[str] = set()
        for candidate in candidates:
            matched |= rism_by_key.get(_matchkey(candidate), set())
        if matched:
            targets.append({"id": w["id"], "title": title, "persons": matched})
    return targets


def run(path: Path, out_path: Path | None) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    targets = _load_targets(conn)
    conn.close()

    target_person_ids: set[str] = set()
    target_title_exact: dict[str, list[int]] = defaultdict(list)
    for t in targets:
        target_person_ids.update(t["persons"])
        target_title_exact[norm(t["title"])].append(t["id"])

    sources_by_person: dict[str, list[dict]] = defaultdict(list)
    anon_title_hits: set[int] = set()
    n_records = 0
    with gzip.open(path, "rb") as fh:
        for _event, elem in ElementTree.iterparse(fh, events=("end",)):
            if elem.tag != NS + "record":
                continue
            n_records += 1
            if n_records % 300000 == 0:
                print(f"  fuentes leídas: {n_records}", flush=True)
            composer_ids: list[str] = []
            reliability = None
            uniform: list[str] = []
            transcribed: list[str] = []
            has_heading = False
            for child in elem:
                if child.tag != NS + "datafield":
                    continue
                tag = child.get("tag")
                if tag not in ("100", "700", "240", "245"):
                    continue
                subs = {s.get("code"): (s.text or "").strip() for s in child}
                if tag == "100":
                    has_heading = True
                    pid = subs.get("0")
                    if pid and pid.startswith("people/"):
                        composer_ids.append(pid)
                        reliability = subs.get("j") or reliability
                elif tag == "700" and subs.get("4") in ("cmp", "composer"):
                    pid = subs.get("0")
                    if pid and pid.startswith("people/"):
                        composer_ids.append(pid)
                elif tag == "240" and subs.get("a"):
                    uniform.append(subs["a"])
                elif tag == "245" and subs.get("a"):
                    transcribed.append(subs["a"])
            elem.clear()

            hit = {pid for pid in composer_ids if pid in target_person_ids}
            if hit:
                record = {"reliability": reliability, "uniform": uniform[:4],
                          "transcribed": transcribed[:4]}
                for pid in hit:
                    sources_by_person[pid].append(record)
            elif not has_heading:
                for title in (*uniform, *transcribed):
                    for wid in target_title_exact.get(norm(title), []):
                        anon_title_hits.add(wid)

    categories: Counter[str] = Counter()
    states: Counter[str] = Counter()
    reliability_dist: Counter[str] = Counter()
    matched_via: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for t in targets:
        work_sig = _significant(t["title"])
        person_sources = [s for pid in t["persons"] for s in sources_by_person.get(pid, [])]
        if not person_sources:
            categories["sin_fuentes_rism"] += 1
            if t["id"] in anon_title_hits:
                categories["anonimo_rism"] += 1
                if len(examples["anonimo_rism"]) < 10:
                    examples["anonimo_rism"].append(f"{t['title']} (id {t['id']})")
            continue
        found = None
        weak = False
        for s in person_sources:
            via = _strong_match(work_sig, s)
            if via:
                found = (s, via)
                break
            weak = weak or _weak_overlap(work_sig, s)
        if found is not None:
            source, via = found
            categories["conecta_fuerte"] += 1
            matched_via[via] += 1
            reliability = source["reliability"] or "(sin $j)"
            reliability_dist[reliability] += 1
            state = STATE_BY_J.get((source["reliability"] or "").lower(), "unclassified")
            states[state] += 1
            if len(examples["conecta_fuerte"]) < 12:
                examples["conecta_fuerte"].append(
                    f"{t['title']} (id {t['id']}) vía {via} [{source['reliability'] or 'sin $j'}]"
                )
        elif weak:
            categories["solo_nominal_debil"] += 1
            if len(examples["solo_nominal_debil"]) < 8:
                examples["solo_nominal_debil"].append(f"{t['title']} (id {t['id']})")
        else:
            categories["solo_nominal"] += 1
            if len(examples["solo_nominal"]) < 8:
                examples["solo_nominal"].append(f"{t['title']} (id {t['id']})")

    lines: list[str] = []
    add = lines.append
    add("# Fase 2A — Fuentes RISM: conexión obra↔persona y contrato de evidencia\n")
    add("Generado por `scripts/analyze_rism_sources.py` (read-only). Fuente RISM: CC-BY-3.0.\n")
    add(f"- Fuentes RISM leídas: **{n_records}**")
    add(f"- Obras con candidato y match de persona RISM: **{len(targets)}**")
    add(f"- Personas RISM objetivo: **{len(target_person_ids)}**\n")
    add("## Contrato de evidencia (`100 $j` → estado del resolver)\n")
    add("| `$j` | Estado | ¿Resuelve compositor? |")
    add("|---|---|---|")
    for j, state in (("Verified", "resolved"), ("Ascertained", "inferred"),
                     ("Conjectural", "ambiguous"), ("Alleged", "ambiguous"),
                     ("Doubtful", "ambiguous"), ("(sin $j)", "unclassified"),
                     ("solo_nominal", "unclassified")):
        add(f"| {j} | {state} | {'sí' if state in ('resolved', 'inferred') else 'no automáticamente'} |")
    add("\n`resolved` = evidencia externa suficientemente fuerte para que el resolver la considere")
    add("atribución resuelta; no significa que «RISM diga la verdad».\n")
    add("## Matching endurecido (2A.1)\n")
    add("Conexión fuerte = título uniforme `240` **o** ≥2 tokens significativos coincidentes (+ persona).")
    add("Se excluyen títulos de un solo token significativo y tokens genéricos (Gavotte, Air, Mass…).\n")
    add("## Clasificación\n")
    add("| Resultado | Obras |")
    add("|---|---|")
    for key, value in categories.most_common():
        add(f"| {key} | {value} |")
    add(f"\nConexiones fuertes por vía: 240={matched_via.get('240', 0)}, 245={matched_via.get('245', 0)}\n")
    add("## Estado de evidencia de las conexiones fuertes\n")
    add("| Estado | Obras |")
    add("|---|---|")
    for key, value in states.most_common():
        add(f"| {key} | {value} |")
    add("\n## Fiabilidad (`$j`) de las conexiones fuertes\n")
    add("| `$j` | Obras |")
    add("|---|---|")
    for key, value in reliability_dist.most_common():
        add(f"| {key} | {value} |")
    add("\n## Ejemplos\n")
    for key in ("conecta_fuerte", "solo_nominal_debil", "solo_nominal", "anonimo_rism"):
        add(f"\n**{key}**\n")
        add("\n".join(f"- {e}" for e in examples.get(key, [])) or "(sin ejemplos)")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print(f"fuentes={n_records} targets={len(targets)} personas_objetivo={len(target_person_ids)}")
    print("categorías:", dict(categories))
    print("estados:", dict(states))
    print("fiabilidad:", dict(reliability_dist), "vía:", dict(matched_via))


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=Path(r"G:\rism\source-latest.xml.gz"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.file, args.out)


if __name__ == "__main__":
    main()
