# Plan de ejecución Lote 1A (dry-run, read-only)

- Merges: **9** (A=7, B=2)

## Grupo A

| origen | destino | evidencia | roles origen | roles destino | colisiones wpr | alias a mover | ids a mover | refs |
|---|---|---|---|---|---|---|---|---|
| Arranged from Haydn (1732-1809) | Joseph Haydn | alias | {"1": 2, "3": 2} | {"1": 499, "3": 2, "10": 313} | 2 | 0 | {} | {"works_person_roles": 4, "persons_identity": 2} |
| from Ludwig van Beethoven (1770-1827) | Ludwig van Beethoven | nombre exacto | {"3": 5} | {"1": 298, "3": 1, "10": 377} | 0 | 0 | {} | {"works_person_roles": 5, "persons_identity": 1} |
| Arranged from Ludwig van Beethoven (1770-1827) | Ludwig van Beethoven | nombre exacto | {"1": 5} | {"1": 298, "3": 1, "10": 377} | 0 | 0 | {} | {"works_person_roles": 5, "persons_identity": 1} |
| Arr Alexander Maltas | Alexander Maltas | alias | {"1": 1} | {"1": 3, "3": 1} | 0 | 0 | {} | {"works_person_roles": 1, "persons_identity": 1} |
| Arranged from Ludwig van Beethoven | Ludwig van Beethoven | nombre exacto | {"1": 1} | {"1": 298, "3": 1, "10": 377} | 0 | 0 | {} | {"works_person_roles": 1, "persons_identity": 1} |
| From Ludwig van Beethoven | Ludwig van Beethoven | nombre exacto | {"1": 4, "3": 1} | {"1": 298, "3": 1, "10": 377} | 0 | 1 | {} | {"works_person_roles": 5, "persons_aliases": 1, "persons_identity": 1} |
| Arranged from Franz Schubert Opus 140 | Franz Schubert | alias | {"1": 1, "3": 1} | {"1": 337, "10": 228} | 0 | 0 | {} | {"works_person_roles": 2, "persons_identity": 2} |

## Grupo B

| origen | destino | evidencia | roles origen | roles destino | colisiones wpr | alias a mover | ids a mover | refs |
|---|---|---|---|---|---|---|---|---|
| Arr : Iraj Goli | iraj goli | alias | {"1": 1} | {"3": 1, "10": 3} | 0 | 0 | {} | {"works_person_roles": 1, "persons_identity": 1} |
| Edited byJAY YOUNG | Jay Young | alias | {"1": 1} | {} | 0 | 1 | {} | {"works_person_roles": 1, "persons_aliases": 1, "persons_identity": 1} |

## Detalle y revert

### [B] Arr : Iraj Goli → iraj goli

- origen: `3a5a0673-38c1-4aba-89a1-602b07f2981a` · destino: `1774908f-9ab7-4b58-abc1-865a4e9df59d`
- roles origen: {"1": 1} · roles destino: {"3": 1, "10": 3}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 1, "persons_identity": 1}
- obras (muestra): 121604:Morghe Sahar For Guitar
- persons_merge_history: {"merge_operation_id": "merge:3a5a0673-38c1-4aba-89a1-602b07f2981a->1774908f-9ab7-4b58-abc1-865a4e9df59d", "source_person_id": "3a5a0673-38c1-4aba-89a1-602b07f2981a", "target_person_id": "1774908f-9ab7-4b58-abc1-865a4e9df59d", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] Arranged from Haydn (1732-1809) → Joseph Haydn

- origen: `46efddc8-6acd-4cf7-9605-5ad2faea8558` · destino: `f1f53fb0-34d0-4402-8a4c-a5b640af3886`
- roles origen: {"1": 2, "3": 2} · roles destino: {"1": 499, "3": 2, "10": 313}
- colisiones works_person_roles: 2
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 4, "persons_identity": 2}
- obras (muestra): 127419:BRADFORD (Haydn) - Joseph Haydn; 220960:I live for those who love me - Franz J. Haydn
- persons_merge_history: {"merge_operation_id": "merge:46efddc8-6acd-4cf7-9605-5ad2faea8558->f1f53fb0-34d0-4402-8a4c-a5b640af3886", "source_person_id": "46efddc8-6acd-4cf7-9605-5ad2faea8558", "target_person_id": "f1f53fb0-34d0-4402-8a4c-a5b640af3886", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [B] Edited byJAY YOUNG → Jay Young

- origen: `6e415a02-a460-46ea-8fc7-f70fd763cd5b` · destino: `28ad1df6-ea68-45b7-948f-614eb7a12ead`
- roles origen: {"1": 1} · roles destino: {}
- colisiones works_person_roles: 0
- alias a mover: ['edited byjay young'] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 1, "persons_aliases": 1, "persons_identity": 1}
- obras (muestra): 225092:Preces and Responses - Thomas Tomkins
- persons_merge_history: {"merge_operation_id": "merge:6e415a02-a460-46ea-8fc7-f70fd763cd5b->28ad1df6-ea68-45b7-948f-614eb7a12ead", "source_person_id": "6e415a02-a460-46ea-8fc7-f70fd763cd5b", "target_person_id": "28ad1df6-ea68-45b7-948f-614eb7a12ead", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] from Ludwig van Beethoven (1770-1827) → Ludwig van Beethoven

- origen: `70c8c36c-86ee-4ecc-baa3-b9e489502a60` · destino: `e8994f5a-f1de-4676-bb00-7c2c8af2b2df`
- roles origen: {"3": 5} · roles destino: {"1": 298, "3": 1, "10": 377}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 5, "persons_identity": 1}
- obras (muestra): —
- persons_merge_history: {"merge_operation_id": "merge:70c8c36c-86ee-4ecc-baa3-b9e489502a60->e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "source_person_id": "70c8c36c-86ee-4ecc-baa3-b9e489502a60", "target_person_id": "e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] Arranged from Ludwig van Beethoven (1770-1827) → Ludwig van Beethoven

- origen: `89d0174e-4ef7-4692-aa5b-431fabc4c514` · destino: `e8994f5a-f1de-4676-bb00-7c2c8af2b2df`
- roles origen: {"1": 5} · roles destino: {"1": 298, "3": 1, "10": 377}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 5, "persons_identity": 1}
- obras (muestra): 2485:Friend Unfailing - Ludwig van Beethoven; 41822:Mount Of Olives - Ludwig van Beethoven; 91300:Alsace - Ludwig van Beethoven; 104636:This is jesus precious bible - Ludwig van Beethoven; 199319:O jesus friend unfailing - Ludwig van Beethoven
- persons_merge_history: {"merge_operation_id": "merge:89d0174e-4ef7-4692-aa5b-431fabc4c514->e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "source_person_id": "89d0174e-4ef7-4692-aa5b-431fabc4c514", "target_person_id": "e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] Arr Alexander Maltas → Alexander Maltas

- origen: `b63cde50-a57f-4ea3-a9ee-aab9ba9ac9a6` · destino: `8d071f03-5680-4dc7-893d-498a984915c3`
- roles origen: {"1": 1} · roles destino: {"1": 3, "3": 1}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 1, "persons_identity": 1}
- obras (muestra): 210881:Advance Australia Fair
- persons_merge_history: {"merge_operation_id": "merge:b63cde50-a57f-4ea3-a9ee-aab9ba9ac9a6->8d071f03-5680-4dc7-893d-498a984915c3", "source_person_id": "b63cde50-a57f-4ea3-a9ee-aab9ba9ac9a6", "target_person_id": "8d071f03-5680-4dc7-893d-498a984915c3", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] Arranged from Ludwig van Beethoven → Ludwig van Beethoven

- origen: `c63a6a9d-a7ff-4db9-8065-5de004db144d` · destino: `e8994f5a-f1de-4676-bb00-7c2c8af2b2df`
- roles origen: {"1": 1} · roles destino: {"1": 298, "3": 1, "10": 377}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 1, "persons_identity": 1}
- obras (muestra): 76470:Christians lo the star appeareth - Ludwig van Beethoven
- persons_merge_history: {"merge_operation_id": "merge:c63a6a9d-a7ff-4db9-8065-5de004db144d->e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "source_person_id": "c63a6a9d-a7ff-4db9-8065-5de004db144d", "target_person_id": "e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] From Ludwig van Beethoven → Ludwig van Beethoven

- origen: `d9977651-501c-4cda-831b-c0d158ec4ad4` · destino: `e8994f5a-f1de-4676-bb00-7c2c8af2b2df`
- roles origen: {"1": 4, "3": 1} · roles destino: {"1": 298, "3": 1, "10": 377}
- colisiones works_person_roles: 0
- alias a mover: ['from ludwig van beethoven'] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 5, "persons_aliases": 1, "persons_identity": 1}
- obras (muestra): 10604:HAYES (Beethoven) - Ludwig van Beethoven; 84144:Father of all whose powerful voice - John Wesley; 200450:Father of all whose powerful voice - Ludwig van Beethoven; 246154:God is love! his mercy brightens - Ludwig van Beethoven
- persons_merge_history: {"merge_operation_id": "merge:d9977651-501c-4cda-831b-c0d158ec4ad4->e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "source_person_id": "d9977651-501c-4cda-831b-c0d158ec4ad4", "target_person_id": "e8994f5a-f1de-4676-bb00-7c2c8af2b2df", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

### [A] Arranged from Franz Schubert Opus 140 → Franz Schubert

- origen: `dbbf4b8f-93be-467d-bc93-4cf92990e2ba` · destino: `2adf9877-4120-58ac-a003-7d728ef6cbf1`
- roles origen: {"1": 1, "3": 1} · roles destino: {"1": 337, "10": 228}
- colisiones works_person_roles: 0
- alias a mover: [] · ya en destino: []
- identificadores a mover: {}
- otras refs: {"works_person_roles": 2, "persons_identity": 2}
- obras (muestra): 39054:All the beauty out of doors - Franz Schubert
- persons_merge_history: {"merge_operation_id": "merge:dbbf4b8f-93be-467d-bc93-4cf92990e2ba->2adf9877-4120-58ac-a003-7d728ef6cbf1", "source_person_id": "dbbf4b8f-93be-467d-bc93-4cf92990e2ba", "target_person_id": "2adf9877-4120-58ac-a003-7d728ef6cbf1", "merged_by": "rism-lote1a"}
- revert: mover de vuelta los roles/alias/identificadores trasladados; personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history
- info del destino: sí (no se sobrescribe; solo se añaden alias/ids que faltan)

