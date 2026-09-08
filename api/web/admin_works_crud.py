"""Página de administración: Mantenimiento de obras (CRUD convencional standalone).

Listado del fichero de obras (30/página, búsqueda) y detalle Ver/Editar usando los
endpoints de admin existentes:
  GET /api/admin/works?q&limit&offset
  GET /api/admin/works/{id}
  PUT /api/admin/works/{id}

El token de servicio llega por URL (?token=...); si no viene, se muestra la caja
para pegarlo. La página en sí no contiene datos (exenta de auth); el API exige
storage:admin.
"""

from __future__ import annotations

_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mantenimiento de obras</title>
<style>
  :root{ --border:#334155; --muted:#94a3b8; --bg:#0f172a; --card:#1e293b; --accent:#38bdf8; }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:#e2e8f0;
      font:14px/1.5 system-ui,Segoe UI,sans-serif;}
  .wrap{max-width:1100px;margin:0 auto;padding:16px}
  h1{font-size:20px} .sub{color:var(--muted);margin-top:-8px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px;
        padding:14px;margin:12px 0}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  input,select,textarea{background:#0b1524;color:#e2e8f0;border:1px solid var(--border);
        border-radius:8px;padding:7px 9px;font:inherit}
  input:disabled{opacity:.75}
  textarea{width:100%;min-height:90px}
  table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:7px 8px;
        border-bottom:1px solid var(--border);vertical-align:top}
  th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase}
  button{cursor:pointer;border:1px solid var(--border);border-radius:8px;padding:7px 12px;
        background:#0b1524;color:#e2e8f0}
  button.ghost{background:transparent} button:hover{border-color:var(--accent);color:#fff}
  .tools{display:flex;gap:6px}
  a{color:var(--accent)} .muted{color:var(--muted)}
  .hidden{display:none} .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  dl.detail{display:grid;grid-template-columns:1fr 2fr;gap:6px 12px;margin:0}
  dl.detail dt{color:var(--muted)} dd{margin:0;overflow-wrap:anywhere}
  @media(max-width:760px){.grid,dl.detail{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
  <h1>Mantenimiento de obras</h1>
  <p class="sub">Listado del fichero <code>works</code> · 30 filas por página.</p>

  <div class="card" id="tokenCard">
    <label>Service token (Bearer)</label>
    <div class="row">
      <input style="flex:1" id="token" placeholder="pega el service token (o usa ?token=...)" />
      <button id="btnApply">Aplicar</button>
    </div>
  </div>
  <div id="msg" class="muted"></div>

  <div id="listView">
    <div class="card"><div class="row" style="justify-content:space-between">
      <div class="row">
        <label>Buscar <input id="q" placeholder="título, compositor o catálogo" /></label>
        <button id="btnSearch">Buscar</button>
      </div>
      <div class="muted"><span id="pageInfo"></span></div>
    </div></div>
    <div class="card"><div id="area"><div class="muted">Cargando…</div></div>
      <div class="row" style="justify-content:space-between;margin-top:10px">
        <button id="prev">← Anterior</button>
        <button id="next">Siguiente →</button>
      </div>
    </div>
  </div>

  <div id="detailView" class="hidden"></div>
</div>
<script>
const qs = (k) => new URLSearchParams(location.search).get(k);
const q = qs("token") || "";
const mode = qs("mode") === "edit" ? "edit" : "view";
const wid = qs("id") || "";
const state = { items: [], total: 0, limit: 30, offset: 0 };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const $ = (i) => document.getElementById(i);
function token(){ const v = q || $("token").value; return v.trim(); }
function auth(){ return { Authorization: "Bearer " + token() }; }
function msg(m, err){ const el = $("msg"); if(!el) return; el.textContent = m;
  el.style.color = err ? "#f87171" : "#94a3b8"; }
async function api(url, opts){
  const r = await fetch(url, Object.assign({ headers: { Accept: "application/json" } }, opts || {}));
  if (!r.ok){ let t=""; try{ t = (await r.json()).detail || ""; }catch(e){} throw new Error("HTTP "+r.status+" "+t); }
  return r.json();
}
function loadToken(){
  if (q){ $("token").value = q; $("tokenCard").classList.add("hidden"); }
  else { $("tokenCard").classList.remove("hidden"); }
}
const SCALARS = [
  ["title","Título"],["subtitle","Subtítulo"],["composer","Compositor"],["composer_id","composer_id"],
  ["artist","Artista"],["song_name","Song name"],["genre","Género"],["opus","Opus"],
  ["catalogue","Catálogo"],["musical_key","Tonalidad"],["year","Año","number"],
  ["instrumentation","Instrumentación"],["language","Idioma"],["duration","Duración"],
  ["measures","Compases","number"],["pages","Páginas","number"],["parts","Nº de partes","number"],
  ["complexity","Complejidad (1-5)","number"],["license","Licencia"],["thumbnails","Thumbnails"],
  ["work_key","work_key"],["relative_path","relative_path"],["attribution_type","attribution_type"],
  ["attribution_note","attribution_note"]
];
const LISTS = [
  ["tags","Etiquetas"],["genres","Géneros"],["instruments","Instrumentos"],["parts_names","Partes"]
];
function fmt(v){ return v === null || v === undefined || v === "" ? "—" : String(v); }
function valInput(k, d, editable){
  const cfg = SCALARS.find(s => s[0] === k);
  const type = cfg && cfg[2];
  if (type === "number"){
    return `<input id="f_${k}" type="number" value="${esc(d[k] ?? "")}" ${editable?"":"disabled"} />`;
  }
  if (k === "public_domain"){
    return `<select id="f_${k}" ${editable?"":"disabled"}>
      <option value="1" ${d.public_domain?"selected":""}>sí</option>
      <option value="0" ${d.public_domain?"":"selected"}>no</option></select>`;
  }
  return `<input id="f_${k}" value="${esc(d[k] ?? "")}" ${editable?"":"disabled"} />`;
}
function renderDetail(d){
  const editable = mode === "edit";
  let h = `<h2>${esc(d.title || d.work_key || "Obra")} <span class="muted">(#${esc(d.id)})</span></h2>`;
  if (editable){
    h += `<div class="card"><div class="grid">`;
    for (const [k,lab] of SCALARS) h += `<label>${lab}<br>${valInput(k,d,true)}</label>`;
    h += `<label>Dominio público<br>${valInput("public_domain",d,true)}</label>`;
    h += `</div>
      <label style="margin-top:10px">Descripción<br><textarea id="f_description" ${editable?"":"disabled"}>${esc(d.description||"")}</textarea></label>`;
    for (const [k,lab] of LISTS){
      h += `<label style="margin-top:8px">${lab} (separados por coma)<br><input id="f_${k}" value="${esc((d[k]||[]).join(", "))}" /></label>`;
    }
    h += `<div class="row" style="margin-top:10px"><button onclick="saveId()">Guardar</button>
      <button class="ghost" onclick="backToList()">← Volver al listado</button></div>`;
    h += `</div>`;
  } else {
    h += `<div class="card"><dl class="detail">`;
    for (const [k,lab] of SCALARS) h += `<dt>${lab}</dt><dd>${esc(fmt(d[k]))}</dd>`;
    h += `<dt>Dominio público</dt><dd>${d.public_domain ? "sí" : "no"}</dd>`;
    h += `<dt>Descripción</dt><dd>${esc(fmt(d.description))}</dd>`;
    for (const [k,lab] of LISTS) h += `<dt>${lab}</dt><dd>${esc((d[k]||[]).join(", ") || "—")}</dd>`;
    h += `</dl>
      <div class="row" style="margin-top:10px">
        <button onclick="openMode('edit','${esc(d.id)}')">Editar</button>
        <button class="ghost" onclick="backToList()">← Volver al listado</button>
      </div></div>`;
  }
  $("detailView").innerHTML = h; $("listView").classList.add("hidden");
  $("detailView").classList.remove("hidden");
}
async function loadDetail(){
  try{
    const d = await api("/api/admin/works/"+encodeURIComponent(wid), { headers: auth() });
    renderDetail(d); msg("");
  }catch(e){ msg(e.message, true); }
}
function num(v){ const n = parseInt(v,10); return Number.isNaN(n) ? null : n; }
function listVal(id){ const v = $("f_"+id).value.split(",").map(s=>s.trim()).filter(Boolean); return v; }
async function saveId(){
  const body = {};
  for (const [k] of SCALARS){
    const el = $("f_"+k); if (!el) continue;
    const cfg = SCALARS.find(s => s[0] === k);
    body[k] = cfg && cfg[2] === "number" ? num(el.value) : (el.value === "" ? null : el.value);
  }
  const pd = $("f_public_domain"); if (pd) body.public_domain = pd.value === "1";
  const desc = $("f_description"); if (desc) body.description = desc.value || null;
  for (const [k] of LISTS){ const el = $("f_"+k); if (el) body[k] = listVal(k); }
  try{
    await api("/api/admin/works/"+encodeURIComponent(wid),
      { method:"PUT", headers: auth(), body: JSON.stringify(body) });
    msg("Obra actualizada");
    await loadDetail();
  }catch(e){ msg(e.message, true); }
}
function renderRows(){
  const area = $("area");
  if (!state.items.length){ area.innerHTML = '<div class="muted">Sin obras.</div>'; return; }
  let h = "<table><thead><tr><th>ID</th><th>Título</th><th>Compositor</th><th>Catálogo</th><th>Año</th><th></th></tr></thead><tbody>";
  for (const w of state.items){
    h += `<tr><td>${esc(w.id)}</td><td><strong>${esc(w.title || "—")}</strong>${w.subtitle ? " <span class='muted'>— "+esc(w.subtitle)+"</span>" : ""}</td>
      <td>${esc(w.composer || "")}</td><td>${esc(w.catalogue || "")}</td><td>${esc(w.year || "")}</td>
      <td><div class="tools">
        <button class="ghost" onclick="openMode('view','${esc(w.id)}')">Ver</button>
        <button class="ghost" onclick="openMode('edit','${esc(w.id)}')">Editar</button>
      </div></td></tr>`;
  }
  area.innerHTML = h + "</tbody></table>";
  $("pageInfo").textContent = `página ${Math.floor(state.offset/state.limit)+1} · total ${state.total}`;
}
function openMode(m, id){ location = "?token="+encodeURIComponent(token())+"&mode="+m+"&id="+encodeURIComponent(id); }
async function loadList(){
  if (!token()) return msg("Introduce el service token.", true);
  const p = new URLSearchParams({ limit: String(state.limit), offset: String(state.offset) });
  const qv = $("q").value.trim(); if (qv) p.set("q", qv);
  try{
    const d = await api("/api/admin/works?"+p, { headers: auth() });
    state.items = d.items || []; state.total = d.total || 0;
    renderRows(); msg("");
  }catch(e){ msg(e.message, true); }
}
function backToList(){ $("detailView").classList.add("hidden");
  $("listView").classList.remove("hidden"); loadList(); }
(async function init(){
  loadToken();
  if (wid){ loadDetail(); } else {
    $("btnApply").onclick = loadList; $("btnSearch").onclick = () => { state.offset = 0; loadList(); };
    $("q").onkeydown = (e) => { if (e.key === "Enter"){ state.offset = 0; loadList(); } };
    $("prev").onclick = () => { if (state.offset >= state.limit){ state.offset -= state.limit; loadList(); } };
    $("next").onclick = () => { state.offset += state.limit; loadList(); };
    if (token()) loadList();
  }
})();
</script></body></html>
"""


def admin_works_crud_page(token: str = "") -> str:
    return _PAGE
