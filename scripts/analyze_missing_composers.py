"""Auditoría read-only de las obras SIN compositor: ¿de dónde puede recuperarse?

No modifica el resolutor ni la BBDD. Clasifica cada obra sin compositor según la evidencia
interna disponible y produce un informe con métricas, desglose por origen y muestras.

    .venv\\Scripts\\python.exe scripts/analyze_missing_composers.py
    .venv\\Scripts\\python.exe scripts/analyze_missing_composers.py --out docsNew/analisis-compositores-ausentes.md
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.composer_quality import validar_nombre_compositor  # noqa: E402

# Roles que podrían aportar autoría musical (no intérprete): arreglista, orquestador,
# transcriptor, completador, maestro de capilla.
COMPOSER_LIKE_ROLES = {3, 4, 5, 7, 11}
_ANON_RE = re.compile(
    r"trad|anon|unknown|unbekannt|anonym|desconocid|sin autor|vvaa|varios|various", re.I
)


@dataclass
class Audit:
    work_id: int
    origin: str
    title: str | None
    candidates: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, source: str, value: str | None) -> None:
        if value and value.strip():
            self.candidates[source].add(value.strip())


def _valid_person(text: str | None) -> bool:
    if not text:
        return False
    return bool(validar_nombre_compositor(text)[0])


def _load(conn) -> tuple[list[dict], dict[int, str], dict[int, list[str]], dict[str, set[str]],
                         dict[str, set[str]]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, works_title, works_catalogue, works_origin, works_attribution_note, "
            "       works_attr_type FROM works"
        )
        works = cur.fetchall()
        cur.execute(
            "SELECT r.works_person_roles_work_id wid, p.persons_name name FROM works_person_roles r "
            "JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
            "WHERE r.works_person_roles_role_id=1"
        )
        composer_by_work = {r["wid"]: r["name"] for r in cur.fetchall()}
        cur.execute(
            "SELECT r.works_person_roles_work_id wid, r.works_person_roles_role_id role, "
            "       p.persons_name name FROM works_person_roles r "
            "JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
            "WHERE r.works_person_roles_role_id<>1"
        )
        other_roles: dict[int, list[str]] = defaultdict(list)
        for r in cur.fetchall():
            if r["role"] in COMPOSER_LIKE_ROLES:
                other_roles[r["wid"]].append(r["name"])

    titles_with_composer: dict[str, set[str]] = defaultdict(set)
    cat_with_composer: dict[str, set[str]] = defaultdict(set)
    for w in works:
        name = composer_by_work.get(w["id"])
        if not name:
            continue
        key_t = norm(w["works_title"])
        if key_t:
            titles_with_composer[key_t].add(name)
        key_c = norm(w["works_catalogue"])
        if key_c:
            cat_with_composer[key_c].add(name)
    return works, composer_by_work, other_roles, titles_with_composer, cat_with_composer


def run(out_path: Path | None) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    (
        works, composer_by_work, other_roles, titles_with_composer, cat_with_composer,
    ) = _load(conn)
    conn.close()

    missing = [w for w in works if not composer_by_work.get(w["id"])]
    categories: Counter[str] = Counter()
    by_origin: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[str]] = defaultdict(list)
    anon_expected = 0

    for w in missing:
        audit = Audit(work_id=w["id"], origin=w["works_origin"] or "?", title=w["works_title"])
        for name in other_roles.get(w["id"], []):
            audit.add("otra_relacion", name)
        for name in titles_with_composer.get(norm(w["works_title"]), set()):
            audit.add("catalogo_titulo_hermana", name)
        for name in cat_with_composer.get(norm(w["works_catalogue"]), set()):
            audit.add("catalogo_hermano", name)
        title = w["works_title"] or ""
        if " - " in title:
            suffix = title.rsplit(" - ", 1)[-1].strip()
            if _valid_person(suffix):
                audit.add("titulo_contexto", suffix)
        note = w["works_attribution_note"] or w["works_attr_type"]
        if _valid_person(note):
            audit.add("metadatos", note)

        distinct = {v for values in audit.candidates.values() for v in values}
        if len(distinct) > 1:
            category = "varias_posibilidades"
        elif distinct:
            for source in ("otra_relacion", "catalogo_hermano", "catalogo_titulo_hermana",
                           "metadatos", "titulo_contexto"):
                if audit.candidates.get(source):
                    category = source
                    break
            else:
                category = "otra"
        else:
            category = "ninguna_evidencia"
            if _ANON_RE.search(title) or _ANON_RE.search(note or ""):
                anon_expected += 1
                category = "anonimo_esperado"

        categories[category] += 1
        by_origin[w["works_origin"] or "?"][category] += 1
        if len(samples[category]) < 8:
            detail = next((f"{s}={sorted(v)[0]}" for s, v in audit.candidates.items() if v), "")
            samples[category].append(f"`{w['works_title']}` (id {w['id']}, {w['works_origin']}) {detail}")

    lines: list[str] = []
    add = lines.append
    add("# Auditoría de obras sin compositor\n")
    add("Generado por `scripts/analyze_missing_composers.py` (read-only).\n")
    add(f"- Obras totales: **{len(works)}** | sin compositor: **{len(missing)}** "
        f"({len(missing) * 100 // len(works)}%)")
    add(f"- De ellas, con patrones de anonimato/tradicional en título o nota: **{anon_expected}**\n")
    add("## Clasificación por evidencia interna\n")
    add("| Categoría | Obras |")
    add("|---|---|")
    for key, value in categories.most_common():
        add(f"| {key} | {value} |")
    add("\n## Desglose por origen\n")
    origins = sorted(by_origin)
    add("| Categoría | " + " | ".join(origins) + " |")
    add("|---" * (len(origins) + 1) + "|")
    for key, _ in categories.most_common():
        add(f"| {key} | " + " | ".join(str(by_origin[o].get(key, 0)) for o in origins) + " |")
    add("\n## Muestras\n")
    for key, _ in categories.most_common():
        add(f"\n### {key}\n")
        add("\n".join(f"- {s}" for s in samples.get(key, [])) or "(sin muestras)")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print("sin_compositor:", len(missing), "anonimo_esperado:", anon_expected)
    for key, value in categories.most_common():
        print(f"  {key:26s} {value}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
