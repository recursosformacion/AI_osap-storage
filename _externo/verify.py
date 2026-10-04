"""Verificacion independiente del entregable resultado.md contra la BD (solo lectura)."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_ensembles as audit  # noqa: E402

rows = audit.read_rows()
db_codes = [r["ensembles_code"] for r in rows]
existing = set(db_codes)

lines = (audit.BASE / "resultado.md").read_text(encoding="utf-8").splitlines()
assert lines[0] == "| ensembles_code | ID_Canonico | Existe_en_Tabla (0/1) |", lines[0]
assert lines[1] == "|---|---|---|", lines[1]
body = lines[2:]
assert len(body) == len(db_codes), (len(body), len(db_codes))

CELL = re.compile(r"^\| (.*) \| ([A-Z0-9_]+) \| ([01]) \|$")
errores = 0
for code, line in zip(db_codes, body):
    m = CELL.match(line)
    if not m:
        print("FORMATO:", line)
        errores += 1
        continue
    code_md, canonico, existe = m.groups()
    esperado = audit.canonicalize(code)
    if code_md != code:
        print("CODIGO DISTINTO:", code_md, "!=", code)
        errores += 1
    if canonico != esperado["id_canonico"]:
        print("ID DISTINTO:", code, canonico, esperado["id_canonico"])
        errores += 1
    if int(existe) != (1 if esperado["id_canonico"] in existing else 0):
        print("EXISTE DISTINTO:", code, canonico, existe)
        errores += 1

detalle = list(csv.DictReader(
    (audit.BASE / "auditoria_detalle.csv").open(encoding="utf-8-sig"),
    delimiter=";"))
assert len(detalle) == len(db_codes), (len(detalle), len(db_codes))

print(f"filas en resultado.md : {len(body)}")
print(f"filas en detalle CSV  : {len(detalle)}")
print(f"errores de verificacion: {errores}")
print("OK" if errores == 0 else "REVISAR")
