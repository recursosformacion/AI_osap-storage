"""Fase 1 de limpieza de `persons`: ocultar no-personas y renombrar prefijados.

Metodología: dry-run por defecto; `--apply` escribe; `--revert <batch>` deshace.
Toda escritura queda auditada en `persons_correction_history`.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import uuid

import pymysql
import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLAN = r"G:\rism\persons_fase1_plan.csv"

# Renombrados aprobados (nombre exacto actual -> nombre limpio).
RENAME = {
    ": Hans Sitt (1850-1922)": "Hans Sitt (1850-1922)",
    ": Siegfried Flesch (1933-2007)": "Siegfried Flesch (1933-2007)",
    ": Frederick F. Polnauer": "Frederick F. Polnauer",
    "'Femi Adeogun": "Femi Adeogun",
    ": Bob Reifsnyder": "Bob Reifsnyder",
    ": Stefan Altner": "Stefan Altner",
    "Charles Winfred Douglas (18671944)": "Charles Winfred Douglas (1867-1944)",
    "Written by John Francis Wade (17111786)": "John Francis Wade (1711-1786)",
    ": All Time Low ft. Vic Fuentes": "All Time Low ft. Vic Fuentes",
    "?Raisin Band?": "Raisin Band",
}

# Filas del plan "renombrar"/"corregir_fecha" que NO se tocan aún (bloques de crédito con
# varias personas, pares pegados, "Revised by", etc.) -> quedan para la fase de división.
DEFER = {
    "? Revised by David Charlier",
    ": Max Schneider (1875-1967)Rudolf Steglich (1886-1976)",
    ": Ferdinand David (1810 1873)and Friedrich Hermann (1828-1907)",
    ": Hans Sitt (18501922)Paul Klengel (1854-1935)",
    ": Leopold Auer (1845-1930) violinCarl Friedberg (18721955)",
    "Melodie: anonym (Chanson)(T.)u.M.: Une petite feste c. 1599(T.)u.A.: "
    "(?)Friedrich Spee SJ (15911635) 1637/1638Begleitung: Johannes Brahms (18331897)",
    "Words: Joseph Hart (17121768)Music: Benjamin F. White (1844 Sacred Harp)",
    "Georg Friederich Händel (16851759) 1741Klavierauszug: Kurt Soldan "
    "Arnold ScheringEdition Peters 4501 (Plate â. 11425)",
    "Georges Bizet(18381875)arr. Petey Piranha (b. 2003)",
    "James Lord Pierpont (18221893)Ðrr Goran Stojanovic",
    "? Revised by David Charlier ",
}

# Filas "renombrar" que son en realidad frases/bandas -> se ocultan igualmente.
HIDE_EXTRA = {
    "'By Mr Clark 1840'In different hand",
    "'ve found a friend O such a friend - Barnby",
    "'ll go to plough no more - Mundy",
    "'m Just Mashing Them Together",
    ": All Time Low ft. Vic Fuentes",
}

PLACEHOLDER_PREFIX = re.compile(
    r"^\((trad\.?|attributed|attrib|traditional)", re.I)


def load_plan() -> tuple[list[dict], list[dict], list[dict]]:
    with open(PLAN, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    hide, rename, deferred = [], [], []
    for r in rows:
        name = r["persons_name"]
        if r["accion"] == "placeholder_pendiente":
            continue
        if name in RENAME:
            rename.append({"persons_id": r["persons_id"], "old": name, "new": RENAME[name]})
        elif name in DEFER or name.rstrip() in DEFER:
            deferred.append({"persons_id": r["persons_id"], "name": name, "accion": r["accion"]})
        elif r["accion"] == "ocultar" or name in HIDE_EXTRA:
            hide.append({"persons_id": r["persons_id"], "name": name})
        else:
            deferred.append({"persons_id": r["persons_id"], "name": name, "accion": r["accion"]})
    return hide, rename, deferred


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="BATCH")
    args = ap.parse_args()

    with open("config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], db=cfg["name"], charset="utf8mb4",
                           autocommit=False, cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()

    if args.revert:
        cur.execute(
            "SELECT * FROM persons_correction_history WHERE reason LIKE %s ORDER BY id DESC",
            (f"%batch={args.revert}%",))
        hist = cur.fetchall()
        print(f"historial del batch {args.revert}: {len(hist)} filas")
        for h in hist:
            before = json.loads(h["before_json"] or "{}")
            if "visible" in before:
                cur.execute("UPDATE persons SET persons_visible=%s WHERE persons_id=%s",
                            (before["visible"], h["persons_id"]))
            if "name" in before:
                cur.execute("UPDATE persons SET persons_name=%s WHERE persons_id=%s",
                            (before["name"], h["persons_id"]))
            cur.execute(
                "UPDATE persons_correction_history SET operation='revert' WHERE id=%s", (h["id"],))
        conn.commit()
        print("revert aplicado")
        conn.close()
        return

    hide, rename, deferred = load_plan()
    print(f"plan: ocultar={len(hide)} renombrar={len(rename)} diferido={len(deferred)}")

    collisions = []
    for r in rename:
        cur.execute("SELECT persons_id FROM persons WHERE persons_name=%s AND persons_id<>%s",
                    (r["new"], r["persons_id"]))
        if cur.fetchone():
            collisions.append(r)
    if collisions:
        print("COLISIONES (abortado):", [c["new"] for c in collisions])
        conn.close()
        return

    if not args.apply:
        print("\n[DRY-RUN] ocultar:")
        for r in hide[:12]:
            print(f"   {r['name'][:70]!r}")
        print(f"   ... {len(hide)} filas")
        print("\n[DRY-RUN] renombrar:")
        for r in rename:
            print(f"   {r['old'][:55]!r} -> {r['new']!r}")
        print(f"\n[DRY-RUN] diferido (sin tocar): {len(deferred)}")
        conn.close()
        return

    batch = str(uuid.uuid4())
    reason = f"limpieza persons fase1 no-persona/prefijo batch={batch}"
    for r in hide:
        cur.execute("SELECT persons_visible FROM persons WHERE persons_id=%s", (r["persons_id"],))
        row = cur.fetchone()
        if row is None:
            continue
        cur.execute("UPDATE persons SET persons_visible=0 WHERE persons_id=%s", (r["persons_id"],))
        cur.execute(
            "INSERT INTO persons_correction_history (persons_id, operation, reason, before_json, after_json) "
            "VALUES (%s,'correct',%s,%s,%s)",
            (r["persons_id"], reason, json.dumps({"visible": row["persons_visible"], "name": r["name"]}),
             json.dumps({"visible": 0})))
    for r in rename:
        cur.execute("UPDATE persons SET persons_name=%s WHERE persons_id=%s",
                    (r["new"], r["persons_id"]))
        cur.execute(
            "INSERT INTO persons_correction_history (persons_id, operation, reason, before_json, after_json) "
            "VALUES (%s,'correct',%s,%s,%s)",
            (r["persons_id"], reason, json.dumps({"name": r["old"]}), json.dumps({"name": r["new"]})))
    conn.commit()
    print(f"aplicado batch={batch}: ocultar={len(hide)} renombrar={len(rename)}")
    conn.close()


if __name__ == "__main__":
    main()
