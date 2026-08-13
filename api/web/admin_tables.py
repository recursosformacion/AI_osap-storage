from __future__ import annotations

# Pantalla web completa del CRUD de tablas de osap-storage. La sirve storage; osap-api
# la invoca enlazando a /admin?token=<service-token>. Storage es ajeno a usuarios: la
# página solo presenta el token de servicio que osap-api le pasa y lo envía como Bearer
# a /api/admin/tables/* (protegido con storage:admin).

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>osap-storage · Admin CRUD</title>
<style>
  :root { --bg:#0f1115; --card:#1a1e27; --border:#2b3240; --fg:#e6e8ee; --muted:#9aa3b5; --accent:#4f8cff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .wrap { max-width:1100px; margin:0 auto; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 20px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:16px; }
  label { display:block; color:var(--muted); margin:0 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
  input[type=text], select, textarea {
    width:100%; background:#0d0f14; color:var(--fg); border:1px solid var(--border);
    border-radius:6px; padding:8px 10px; font:inherit; margin-bottom:10px;
  }
  textarea { font-family:ui-monospace, SFMono-Regular, Menlo, monospace; min-height:120px; }
  .row { display:flex; gap:10px; align-items:flex-end; }
  .row .grow { flex:1; }
  button { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:8px 14px; cursor:pointer; font:inherit; }
  button.ghost { background:transparent; border:1px solid var(--border); color:var(--muted); }
  button.danger { background:#c0392b; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top; }
  th { color:var(--muted); font-weight:600; white-space:nowrap; }
  td pre { margin:0; white-space:pre-wrap; word-break:break-word; max-width:520px; }
  .tools { display:flex; gap:8px; }
  .pager { display:flex; gap:10px; align-items:center; color:var(--muted); margin-top:10px; }
  #msg { color:var(--accent); }
  #msg.err { color:#e74c3c; }
  .empty { color:var(--muted); padding:12px 0; }
  .muted { color:var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <h1>osap-storage · Administración de tablas</h1>
  <p class="sub">CRUD genérico sobre las tablas. Protegido: requiere un <b>service token</b> con scope <code>storage:admin</code>.</p>

  <div class="card">
    <label>Service token (Bearer)</label>
    <div class="row">
      <input class="grow" type="text" id="token" placeholder="pega el service token (o usa ?token=...)" />
      <button id="btnLoad">Cargar tablas</button>
    </div>
    <div id="msg"></div>
  </div>

  <div class="card">
    <label>Tabla</label>
    <div class="row">
      <select class="grow" id="tableSelect"><option value="">(carga las tablas)</option></select>
      <button id="btnView">Ver filas</button>
    </div>
    <div class="pager">
      <button class="ghost" id="prev">←</button>
      <span id="pageInfo">página 0</span>
      <button class="ghost" id="next">→</button>
      <span class="grow"></span>
      <label style="margin:0">límite</label>
      <select id="limitSel" style="width:90px"><option>20</option><option selected>50</option><option>100</option></select>
    </div>
  </div>

  <div class="card">
    <div id="rowsArea"><div class="empty">Selecciona una tabla y pulsa "Ver filas".</div></div>
  </div>

  <div class="card">
    <label>Editar / Añadir fila (JSON)</label>
    <textarea id="jsonEditor" placeholder='{ "columna": "valor", ... }'></textarea>
    <div class="row">
      <button id="btnCreate">Crear</button>
      <button class="ghost" id="btnClear">Limpiar</button>
      <span class="grow"></span>
      <span id="editPk" class="muted"></span>
    </div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
let currentTable = null;
let offset = 0;
let limit = 50;
let pkCol = "id";

function token() { return $("token").value.trim(); }
function auth() { return { "Authorization": "Bearer " + token(), "Content-Type": "application/json" }; }
function msg(t, err) { const el = $("msg"); el.textContent = t; el.className = err ? "err" : ""; }
function api(url, opts) {
  return fetch(url, opts).then(async (r) => {
    if (r.status === 401 || r.status === 403) throw new Error("Token ausente/inválido o sin scope storage:admin");
    if (!r.ok) { let d = {}; try { d = await r.json(); } catch(e){} throw new Error((d.detail) || ("HTTP " + r.status)); }
    return r.json();
  });
}

function init() {
  const q = new URLSearchParams(location.search).get("token");
  if (q) $("token").value = q;
  $("btnLoad").onclick = loadTables;
  $("btnView").onclick = viewRows;
  $("btnCreate").onclick = createRow;
  $("btnClear").onclick = () => { $("jsonEditor").value = ""; $("editPk").textContent = ""; };
  $("prev").onclick = () => { if (offset >= limit) { offset -= limit; viewRows(); } };
  $("next").onclick = () => { offset += limit; viewRows(); };
  $("limitSel").onchange = () => { limit = parseInt($("limitSel").value, 10); offset = 0; viewRows(); };
  $("token").onkeydown = (e) => { if (e.key === "Enter") loadTables(); };
}

async function loadTables() {
  if (!token()) return msg("Introduce el service token.", true);
  try {
    const data = await api("/api/admin/tables", { headers: auth() });
    const sel = $("tableSelect");
    sel.innerHTML = '<option value="">(elige tabla)</option>';
    (data.tables || []).forEach((t) => {
      const o = document.createElement("option");
      o.value = t; o.textContent = t; sel.appendChild(o);
    });
    msg("Tablas cargadas: " + (data.tables || []).length);
  } catch (e) { msg(e.message, true); }
}

async function viewRows() {
  if (!token()) return msg("Introduce el service token.", true);
  const t = $("tableSelect").value;
  if (!t) return msg("Elige una tabla.", true);
  currentTable = t;
  try {
    const data = await api(`/api/admin/tables/${encodeURIComponent(t)}?limit=${limit}&offset=${offset}`, { headers: auth() });
    renderRows(data.rows || []);
    pkCol = data.rows && data.rows[0] && Object.keys(data.rows[0]).length ? null : "id";
    $("pageInfo").textContent = `página ${Math.floor(offset / limit) + 1} · ${(data.rows||[]).length} filas`;
    msg("");
  } catch (e) { msg(e.message, true); }
}

function renderRows(rows) {
  const area = $("rowsArea");
  if (!rows.length) { area.innerHTML = '<div class="empty">Sin filas.</div>'; return; }
  const cols = Object.keys(rows[0]);
  let html = "<table><thead><tr>" + cols.map((c) => "<th>" + escape(c) + "</th>").join("") + "<th></th></tr></thead><tbody>";
  rows.forEach((row, i) => {
    html += "<tr>" + cols.map((c) => {
      const v = row[c];
      const s = (v === null || v === undefined) ? "" : (typeof v === "object" ? JSON.stringify(v) : String(v));
      return "<td><pre>" + escape(s) + "</pre></td>";
    }).join("") + `<td><div class="tools"><button class="ghost" onclick="editRow(${i})">Editar</button><button class="danger" onclick="delRow(${i})">Borrar</button></div></td></tr>`;
  });
  html += "</tbody></table>";
  area.innerHTML = html;
  window.__rows = rows;
  window.__cols = cols;
}

function findPk(row) {
  // Usa la primera columna que parece clave (id, work_id, composer_id...) o la primera.
  const names = Object.keys(row);
  return names.find((n) => n === "id" || n.endsWith("_id")) || names[0];
}

function editRow(i) {
  const row = window.__rows[i];
  const pk = findPk(row);
  const data = Object.fromEntries(Object.entries(row).filter(([k]) => k !== pk));
  $("jsonEditor").value = JSON.stringify(data, null, 2);
  $("editPk").textContent = `editando PK ${pk}=${JSON.stringify(row[pk])} de ${currentTable}`;
}

function delRow(i) {
  const row = window.__rows[i];
  const pk = findPk(row);
  if (!confirm(`¿Borrar fila con ${pk}=${JSON.stringify(row[pk])} en ${currentTable}?`)) return;
  api(`/api/admin/tables/${encodeURIComponent(currentTable)}/${encodeURIComponent(row[pk])}`, { method: "DELETE", headers: auth() })
    .then(() => { msg("Fila borrada."); viewRows(); })
    .catch((e) => msg(e.message, true));
}

function createRow() {
  if (!currentTable) return msg("Elige una tabla.", true);
  let data;
  try { data = JSON.parse($("jsonEditor").value || "{}"); } catch (e) { return msg("JSON inválido.", true); }
  const pkText = $("editPk").textContent;
  const isEdit = /editando/.test(pkText);
  const pk = window.__cols ? window.__cols.find((c) => c === "id" || c.endsWith("_id")) : null;
  const pkVal = isEdit ? JSON.parse(pkText.split("=")[1]) : null;
  const url = isEdit
    ? `/api/admin/tables/${encodeURIComponent(currentTable)}/${encodeURIComponent(pkVal)}`
    : `/api/admin/tables/${encodeURIComponent(currentTable)}`;
  const method = isEdit ? "PUT" : "POST";
  api(url, { method, headers: auth(), body: JSON.stringify(data) })
    .then((r) => { msg("Fila " + (isEdit ? "actualizada" : "creada") + " (PK " + (r.row[pk] || "") + ")"); $("editPk").textContent = ""; viewRows(); })
    .catch((e) => msg(e.message, true));
}

init();
</script>
</body>
</html>
"""


def admin_tables_page(token: str = "") -> str:
    return _PAGE
