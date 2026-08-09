<#
.SYNOPSIS
    Extrae los nombres de compositor de la copia PDMX en G: y genera un CSV
    compacto (solo la columna composer_name) listo para `populate-composers`.

.DESCRIPTION
    G:\osap-storage\PDMX.csv es el mirror completo de PDMX. Este script lee
    solo la columna de compositor y escribe un CSV ligero que se puede copiar
    al servidor de producción para poblar composers/composer_aliases allí.
#>
param(
    [string]$Source = "G:\osap-storage\PDMX.csv",
    [string]$Out = "G:\osap-storage\composer_names.csv"
)

$ErrorActionPreference = "Stop"
$py = "D:\Proyectos\AI_OSAP\osap-storage\.venv\Scripts\python.exe"

& $py -c @"
import csv
src = r'$Source'
dst = r'$Out'
columns = ('composer_name', 'composer', 'artist_name', 'artist')
with open(src, newline='', encoding='utf-8-sig') as fh:
    reader = csv.DictReader(fh)
    header = list(reader.fieldnames or [])
    lowered = [h.strip().lower() for h in header]
    col = next((header[lowered.index(c)] for c in columns if c in lowered), None)
    if col is None:
        raise SystemExit('sin columna de compositor en ' + src)
    with open(dst, 'w', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow([col])
        n = 0
        for row in reader:
            v = (row.get(col) or '').strip()
            if v:
                writer.writerow([v])
                n += 1
print('filas:', n, '->', dst)
"@
