"""Mapea instrumentación/voces/ensembles al nuevo modelo:
`work_instruments` (+cantidad), `work_voices` (solo/ensemble), `work_ensembles`.

Fuentes:
- `osap-storage`.`work_instruments` (textos enriquecidos, cantidad embebida "(N)")
- `osap-storage`.`works`.`works_voicing` (CPDL)
- `osap-storage`.`works`.`works_instrumentation` (CPDL)

Uso:
    .venv\\Scripts\\python.exe scripts/map_instrumentation.py --db osap-storage [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

QTY = re.compile(r"^(?P<name>.*?)\s*\(\s*(?P<qty>\d+)\s*\)\s*$")

INSTRUMENT_ALIASES = {
    "saxophone alto": "Saxophone",
    "saxophone tenor": "Saxophone",
    "saxophone baritone": "Saxophone",
    "saxophone soprano": "Saxophone",
    "clarinet in b-flat": "Clarinet",
    "clarinet in bb": "Clarinet",
    "clarinet bass": "Bass Clarinet",
    "clarinet other": "Clarinet",
    "trumpet in b-flat": "Trumpet",
    "trumpet in bb": "Trumpet",
    "trumpet other": "Trumpet",
    "trombone bass": "Bass Trombone",
    "trombone other": "Trombone",
    "flute piccolo": "Piccolo",
    "contrabass": "Double Bass",
    "double bass": "Double Bass",
    "baritone horn": "Euphonium",
    "mellophone": "French Horn",
    "organ": "Pipe Organ",
    "guitar": "Acoustic Guitar",
    "tenor drum": "Snare Drum",
    "crash": "Cymbals",
    "crash cymbal": "Cymbals",
    "trumpet in c": "Trumpet",
    "natural horn": "French Horn",
    "trombone tenor": "Trombone",
    "trombone alto": "Trombone",
    "flute other": "Flute",
    "flute alto": "Flute",
    "saxophone other": "Saxophone",
    "clarinet in a": "Clarinet",
    "clarinet in e-flat": "Clarinet",
    "clarinet alto": "Clarinet",
    "clarinet contrabass": "Bass Clarinet",
    "tamtam": "Tam-tam",
    "bass voice": None,
    "vocals": None,
}

VOICE_ALIASES = {
    "soprano": "Soprano",
    "mezzo-soprano": "Mezzo-soprano",
    "mezzo": "Mezzo-soprano",
    "mezzo soprano": "Mezzo-soprano",
    "male": "Voice",
    "female": "Voice",
    "alto": "Contralto",
    "contralto": "Contralto",
    "countertenor": "Countertenor",
    "tenor": "Tenor",
    "baritone": "Baritone",
    "bass": "Bass",
    "bass voice": "Bass",
    "treble": "Treble",
    "voice": "Voice",
    "vocals": "Voice",
    "voice (other)": "Voice",
    "vocals (other)": "Voice",
}

GROUP_PATTERNS = re.compile(
    r"group|section|\(other\)|choir|ensemble", re.I
)
_LETTER_VOICE = {"s": "Soprano", "a": "Contralto", "t": "Tenor", "b": "Bass"}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    t = t.lower().strip().replace("_", " ")
    return re.sub(r"\s+", " ", t)


def split_qty(text: str) -> tuple[str, int]:
    m = QTY.match(text.strip())
    if not m:
        return text.strip(), 1
    return m.group("name").strip(), int(m.group("qty"))


async def run(db_name: str, dry_run: bool, source_db: str = "osap-storage_v1") -> None:
    base = Settings()  # type: ignore[call-arg]
    src = Database(base.model_copy(update={"db_name": source_db}))
    tgt = Database(base.model_copy(update={"db_name": db_name}))
    await src.connect()
    await tgt.connect()

    async with tgt.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, code, name_en, name_es, aliases FROM instruments")
        inst_keys: dict[str, int] = {}
        for r in await cur.fetchall():
            for key in (r["name_en"], r["name_es"], r["code"]):
                if key:
                    inst_keys.setdefault(norm(str(key)), int(r["id"]))
            if r.get("aliases"):
                try:
                    for a in json.loads(r["aliases"]) or []:
                        inst_keys.setdefault(norm(str(a)), int(r["id"]))
                except (ValueError, TypeError):
                    pass
        await cur.execute("SELECT id, voices_name FROM voices")
        voice_ids = {norm(r["voices_name"]): int(r["id"]) for r in await cur.fetchall()}
        await cur.execute("SELECT id, ensembles_code, ensembles_name FROM ensembles")
        ens_ids: dict[str, int] = {}
        for r in await cur.fetchall():
            ens_ids[norm(r["ensembles_code"])] = int(r["id"])
            if r["ensembles_name"]:
                ens_ids.setdefault(norm(r["ensembles_name"]), int(r["id"]))
        for alias, target in INSTRUMENT_ALIASES.items():
            if target is not None:
                inst_keys.setdefault(norm(alias), inst_keys.get(norm(target), 0))
        for alias, target in VOICE_ALIASES.items():
            voice_ids.setdefault(norm(alias), voice_ids.get(norm(target), 0))

    def classify(name: str):
        key = norm(name)
        if voice_ids.get(key):
            return ("voice", voice_ids[key])
        if key in ens_ids:
            return ("ens", ens_ids[key])
        if inst_keys.get(key):
            return ("inst", inst_keys[key])
        return None

    def classify_cpdl(wid: int, raw: str, acc_dict, unmatched) -> None:
        for piece in re.split(r"\s*,\s*|\s+or\s+|\s+and\s+", raw, flags=re.I):
            p = piece.strip().strip(";:.")
            if not p or p[0].isdigit() or "{{" in p or p.lower().startswith("add="):
                continue
            low = norm(p).replace("capella", "cappella").replace(" divisi", "")
            low = re.sub(r"\s+", " ", low).strip()
            if low in {"unknown", "other", "-", ""}:
                continue
            if low.startswith("solo "):
                vname = VOICE_ALIASES.get(norm(p[5:]))
                vid = voice_ids.get(norm(vname)) if vname else None
                if vid:
                    acc_dict.setdefault("v", {}).setdefault(vid, 0)
                    acc_dict["v"][vid] += 1
                continue
            low3 = low.replace(".", "-").replace("/", "-").replace(" ", "")
            hit = classify(p) or classify(low3)
            if hit:
                kind, iid = hit
                slot = {"voice": "v", "ens": "e", "inst": "i"}[kind]
                acc_dict.setdefault(slot, {}).setdefault(iid, 0)
                acc_dict[slot][iid] += 1
                continue
            if re.fullmatch(r"[satbr]+", low3):
                if len(low3) == 1:
                    vname = _LETTER_VOICE.get(low3)
                    vid = voice_ids.get(norm(vname)) if vname else None
                    if vid:
                        acc_dict.setdefault("v", {}).setdefault(vid, 0)
                        acc_dict["v"][vid] += 1
                else:
                    acc_dict.setdefault("e", {}).setdefault(("new", low3), 0)
                    acc_dict["e"][("new", low3)] += 1
                continue
            unmatched[p] = unmatched.get(p, 0) + 1

    # ---- 1. Fuente enriquecida (PDMX) ----
    acc: dict[int, dict] = {}
    unmatched_src: dict[str, int] = {}
    async with src.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT work_id, instrument FROM work_instruments ORDER BY work_id")
        rows = await cur.fetchall()
    for r in rows:
        wid = int(r["work_id"])
        name, qty = split_qty(str(r["instrument"]))
        slot = acc.setdefault(wid, {"i": {}, "v": {}, "e": {}})
        hit = classify(name)
        if hit:
            kind, iid = hit
            key = {"voice": "v", "ens": "e", "inst": "i"}[kind]
            slot[key][iid] = slot[key].get(iid, 0) + qty
        elif GROUP_PATTERNS.search(name):
            unmatched_src["[grupo] " + name] = unmatched_src.get("[grupo] " + name, 0) + 1
        else:
            unmatched_src[name] = unmatched_src.get(name, 0) + 1

    wi, wv, we = [], [], []
    for wid, slot in acc.items():
        for iid, q in slot["i"].items():
            wi.append((wid, iid, q))
        for eid, q in slot["e"].items():
            if isinstance(eid, tuple):
                continue
            we.append((wid, eid, q))
        ctx = "solo" if len(slot["v"]) <= 1 else "ensemble"
        for vid, q in slot["v"].items():
            wv.append((wid, vid, q, ctx))

    # ---- 2. CPDL (works_voicing + works_instrumentation) ----
    cpdl_acc: dict[int, dict] = {}
    unmatched_cpdl: dict[str, int] = {}
    async with tgt.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, works_voicing, works_instrumentation FROM works "
            "WHERE works_voicing IS NOT NULL OR works_instrumentation IS NOT NULL"
        )
        for r in await cur.fetchall():
            wid = int(r["id"])
            slot = cpdl_acc.setdefault(wid, {"i": {}, "v": {}, "e": {}})
            for col in ("works_voicing", "works_instrumentation"):
                raw = r.get(col)
                if not raw:
                    continue
                try:
                    terms = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(terms, list):
                    continue
                for item in terms:
                    if isinstance(item, str):
                        classify_cpdl(wid, item, slot, unmatched_cpdl)

    new_ens = {k[1] for s in cpdl_acc.values() for k in s.get("e", {}) if isinstance(k, tuple)}
    cpdl_wi, cpdl_wv, cpdl_we = [], [], []
    for wid, slot in cpdl_acc.items():
        for iid, q in slot.get("i", {}).items():
            cpdl_wi.append((wid, iid, q))
        for eid, q in slot.get("e", {}).items():
            if not isinstance(eid, tuple):
                cpdl_we.append((wid, eid, q))
        ctx = "solo" if len(slot.get("v", {})) <= 1 else "ensemble"
        for vid, q in slot.get("v", {}).items():
            cpdl_wv.append((wid, vid, q, ctx))

    if dry_run:
        print(json.dumps({
            "work_instruments": len(wi), "work_voices": len(wv), "work_ensembles": len(we),
            "cpdl work_instruments": len(cpdl_wi), "cpdl work_voices": len(cpdl_wv),
            "cpdl work_ensembles": len(cpdl_we), "cpdl ensembles nuevos": len(new_ens),
            "no mapeados origen": len(unmatched_src), "no mapeados cpdl": len(unmatched_cpdl),
        }, ensure_ascii=False, indent=1))
        for title, d in (("ORIGEN", unmatched_src), ("CPDL", unmatched_cpdl)):
            print(f"top no mapeados {title}:")
            for k, v in sorted(d.items(), key=lambda x: -x[1])[:100]:
                print(f"  {v:>7}  {k}")
        await src.close()
        await tgt.close()
        return

    async with tgt.transaction() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM work_instruments")
        await cur.execute("DELETE FROM work_voices")
        await cur.execute("DELETE FROM work_ensembles")
        ens_after = dict(ens_ids)
        for code in sorted(new_ens):
            await cur.execute(
                "INSERT IGNORE INTO ensembles (ensembles_code, ensembles_name) VALUES (%s,%s)",
                (code, code),
            )
        if new_ens:
            await cur.execute("SELECT id, ensembles_code FROM ensembles")
            ens_after = {norm(r["ensembles_code"]): int(r["id"]) for r in await cur.fetchall()}
        for wid, slot in cpdl_acc.items():
            for eid, q in slot.get("e", {}).items():
                if isinstance(eid, tuple):
                    cpdl_we.append((wid, ens_after[eid[1]], q))
        if wi or cpdl_wi:
            await cur.executemany(
                "INSERT IGNORE INTO work_instruments (works_id, instruments_id, "
                "work_instruments_quantity) VALUES (%s,%s,%s)", wi + cpdl_wi)
        if wv or cpdl_wv:
            await cur.executemany(
                "INSERT IGNORE INTO work_voices (works_id, voices_id, work_voices_quantity, "
                "work_voices_context) VALUES (%s,%s,%s,%s)", wv + cpdl_wv)
        if we or cpdl_we:
            await cur.executemany(
                "INSERT IGNORE INTO work_ensembles (works_id, ensembles_id, "
                "work_ensembles_quantity) VALUES (%s,%s,%s)", we + cpdl_we)

    await src.close()
    await tgt.close()
    print(json.dumps({
        "work_instruments": len(wi) + len(cpdl_wi),
        "work_voices": len(wv) + len(cpdl_wv),
        "work_ensembles": len(we) + len(cpdl_we),
        "no mapeados origen": len(unmatched_src),
        "no mapeados cpdl": len(unmatched_cpdl),
    }, ensure_ascii=False))
    for k, v in sorted(unmatched_src.items(), key=lambda x: -x[1])[:30]:
        print(f"  ORIGEN sin mapear {v:>6}  {k}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--source-db", default="osap-storage_v1", help="BBDD con los textos enriquecidos (work_instruments)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, args.dry_run, args.source_db))


if __name__ == "__main__":
    main()
