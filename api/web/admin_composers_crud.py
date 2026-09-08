"""Página de administración: Mantenimiento compositores (CRUD convencional standalone).

NO es parte del multimantenimiento. Muestra el listado del fichero `composers`
(30/página, paginación) y un detalle Ver/Editar por compositor usando los endpoints
de admin existentes:
  GET /api/admin/composers?visible=all&limit&offset
  GET  /api/admin/composers/{id}
  PUT  /api/admin/composers/{id}      (identidad)

El token de servicio llega por URL (?token=...); si no viene, se muestra la caja
para pegarlo.
"""

from __future__ import annotations

_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mantenimiento compositores</title>
<style>
  :root{ --border:#334155; --muted:#94a3b8; --bg:#0f172a; --card:#1e293b; --accent:#38bdf8; }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:#e2e8f0;
      font:14px/1.5 system-ui,Segoe UI,sans-serif;}
  .wrap{max-width:1000px;margin:0 auto;padding:16px}
  h1{font-size:20px} .sub{color:var(--muted);margin-top:-8px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px;
        padding:14px;margin:12px 0}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  input,select,textarea{background:#0b1524;color:#e2e8f0;border:1px solid var(--border);
        border-radius:8px;padding:7px 9px;font:inherit}
  input:disabled{opacity:.75}
  textarea{width:100%;min-height:70px}
  table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:7px 8px;
        border-bottom:1px solid var(--border);vertical-align:top}
  th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase}
  button{cursor:pointer;border:1px solid var(--border);border-radius:8px;padding:7px 12px;
        background:#0b1524;color:#e2e8f0}
  button.ghost{background:transparent} button:hover{border-color:var(--accent);color:#fff}
  .tools{display:flex;gap:6px}
  a{color:var(--accent)} .muted{color:var(--muted)}
  .hidden{display:none} .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  @media(max-width:760px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
  <h1>Mantenimiento compositores</h1>
  <p class="sub">Listado del fichero <code>composers</code> · 30 filas por página.</p>

  <div class="card" id="tokenCard">
    <label>Service token (Bearer)</label>
    <div class="row">
      <input class="grow" style="flex:1" id="token" placeholder="pega el service token (o usa ?token=...)" />
      <button id="btnApply">Aplicar</button>
    </div>
  </div>
  <div id="msg" class="muted"></div>

  <div id="listView">
    <div class="card"><div class="row" style="justify-content:space-between">
      <div class="row">
        <label>Buscar <input id="q" placeholder="nombre o alias" /></label>
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
const cid = qs("id") || "";
const state = { items: [], total: 0, limit: 30, offset: 0 };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
function token(){ const v = q || $("token").value; return v.trim(); }
function auth(){ return { Authorization: "Bearer " + token() }; }
const $ = (i) => document.getElementById(i);
let EP = [];
async function loadEpochs(){ try { EP = await api("/api/admin/epochs"); } catch(e){ EP = []; } }
function eraTitle(v){ if (/^\\d+$/.test(String(v || ""))){ const f = EP.find(e => String(e.id) === String(v)); if (f) return f.title; } return v ? String(v) : "—"; }
function eraOptions(cur){
  let o = '<option value="">(sin época)</option>';
  for (const e of EP){ o += `<option value="${e.id}" ${String(cur || "") === String(e.id) ? "selected" : ""}>${esc(e.title)}</option>`; }
  return o;
}
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
function renderDetail(d){
  const identity = [
    ["name","Nombre"],["birth_year","Nacimiento"],["death_year","Fallecimiento"],
    ["cluster_id","cluster_id"],["musicbrainz_id","musicbrainz_id"]
  ];
  const editable = mode === "edit";
  let h = `<h2>${esc(d.name)} <span class="muted">(${esc(d.id)})</span></h2>
    <div class="card"><h3>Identidad</h3><div class="grid">`;
  for (const [k,lab] of identity){
    h += `<label>${lab}<br><input id="f_${k}" value="${esc(d[k] ?? "")}" ${editable?"":"disabled"} /></label>`;
  }
  h += `<label>Status<br><select id="f_status" ${editable?"":"disabled"}>
      ${["active","candidate","merged"].map(v=>`<option ${d.status===v?"selected":""}>${v}</option>`).join("")}
    </select></label>
    <label>Visible<br><select id="f_visible" ${editable?"":"disabled"}>
      <option value="1" ${d.visible?"selected":""}>sí</option>
      <option value="0" ${d.visible?"":"selected"}>no</option>
    </select></label></div>
    <label>Homepage (URL)<br><input id="f_homepage" value="${esc(d.homepage || "")}" ${editable?"":"disabled"} style="width:100%" /></label>
    <h3>Biografía</h3><div class="grid">
      <label>Resumen<br><textarea id="f_bio" ${editable?"":"disabled"}>${esc(d.biography_summary || "")}</textarea></label>
      <label>Época<br>${editable ? `<select id="f_era">${eraOptions(d.biography_era)}</select>` : `<span>${esc(eraTitle(d.biography_era))}</span>`}</label>
      <label>Nacionalidad<br><input id="f_nat" value="${esc(d.biography_nationality||"")}" ${editable?"":"disabled"} /></label>
    </div>`;
  if (editable) h += `<div class="row" style="margin-top:10px"><button onclick="saveId()">Guardar</button></div>`;
  h += `<button style="margin-top:10px" onclick="backToList()">← Volver al listado</button></div>`;
  $("detailView").innerHTML = h; $("listView").classList.add("hidden");
  $("detailView").classList.remove("hidden");
}
async function loadDetail(){
  try{
    const d = await api("/api/admin/composers/"+encodeURIComponent(cid), { headers: auth() });
    if (!d.biography_summary){
      try { const b = await api("/api/admin/composers/"+encodeURIComponent(cid)+"/biography", { headers: auth() });
        Object.assign(d, b); } catch(e){}
    }
    renderDetail(d); msg("");
  }catch(e){ msg(e.message, true); }
}
async function saveId(){
  const d = await api("/api/admin/composers/"+encodeURIComponent(cid), { headers: auth() });
  const body = {
    name: $("f_name").value, birth_year: $("f_birth_year").value || null,
    death_year: $("f_death_year").value || null, homepage: $("f_homepage").value || null,
    cluster_id: $("f_cluster_id").value || null, musicbrainz_id: $("f_musicbrainz_id").value || null,
    status: $("f_status").value, visible: $("f_visible").value === "1",
    review_status: d.review_status || null, review_reason: d.review_reason || null,
  };
  try{
    await api("/api/admin/composers/"+encodeURIComponent(cid),
      { method:"PUT", headers: auth(), body: JSON.stringify(body) });
    await api("/api/admin/composers/"+encodeURIComponent(cid)+"/biography",
      { method:"PUT", headers: auth(), body: JSON.stringify({
          summary: $("f_bio") ? ($("f_bio").value || null) : null,
          era: $("f_era") ? ($("f_era").value || null) : null,
          nationality: $("f_nat") ? ($("f_nat").value || null) : null,
      }) });
    msg("Compositor actualizado");
  }catch(e){ msg(e.message, true); }
}
function renderRows(){
  const area = $("area");
  if (!state.items.length){ area.innerHTML = '<div class="muted">Sin compositores.</div>'; return; }
  let h = "<table><thead><tr><th>ID</th><th>Name</th><th>Nac.</th><th>Muerte</th><th>Visible</th><th></th></tr></thead><tbody>";
  for (const c of state.items){
    h += `<tr><td>${esc(c.id)}</td><td><strong>${esc(c.name)}</strong></td>
      <td>${esc(c.birth_year || "")}</td><td>${esc(c.death_year || "")}</td>
      <td>${c.visible ? "sí" : "no"}</td>
      <td><div class="tools">
        <button class="ghost" onclick="openMode('view','${esc(c.id)}')">Ver</button>
        <button class="ghost" onclick="openMode('edit','${esc(c.id)}')">Editar</button>
      </div></td></tr>`;
  }
  area.innerHTML = h + "</tbody></table>";
  $("pageInfo").textContent = `página ${Math.floor(state.offset/state.limit)+1} · total ${state.total}`;
}
function openMode(m, id){ location = "?token="+encodeURIComponent(token())+"&mode="+m+"&id="+encodeURIComponent(id); }
async function loadList(){
  if (!token()) return msg("Introduce el service token.", true);
  const p = new URLSearchParams({ visible: "all", limit: String(state.limit), offset: String(state.offset) });
  const qv = $("q").value.trim(); if (qv) p.set("q", qv);
  try{
    const d = await api("/api/admin/composers?"+p, { headers: auth() });
    state.items = d.items || []; state.total = d.total || 0;
    renderRows(); msg("");
  }catch(e){ msg(e.message, true); }
}
function backToList(){ $("detailView").classList.add("hidden");
  $("listView").classList.remove("hidden"); loadList(); }
(async function init(){
  loadToken();
  await loadEpochs();
  if (cid){ loadDetail(); } else {
    $("btnApply").onclick = loadList; $("btnSearch").onclick = () => { state.offset = 0; loadList(); };
    $("q").onkeydown = (e) => { if (e.key === "Enter"){ state.offset = 0; loadList(); } };
    $("prev").onclick = () => { if (state.offset >= state.limit){ state.offset -= state.limit; loadList(); } };
    $("next").onclick = () => { state.offset += state.limit; loadList(); };
    if (token()) loadList();
  }
})();
</script></body></html>
"""


def admin_composers_crud_page(token: str = "") -> str:
    return _PAGE
