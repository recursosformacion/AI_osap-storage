# Dry-run: relleno de `works_song_name` (read-only)

- Vacíos: **71818**
- **Propuestas: 71818**
- Sin separador ' - ': 69410
- Sufijo = compositor: 59 · sufijo persona: 1389
- Sufijo no-persona (descartado): 960

## Muestras

| work_id | works_title | propuesto |
|---|---|---|
| 41 | Peter I. Tchaikovsky - Italian Song (Orchestra) Orchestrated by Alex Nuñez | Peter I. Tchaikovsky - Italian Song (Orchestra) Orchestrated by Alex Nuñez |
| 55 | Under the Boardwalk | Under the Boardwalk |
| 99 | Lord be thy word my rule; SATB | Lord be thy word my rule; SATB |
| 101 | Calm It | Calm It |
| 103 | Shot in the dark | Shot in the dark |
| 109 | random song | random song |
| 111 | Fantasia X | Fantasia X |
| 122 | Flow gently sweet Afton | Flow gently sweet Afton |
| 133 | Contre Danze / De klapperman (2) (HS.dGJ.103) | Contre Danze / De klapperman (2) (HS.dGJ.103) |
| 150 | Milan by ear | Milan by ear |
| 158 | Hero's Life (Compact Score) Update | Hero's Life (Compact Score) Update |
| 168 | Sorry (Justin Bieber) Arranged by Ishbah Cox - Timpani | Sorry (Justin Bieber) Arranged by Ishbah Cox |
| 197 | The Pride of March | The Pride of March |
| 237 | Padoana / Pavane Thysius f149r (LHS.Th.10.326) | Padoana / Pavane Thysius f149r (LHS.Th.10.326) |
| 240 | Un Bravo Lupo | Un Bravo Lupo |
| 244 | Musette in D Major | Musette in D Major |
| 251 | GloriaSt Claude de la colombiere | GloriaSt Claude de la colombiere |
| 256 | ASGORE with drumset | ASGORE with drumset |
| 257 | First One | First One |
| 266 | Allegro in C minor | Allegro in C minor |
| 274 | stuff for talent show | stuff for talent show |
| 292 | Gran Vals by Francisco Tárrega for Tuba duet | Gran Vals by Francisco Tárrega for Tuba duet |
| 351 | MCRmix (Fixed) | MCRmix (Fixed) |
| 381 | Naru s Army | Naru s Army |
| 384 | Me lube dziewczÄ | Me lube dziewczÄ |

## Revert

`UPDATE works SET works_song_name=NULL WHERE id IN (...)` sobre el CSV.
