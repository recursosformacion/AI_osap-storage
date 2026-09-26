"""Limpieza de personas duplicadas en `persons` (autoridad de nombres de osap-storage).

Recorre `persons`, agrupa por apellido, **valida** cada variante contra el candidato
canónico y, sólo si es un duplicado mal formado, la mueve a alias y repunta todas las
referencias `person_id`.

Reglas de validación (conservadoras: ante la duda, REVIEW y NO se toca):
  - Se normaliza el nombre: acentos, paréntesis, tokens de rol ("att.", "from", "arr."…),
    catálogos (Op./No./BWV/Wq/…), números y palabras vacías.
  - Familia = mismo **apellido exacto** (primer o último token; nunca subcadena, así
    "Bach" no arrastra a "Bacharach"/"Offenbach"/"Erbach").
  - Es DUPLICADO (AUTO) si, quitando del nombre de la variante el apellido y los
    nombres/iniciales del keeper, **no queda ningún token propio**. Se admiten iniciales
    (`J S Bach`) y prefijos (`Joh Seb Bach` -> Johann Sebastian).
  - Es REVIEW (persona distinta o multi-autor) si sobra algún token propio
    (`Johann Christian Bach`, `Carl Philipp Emanuel Bach`) o si aparecen varios autores
    (`Bach-Gounod`, `Vivaldi Bach`, `Hassler … J.S. Bach`).

Referencias que se repuntan al fusionar:
  works_person_roles, persons_aliases, persons_identity, persons_evidence,
  cpdl_edition_persons, representation_persons. Se registra en persons_merge_history.

Uso:
    .venv\\Scripts\\python.exe scripts/cleanup_person_duplicates.py [--like BACH] [--all]
    .venv\\Scripts\\python.exe scripts/cleanup_person_duplicates.py --apply [--like BACH]

Sin `--apply` es un dry-run (sólo informa). Con `--apply` fusiona únicamente los grupos
AUTO; los REVIEW se listan para revisión manual.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_PRIORITY = {"maestro": 0, "authority": 1, "web": 2, "identity-resolver": 3,
             "cpdl": 4, "pdmx": 5, "": 9}
_PARENS = re.compile(r"\([^)]*\)")
_ROLE = re.compile(
    r"\b(att\.?|attr\.?|attributed to|from|by|arranged?|arr\.?|transcriber|transposer|"
    r"transposed|editor|orchestrator|composer|no estilo de|in the style of|sorry|presque|"
    r"compuesta por|bearbeitet von|harm\.?|harmony|version|edits?|notebook)\b.*$", re.I)
_CAT = re.compile(
    r"\b(op\.?|no\.?|nr\.?|bwv|wq|hob\.?|kv|k\.?|twv|ms|anhang|posth\.?|tab|band)\b"
    r"\s*\.?\s*[a-z0-9]*", re.I)
_NUMS = re.compile(r"\b\d[\w.]*\b")
# Solo palabras vacías. Las INICIALES (j, s, c, ph…) NO son stopwords: distinguen personas
# distintas (J.S. Bach vs J.C. Bach vs C.Ph.E. Bach).
_STOP = {"de", "van", "von", "the", "and", "of", "in", "da", "di", "del", "la", "le",
         "notebook", "version", "collection", "complete"}


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


def clean_tokens(name: str) -> list[str]:
    t = fold(_PARENS.sub(" ", name))
    t = _ROLE.sub(" ", t)
    t = _CAT.sub(" ", t)
    t = _NUMS.sub(" ", t)
    t = re.sub(r"[^a-z]+", " ", t)
    return [x for x in t.split() if x and x not in _STOP]


# Un AUTO sólo se permite si KEEPER y VARIANTE tienen forma de nombre de persona. Estos
# marcadores delatan títulos/roles/colecciones/IDs usados como "compositor" en la fuente.
_NON_PERSON = re.compile(
    r"\b(written|writing|arranged|anged|collected|compiled|originally|worship|song|songs|"
    r"music|lyric|lyrics|performed|recording|recorded|produced|remix|cover|mashup|"
    r"instrumental|file|id|traditional|anon|anonym|anonymus|unknown|trad|feat|ft|"
    r"version|edit|edits|mix|notebook|volume|ms|musical|museum|hymnal|anthology|"
    r"psalter|album|compilation|psalm|psalmen|psalmes|gesang|melodie|zugeschrieben|"
    r"bearbeitung|ordnung|melody|melodies|tune|tunes|chant|plainchant|folksong|"
    r"folksongs|century)\b", re.I)
# Junk PEGADO a un apellido ("Isaacedit", "Bacharr", "BachBWV"): >=3 letras + sufijo.
_GLUED = re.compile(r"^.{3,}(edit|arr|bwv|anged|attributed)$", re.I)
_NON_PERSON_PHRASES = ("file id", "onmi", "misc/", " by ", "worship in", "music by",
                       "written by", "collected by", "arranged by", "arranged from",
                       "anged from", "presque", " and ", " & ")


# Metadatos incrustados (obra/fuente/biografía) que descalifican un AUTO: el AUTO debe
# reducir la variante al NOMBRE del keeper, sin ignorar palabras que no son nombres.
_METADATA = re.compile(
    r"[()]"                                   # paréntesis (años, obra, "Germany"…)
    r"|\b\d{4}\b"                             # año
    r"|\b(from|repository|manuscript|gesangbuch|volksweise|words|lyrics|arr|arrangement|"
    r"bearbeitung|harm|edition|opus|op|no|nr|bwv|wq|hob|kv|twv|ms|hymn|psalm|psalmen|anthem|"
    r"museum|hymnal|psalter|anthology|album|compilation|century|melody|tune|song|songs|"
    r"music|written|collected|compiled|worship|volkslied|chorale|choral|original|society|"
    r"barbershop|harmony|orchestra|choir|ensemble|studio|label|productions|collection|"
    r"collections|foundery|series|the)\b"
    r"|[-:]"                                  # guion/dos puntos separadores
    r"|[0-9]",                               # cualquier dígito
    re.I)


def has_metadata(name: str) -> bool:
    return bool(_METADATA.search(name or ""))


def is_person_name(name: str, tokens: list[str]) -> bool:
    """Descarta cadenas que no son nombres de persona (título/rol/colección/ID)."""
    if not tokens:
        return False
    f = fold(name)
    if _NON_PERSON.search(f):
        return False
    if any(phrase in f for phrase in _NON_PERSON_PHRASES):
        return False
    if f.startswith("no "):  # "No William Clarke of Feltwell", "No Wm Clarke MS…"
        return False
    if "/" in name or "\\" in name:  # rutas/IDs (onmi.misc/…)
        return False
    if any(_GLUED.match(tok) for tok in tokens):  # junk pegado al apellido
        return False
    return True


def is_reliable_keeper(tokens: list[str]) -> bool:
    """Keeper con forma de nombre completo: >=2 tokens y algún apellido (>=3 letras).

    Evita keepers como "J" (una letra) o un apellido suelto ambiguo.
    """
    return len(tokens) >= 2 and any(len(t) >= 3 for t in tokens)


def surname_of(tokens: list[str]) -> str:
    """Apellido = último token no-inicial (>=3 letras); si no, el primero.

    Evita agrupar por nombre de pila ("john"/"william") y soporta el orden invertido
    ("Bach Johann S" -> bach, "J C Bach" -> bach).
    """
    toks = list(tokens)
    while toks and len(toks[-1]) == 1:
        toks.pop()
    if not toks:
        return tokens[-1] if tokens else ""
    if len(toks[-1]) >= 3:
        return toks[-1]
    return toks[0]


def is_prefix_any(token: str, pool: set[str]) -> bool:
    """Solo abreviatura: el token del miembro es MÁS CORTO y prefijo del keeper.

    Así "joh" ~ "johann" se acepta, pero "johannes" (más largo) NO se colapsa en "johann".
    """
    return any(p.startswith(token) and len(token) < len(p) for p in pool if p)


def classify(keeper_tokens: list[str], member_tokens: list[str], surname: str) -> str:
    """AUTO si la variante no aporta tokens propios; REVIEW si aporta alguno."""
    k_given = [t for t in keeper_tokens if t != surname]
    m_given = [t for t in member_tokens if t != surname]
    if not m_given:
        return "AUTO"
    k_set = set(k_given)
    extras = []
    for t in m_given:
        if t in k_set:
            continue
        if len(t) == 1 and any(g.startswith(t) for g in k_given):
            continue  # inicial
        if len(t) >= 3 and is_prefix_any(t, k_set):
            continue  # abreviatura (joh -> johann)
        extras.append(t)
    return "AUTO" if not extras else f"REVIEW ({','.join(extras[:3])})"


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--like", default=None, help="limita a nombres que contengan el texto")
    ap.add_argument("--all", action="store_true", help="no limitar el listado de familias")
    ap.add_argument("--apply", action="store_true", help="aplica las fusiones AUTO")
    ap.add_argument("--plan-out", default=None, help="escribe el plan AUTO a un CSV para revisión")
    ap.add_argument("--review-out", default=None,
                    help="escribe los nombres REVIEW (no-AUTO) a un fichero, uno por línea")
    ap.add_argument("--max-families", type=int, default=40)
    args = ap.parse_args()

    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"),
        database=conf.get("name") or conf.get("database"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.persons_id, p.persons_name, COALESCE(p.persons_source_system,'') src, "
            "(SELECT COUNT(*) FROM works_person_roles r WHERE r.works_person_roles_person_id=p.persons_id "
            "AND r.works_person_roles_role_id=1) obras FROM persons p")
        persons = cur.fetchall()

    for p in persons:
        toks = clean_tokens(p["persons_name"])
        p["tokens"] = toks
        p["tset"] = set(toks)

    families: dict[str, list[dict]] = defaultdict(list)
    skipped_nonperson = 0
    for p in persons:
        if args.like and args.like.lower() not in str(p["persons_name"]).lower():
            continue
        if not is_person_name(str(p["persons_name"]), p["tokens"]) or \
                has_metadata(str(p["persons_name"])):
            skipped_nonperson += 1
            continue
        s = surname_of(p["tokens"])
        if s:
            families[s].append(p)
    print(f"descartados por no ser nombre de persona: {skipped_nonperson}")

    plan: list[tuple[dict, list[dict]]] = []
    review_names: list[str] = []
    review_total = 0
    for surname, members in sorted(families.items(), key=lambda kv: -len(kv[1])):
        if len(members) < 2:
            continue
        members.sort(key=lambda p: (-int(p["obras"] or 0), _PRIORITY.get(p["src"], 9),
                                    -len(str(p["persons_name"]))))
        keeper = members[0]
        # Keeper fiable: no se fusiona hacia una variante mal formada (p. ej. "…Bacharr by…").
        keeper_trust = _PRIORITY.get(keeper["src"], 9) <= 3 or int(keeper["obras"] or 0) >= 5
        if not keeper_trust or not is_reliable_keeper(keeper["tokens"]):
            continue
        autos, reviews = [], []
        for m in members[1:]:
            verdict = classify(keeper["tokens"], m["tokens"], surname)
            (autos if verdict == "AUTO" else reviews).append((m, verdict))
        if autos:
            plan.append((keeper, [m for m, _ in autos]))
        review_total += len(reviews)
        review_names.extend(str(m["persons_name"]) for m, _ in reviews)
        if len(plan) <= args.max_families or args.all:
            print(f"\n### apellido '{surname}' ({len(members)})")
            print(f"   KEEPER [{keeper['obras']:>3}] {keeper['persons_name']!r} src={keeper['src']}")
            for m, verdict in autos:
                print(f"   AUTO          [{m['obras']:>3}] {m['persons_name']!r}")
            for m, verdict in reviews[:12]:
                print(f"   {verdict:<28} [{m['obras']:>3}] {m['persons_name']!r}")

    print(f"\nRESUMEN: familias con AUTO={len(plan)}  miembros AUTO="
          f"{sum(len(v) for _, v in plan)}  REVIEW={review_total}")

    if args.plan_out:
        import csv

        def flat(value: object) -> str:
            return " ".join(str(value).split())  # sin saltos de línea -> 1 fila por registro

        rows_written = 0
        with open(args.plan_out, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["keeper_id", "keeper", "keeper_obras", "keeper_src",
                        "variant_id", "variant", "variant_obras"])
            for keeper, dups in plan:
                kn = str(keeper["persons_name"])
                kt = clean_tokens(kn)
                assert not has_metadata(kn), f"keeper con metadata: {kn}"
                assert is_person_name(kn, kt), f"keeper no-persona: {kn}"
                assert is_reliable_keeper(kt), f"keeper poco fiable: {kn}"
                for m in dups:
                    vn = str(m["persons_name"])
                    vt = clean_tokens(vn)
                    assert not has_metadata(vn), f"variante con metadata: {vn} <= {kn}"
                    assert is_person_name(vn, vt), f"variante no-persona: {vn} <= {kn}"
                    assert classify(kt, vt, surname_of(kt)) == "AUTO", \
                        f"variante no reduce al keeper: {vn} <= {kn}"
                    w.writerow([keeper["persons_id"], flat(kn),
                                keeper["obras"], keeper["src"], m["persons_id"],
                                flat(vn), m["obras"]])
                    rows_written += 1
        expected = sum(len(v) for _, v in plan)
        assert rows_written == expected, f"CSV {rows_written} != plan {expected}"
        print(f"plan escrito en {args.plan_out} ({rows_written} filas, == AUTO {expected})")

    if args.review_out:
        uniq = sorted(set(review_names))
        Path(args.review_out).write_text("\n".join(uniq) + "\n", encoding="utf-8")
        print(f"REVIEW escrito en {args.review_out} ({len(uniq)} nombres únicos)")

    if not args.apply:
        print("DRY-RUN: usa --apply para fusionar los AUTO.")
        conn.close()
        return 0

    merged_ids: set[str] = set()
    with conn.cursor() as cur:
        for keeper, dups in plan:
            dups = [d for d in dups if d["persons_id"] not in merged_ids]
            if not dups:
                continue
            keeper_id = keeper["persons_id"]
            dup_ids = [d["persons_id"] for d in dups]
            ph = ",".join(["%s"] * len(dup_ids))

            cur.execute("CREATE TABLE IF NOT EXISTS persons_cleanup_backup_20260925 "
                        "(run_at DATETIME(6) NOT NULL, persons_id CHAR(36) NOT NULL, "
                        "persons_name VARCHAR(1024), target CHAR(36))")
            for d in dups:
                cur.execute("INSERT INTO persons_cleanup_backup_20260925 VALUES (NOW(6),%s,%s,%s)",
                            (d["persons_id"], d["persons_name"], keeper_id))
            for tbl, col in (("works_person_roles", "works_person_roles_person_id"),
                             ("persons_aliases", "person_id"),
                             ("persons_identity", "persons_id"),
                             ("persons_evidence", "persons_id"),
                             ("cpdl_edition_persons", "persons_id"),
                             ("representation_persons", "representation_persons_person_id")):
                cur.execute(f"UPDATE IGNORE {tbl} SET {col}=%s WHERE {col} IN ({ph})",
                            [keeper_id, *dup_ids])
                cur.execute(f"DELETE FROM {tbl} WHERE {col} IN ({ph})", dup_ids)
            aliases = [(keeper_id, m["persons_name"], str(m["persons_name"]).strip().lower(),
                        "variant_pdmx", "pdmx") for m in dups]
            cur.executemany(
                "INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias, person_aliases_name_type, person_aliases_source) "
                "VALUES (%s,%s,%s,%s,%s)", aliases)
            cur.executemany(
                "INSERT INTO persons_merge_history (source_person_id, target_person_id, merged_by) "
                "VALUES (%s,%s,'cleanup_person_duplicates')",
                [(d["persons_id"], keeper_id) for d in dups])
            cur.execute(f"DELETE FROM persons WHERE persons_id IN ({ph})", dup_ids)
            merged_ids.update(dup_ids)
            print(f"  fusionado en [{keeper['obras']:>3}] {keeper['persons_name']!r}: "
                  f"{len(dups)} variantes")
    conn.commit()
    conn.close()
    print(f"APLICADO: {len(merged_ids)} personas fusionadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
