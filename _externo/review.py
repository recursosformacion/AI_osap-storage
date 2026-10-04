"""Revision de la traza de auditoria."""
import csv
import random
import sys

rows = list(csv.DictReader(
    open("_externo/auditoria_detalle.csv", encoding="utf-8-sig"), delimiter=";"))
print("filas:", len(rows))

mode = sys.argv[1] if len(sys.argv) > 1 else "notas"
width = int(sys.argv[2]) if len(sys.argv) > 2 else 400

if mode == "notas":
    print("\n=== filas con regla especial ===")
    for r in rows:
        if any(k in r["notas_reglas"]
               for k in ("ACEPTADA", "CURADA", "OMITIDO", "DESCARTADA",
                         "MODIFICADOR", "TRANSPOSICION", "NOTA_AMBITU",
                         "FRAGMENTO")):
            print(f"{r['ensembles_code']:<32} -> {r['ID_Canonico']:<20} | {r['notas_reglas']}")
elif mode == "muestra":
    print(f"\n=== muestra aleatoria de {width} filas ===")
    random.seed(7)
    for r in random.sample(rows, width):
        print(f"{r['ensembles_code']:<38} -> {r['ID_Canonico']:<20} "
              f"[{r['firma_frecuencias']:<14}] {r['etiqueta_familia']:<22} ex={r['Existe_en_Tabla']}  {r['notas_reglas']}")
elif mode == "largos":
    print("\n=== codigos de >= 12 caracteres con firma simple ===")
    for r in rows:
        if len(r["ensembles_code"]) >= 12 and r["total_voces"] != "0":
            print(f"{r['ensembles_code']:<38} -> {r['ID_Canonico']:<22} [{r['firma_frecuencias']}]")
elif mode == "voces1":
    print("\n=== codigos que resuelven a una sola voz ===")
    for r in rows:
        if r["total_voces"] == "1":
            print(f"{r['ensembles_code']:<32} -> {r['ID_Canonico']:<8} | {r['notas_reglas']}")
