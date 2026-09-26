"""Saca de "Compositores" las fichas que NO son personas (tradicional/anónimo/atribuido).

`(trad.)`, `(Trad. Germany)`, `Tradicional ?`, `(Attributed to) …`, `(c.1400-1460)` o `(?)` no
son autores: son marcas de atribución. El MusicXML de esas obras dice "traditional"/"anonymous",
así que este script:

1. localiza la persona pseudo-autor en el rol 1 de sus obras,
2. marca la obra con `works_attr_type` (`TRADICIONAL`, `ANONIMA`, `DESCONOCIDO`),
3. **desvincula** el rol 1 (la obra queda atribuida, sin compositor-persona),
4. deja la persona con `persons_visible=0` para que no salga en el catálogo.

    .venv\\Scripts\\python.exe scripts/mark_pseudo_persons.py
    .venv\\Scripts\\python.exe scripts/mark_pseudo_persons.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_SQL_MATCHES: list[tuple[str, str]] = [
    # Sin anclaje y multilingüe: la marca puede ir en cualquier posición
    # ("Author anonimo", "Canto popular Autor Anonimo", "Compositore. Anonimo", "Anoniem").
    ("ANONIMA", r"an[oó]nim|anoniem|anonym|\banon\b"),
    (
        "TRADICIONAL",
        r"\btrad\b|trad[.\s-]|tradicional|traditional|traditionnel|traditioneel|tradizionale|"
        r"traditionell|volksweise|volkslied|\bfolk\b",
    ),
    ("POPULAR", r"popular|populare|populär"),
    ("DESCONOCIDO", r"unknown|desconocid|unbekannt|onbekend|unattributed|sin autor|no author"),
    # Género musical usado como autor ("waltz", "Hymn", "Villancico", "Aria").
    (
        "DESCONOCIDO",
        r"^(el |la |le |the )?(villancico|cancion|canción|canto|himno|hymn|motete|motet|"
        r"madrigal|aria|lied|chorale|choral|requiem|réquiem|sonata|sinfonia|symphony|preludio|"
        r"prelude|waltz|vals|tango|balada|ballad|canzon|chanson)s?$",
    ),
    (
        # Género musical + catálogo usado como autor ("Wiegenlied, D. 498", "Sonata, Op. 2").
        "DESCONOCIDO",
        r"^(el |la |le |the )?(villancico|cancion|canción|canto|himno|hymn|motete|motet|"
        r"madrigal|aria|lied|chorale|choral|requiem|réquiem|sonata|sinfonia|symphony|preludio|"
        r"prelude|waltz|vals|tango|balada|ballad|canzon|chanson|wiegenlied)s?\s*[,:]\s*\S.*$",
    ),
]


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"),
        database=conf.get("name") or conf.get("database"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            # El aviso y la escritura usan EXACTAMENTE los mismos patrones (`_SQL_MATCHES`), para
            # que lo revisado en dry-run sea lo que se aplica.
            patterns = [pattern for _, pattern in _SQL_MATCHES]
            where_sql = " OR ".join(["p.persons_name REGEXP %s"] * len(patterns))
            rows: list[dict] = []
            for attr, pattern in _SQL_MATCHES:
                cur.execute(
                    "SELECT p.persons_id, p.persons_name, p.persons_review_status,"
                    " COUNT(r.works_person_roles_work_id) AS works"
                    " FROM persons p JOIN works_person_roles r"
                    "   ON r.works_person_roles_person_id=p.persons_id"
                    "  AND r.works_person_roles_role_id=1"
                    " WHERE p.persons_name REGEXP %s"
                    " GROUP BY p.persons_id, p.persons_name, p.persons_review_status",
                    (pattern,),
                )
                for row in cur.fetchall():
                    rows.append({**row, "attr": attr})
            total_works = sum(int(r["works"]) for r in rows)
            dist = Counter(str(r["attr"]) for r in rows)
            print(f"fichas pseudo-autor: {len(rows)}  obras afectadas: {total_works}")
            for attr, count in dist.most_common():
                print(f"  {attr}: {count} fichas")
            for r in rows[:12]:
                print(f"    {r['attr']} | {str(r['persons_name'])[:44]!r} | {r['works']} obras")
            if not args.apply:
                print("DRY-RUN: usa --apply para escribir.")
                return 0

            by_attr: Counter[str] = Counter()
            patterns = [pattern for _, pattern in _SQL_MATCHES]
            where_sql = " OR ".join(["p.persons_name REGEXP %s"] * len(patterns))
            # Respaldo antes de mutilar: permite revertir la atribución y los vínculos borrados.
            cur.execute(
                "CREATE TABLE IF NOT EXISTS pseudo_persons_backup ("
                " run_at DATETIME(6) NOT NULL, persons_id CHAR(36) NOT NULL,"
                " persons_name VARCHAR(1024) NOT NULL, work_id BIGINT UNSIGNED NOT NULL,"
                " old_attr_type VARCHAR(32) NULL, role_deleted TINYINT(1) NOT NULL DEFAULT 0)"
            )
            cur.execute(
                "INSERT INTO pseudo_persons_backup (run_at, persons_id, persons_name, work_id,"
                " old_attr_type, role_deleted)"
                " SELECT NOW(6), p.persons_id, p.persons_name, r.works_person_roles_work_id,"
                " w.works_attr_type, 1 FROM works_person_roles r"
                " JOIN persons p ON p.persons_id=r.works_person_roles_person_id"
                " JOIN works w ON w.id=r.works_person_roles_work_id"
                " WHERE r.works_person_roles_role_id=1 AND (" + where_sql + ")",
                patterns,
            )
            print(f"respaldo en pseudo_persons_backup: {cur.rowcount} filas")
            for attr, pattern in _SQL_MATCHES:
                # Guarda el texto original como nota de atribución antes de desvincular.
                cur.execute(
                    "UPDATE works w JOIN works_person_roles r"
                    " ON r.works_person_roles_work_id=w.id"
                    " JOIN persons p ON p.persons_id=r.works_person_roles_person_id"
                    " SET w.works_attribution_note=p.persons_name"
                    " WHERE r.works_person_roles_role_id=1 AND p.persons_name REGEXP %s"
                    " AND (w.works_attribution_note IS NULL OR w.works_attribution_note='')",
                    (pattern,),
                )
                cur.execute(
                    "UPDATE works w JOIN works_person_roles r"
                    " ON r.works_person_roles_work_id=w.id"
                    " JOIN persons p ON p.persons_id=r.works_person_roles_person_id"
                    " SET w.works_attr_type=%s"
                    " WHERE r.works_person_roles_role_id=1 AND p.persons_name REGEXP %s"
                    " AND (w.works_attr_type IS NULL OR w.works_attr_type='')",
                    (attr, pattern),
                )
                by_attr[attr] += cur.rowcount
            cur.execute(
                "DELETE r FROM works_person_roles r JOIN persons p"
                " ON p.persons_id=r.works_person_roles_person_id"
                " WHERE r.works_person_roles_role_id=1 AND (" + where_sql + ")",
                patterns,
            )
            unlinked = cur.rowcount
            cur.execute(
                "UPDATE persons SET persons_visible=0 WHERE "
                + " OR ".join(["persons_name REGEXP %s"] * len(patterns)),
                patterns,
            )
            hidden = cur.rowcount
            print("obras marcadas:", dict(by_attr))
            print(f"roles 1 desvinculados: {unlinked}  fichas ocultadas: {hidden}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
