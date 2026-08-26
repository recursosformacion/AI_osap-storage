from __future__ import annotations

# Pantalla web de mantenimiento de osap-storage: pestañas Compositores | Obras | Tablas.
# La sirve storage en /admin; osap-api la invoca con ?token=<service-token storage:admin>.
# La página habla con /api/admin/* (protegido con storage:admin) usando el token como Bearer.

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>osap-storage · Mantenimiento</title>
<style>
  :root { --bg:#0f1115; --card:#1a1e27; --border:#2b3240; --fg:#e6e8ee; --muted:#9aa3b5; --accent:#4f8cff; --danger:#c0392b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .wrap { max-width:1200px; margin:0 auto; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 20px; }
  .tabs { display:flex; gap:8px; border-bottom:1px solid var(--border); margin-bottom:16px; }
  .tab { padding:8px 18px; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; background:none; border-top:0; border-left:0; border-right:0; font:inherit; }
  .tab.active { color:var(--fg); border-bottom-color:var(--accent); }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:16px; }
  label { display:block; color:var(--muted); margin:0 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
  input[type=text], input[type=number], select, textarea {
    width:100%; background:#0d0f14; color:var(--fg); border:1px solid var(--border);
    border-radius:6px; padding:8px 10px; font:inherit; margin-bottom:10px;
  }
  textarea { font-family:ui-monospace, SFMono-Regular, Menlo, monospace; min-height:120px; }
  .row { display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap; }
  .row .grow { flex:1; min-width:120px; }
  button { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:8px 14px; cursor:pointer; font:inherit; }
  button.ghost { background:transparent; border:1px solid var(--border); color:var(--muted); }
  button.danger { background:var(--danger); }
  button:disabled { opacity:.5; cursor:not-allowed; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top; }
  th { color:var(--muted); font-weight:600; white-space:nowrap; }
  td pre { margin:0; white-space:pre-wrap; word-break:break-word; max-width:480px; }
  .tools { display:flex; gap:8px; flex-wrap:wrap; }
  .pager { display:flex; gap:10px; align-items:center; color:var(--muted); margin-top:10px; }
  #msg { color:var(--accent); }
  #msg.err { color:#e74c3c; }
  .empty { color:var(--muted); padding:12px 0; }
  .muted { color:var(--muted); }
  .pill { display:inline-block; background:#0f172a; border:1px solid var(--border); border-radius:999px; padding:2px 10px; margin:2px; font-size:12px; }
  .hidden { display:none; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media (max-width:900px){ .grid2 { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>osap-storage · Mantenimiento</h1>
  <p class="sub">Compositores, obras y CRUD de tablas. Protegido: requiere un <b>service token</b> con scope <code>storage:admin</code>.</p>

  <div class="card">
    <label>Service token (Bearer)</label>
    <div class="row">
      <input class="grow" type="text" id="token" placeholder="pega el service token (o usa ?token=...)" />
      <button id="btnApply">Aplicar</button>
    </div>
    <div id="msg"></div>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="composers">Compositores</button>
    <button class="tab" data-tab="works">Obras</button>
    <button class="tab" data-tab="tables">Tablas</button>
  </div>

  <!-- ============ COMPOSITORES ============ -->
  <section id="tab-composers">
    <div class="card">
      <label>Listado de compositores</label>
      <div class="row">
        <input class="grow" type="text" id="cQ" placeholder="Buscar por nombre o alias..." />
        <select id="cReview" style="width:180px">
          <option value="">Estado de revisión: todos</option>
          <option value="reviewed">revisados</option>
          <option value="correct">correct</option>
          <option value="incorrect">incorrect</option>
          <option value="not_reviewed">not_reviewed</option>
        </select>
        <select id="cVisible" style="width:160px">
          <option value="visible">visibles</option>
          <option value="hidden">ocultos</option>
          <option value="all">todos</option>
        </select>
        <button id="cSearch">Buscar</button>
      </div>
      <div class="pager">
        <button class="ghost" id="cPrev">←</button>
        <span id="cPage">página 1</span>
        <button class="ghost" id="cNext">→</button>
        <span class="grow"></span>
        <label style="margin:0">límite</label>
        <select id="cLimit" style="width:90px"><option>20</option><option selected>50</option><option>100</option></select>
      </div>
    </div>
    <div class="card" id="cArea"><div class="empty">Usa el buscador.</div></div>
  </section>

  <!-- ============ OBRAS ============ -->
  <section id="tab-works" class="hidden">
    <div class="card">
      <label>Listado de obras</label>
      <div class="row">
        <input class="grow" type="text" id="wQ" placeholder="Buscar por compositor, título o catálogo..." />
        <button id="wSearch">Buscar</button>
      </div>
      <div class="pager">
        <button class="ghost" id="wPrev">←</button>
        <span id="wPage">página 1</span>
        <button class="ghost" id="wNext">→</button>
        <span class="grow"></span>
        <label style="margin:0">límite</label>
        <select id="wLimit" style="width:90px"><option>20</option><option selected>50</option><option>100</option></select>
      </div>
    </div>
    <div class="card" id="wArea"><div class="empty">Usa el buscador.</div></div>
  </section>

  <!-- ============ TABLAS (CRUD genérico) ============ -->
  <section id="tab-tables" class="hidden">
    <div class="card">
      <label>Tabla</label>
      <div class="row">
        <select class="grow" id="tableSelect"><option value="">(carga las tablas)</option></select>
        <button id="btnView">Ver filas</button>
      </div>
      <div class="pager">
        <button class="ghost" id="tPrev">←</button>
        <span id="tPage">página 1</span>
        <button class="ghost" id="tNext">→</button>
        <span class="grow"></span>
        <label style="margin:0">límite</label>
        <select id="tLimit" style="width:90px"><option>20</option><option selected>50</option><option>100</option></select>
      </div>
    </div>
    <div class="card" id="tArea"><div class="empty">Selecciona una tabla y pulsa "Ver filas".</div></div>
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
  </section>
</div>

<script>
const $ = (id) => document.getElementById(id);
let state = { composers: { offset:0, limit:50 }, works: { offset:0, limit:50 }, tables: { offset:0, limit:50 } };

function token() { return $("token").value.trim(); }
function auth() { return { "Authorization": "Bearer " + token(), "Content-Type": "application/json" }; }
function msg(t, err) { const el = $("msg"); el.textContent = t; el.className = err ? "err" : ""; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}
function api(url, opts) {
  return fetch(url, opts).then(async (r) => {
    if (r.status === 401 || r.status === 403) throw new Error("Token ausente/inválido o sin scope storage:admin");
    if (!r.ok) { let d = {}; try { d = await r.json(); } catch(e){} throw new Error((d.detail) || ("HTTP " + r.status)); }
    return r.json();
  });
}

// ---------- Pestañas ----------
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    ["composers","works","tables"].forEach((n) => $("tab-" + n).classList.toggle("hidden", n !== t.dataset.tab));
  };
});

// ---------- Compositores ----------
function cUrl() {
  const s = state.composers;
  const p = new URLSearchParams({ limit: s.limit, offset: s.offset });
  const q = $("cQ").value.trim(); if (q) p.set("q", q);
  const r = $("cReview").value; if (r) p.set("review", r);
  p.set("visible", $("cVisible").value);
  return "/api/admin/composers?" + p.toString();
}
function renderComposers(data) {
  const area = $("cArea");
  if (!data.items || !data.items.length) { area.innerHTML = '<div class="empty">Sin compositores.</div>'; return; }
  let html = "<table><thead><tr><th>Nombre</th><th>Estado</th><th>Revisión</th><th>Obras</th><th>Biografía</th><th></th></tr></thead><tbody>";
  data.items.forEach((c) => {
    const bio = (c.biography_summary || "").slice(0, 90);
    const era = c.biography_era ? '<span class="pill">' + esc(c.biography_era) + "</span>" : "";
    const nat = c.biography_nationality ? '<span class="pill">' + esc(c.biography_nationality) + "</span>" : "";
    html += `<tr>
      <td><strong>${esc(c.name)}</strong></td>
      <td>${esc(c.status)}</td>
      <td>${esc(c.review_status)}</td>
      <td>${c.works_count}</td>
      <td>${era}${nat}<br><span class="muted">${esc(bio)}${bio.length ? "…" : ""}</span></td>
      <td><div class="tools"><button class="ghost" onclick="openComposer('${esc(c.id)}')">Editar</button></div></td>
    </tr>`;
  });
  html += "</tbody></table>";
  area.innerHTML = html;
  $("cPage").textContent = `página ${Math.floor(state.composers.offset / state.composers.limit) + 1} · total ${data.total}`;
}
async function loadComposers() {
  if (!token()) return msg("Introduce el service token.", true);
  try {
    const data = await api(cUrl(), { headers: auth() });
    renderComposers(data);
    msg("");
  } catch (e) { msg(e.message, true); }
}

// ---------- Obras ----------
function wUrl() {
  const s = state.works;
  const p = new URLSearchParams({ limit: s.limit, offset: s.offset });
  const q = $("wQ").value.trim(); if (q) p.set("q", q);
  return "/api/admin/works?" + p.toString();
}
function renderWorks(data) {
  const area = $("wArea");
  if (!data.items || !data.items.length) { area.innerHTML = '<div class="empty">Sin obras.</div>'; return; }
  let html = "<table><thead><tr><th>ID</th><th>Título</th><th>Compositor</th><th>Catálogo</th><th>Año</th><th></th></tr></thead><tbody>";
  data.items.forEach((w) => {
    html += `<tr>
      <td>${w.id}</td>
      <td><strong>${esc(w.title || "")}</strong>${w.subtitle ? "<br><span class='muted'>" + esc(w.subtitle) + "</span>" : ""}</td>
      <td>${esc(w.composer || "")}</td>
      <td>${esc(w.catalogue || "")}</td>
      <td>${esc(w.year ?? "")}</td>
      <td><div class="tools"><button class="ghost" onclick="openWork('${w.id}')">Editar</button></div></td>
    </tr>`;
  });
  html += "</tbody></table>";
  area.innerHTML = html;
  $("wPage").textContent = `página ${Math.floor(state.works.offset / state.works.limit) + 1} · total ${data.total}`;
}
async function loadWorks() {
  if (!token()) return msg("Introduce el service token.", true);
  try {
    const data = await api(wUrl(), { headers: auth() });
    renderWorks(data);
    msg("");
  } catch (e) { msg(e.message, true); }
}

// ---------- Detalle / edición de compositor ----------
window.openComposer = async (id) => {
  try {
    const d = await api("/api/admin/composers/" + encodeURIComponent(id), { headers: auth() });
    const bio = d.biography_summary ? await api("/api/admin/composers/" + encodeURIComponent(id) + "/biography", { headers: auth() }) : d;
    const b = bio.biography_summary ? bio : {};
    const aliases = (d.aliases || []).map(esc).join(", ");
    const ids = (d.identifiers || []).map((i) => i.id_type + ": " + i.id_value).join(", ");
    const area = $("cArea");
    area.innerHTML = `
      <h3 style="margin-top:0">${esc(d.name)} <span class="muted">(${esc(d.id)})</span></h3>
      <div class="grid2">
        <div class="card">
          <label>Identidad</label>
          <input type="text" id="eName" value="${esc(d.name)}" />
          <div class="row">
            <div class="grow"><label>Nacimiento</label><input type="text" id="eBirth" value="${esc(d.birth_year || "")}" /></div>
            <div class="grow"><label>Fallecimiento</label><input type="text" id="eDeath" value="${esc(d.death_year || "")}" /></div>
          </div>
          <div class="row">
            <div class="grow"><label>Status</label>
              <select id="eStatus"><option ${d.status==="active"?"selected":""}>active</option><option ${d.status==="candidate"?"selected":""}>candidate</option><option ${d.status==="merged"?"selected":""}>merged</option></select>
            </div>
            <div class="grow"><label>Visible</label>
              <select id="eVisible"><option value="1" ${d.visible?"selected":""}>sí</option><option value="0" ${d.visible?"":"selected"}>no</option></select>
            </div>
          </div>
          <div class="row">
            <div class="grow"><label>review_status</label>
              <select id="eReview"><option value="">(sin cambio)</option>${["correct","incorrect","reviewed","not_reviewed"].map((v)=>"<option "+ (d.review_status===v?"selected":"") +">"+v+"</option>").join("")}</select>
            </div>
            <div class="grow"><label>cluster_id</label><input type="text" id="eCluster" value="${esc(d.cluster_id || "")}" /></div>
          </div>
          <label>musicbrainz_id</label>
          <input type="text" id="eMbid" value="${esc(d.musicbrainz_id || "")}" />
          <button onclick="saveComposer('${esc(d.id)}')">Guardar identidad</button>
        </div>
        <div class="card">
          <label>Biografía</label>
          <textarea id="bSummary" placeholder="Resumen">${esc(b.biography_summary || "")}</textarea>
          <div class="row">
            <div class="grow"><label>Época</label><input type="text" id="bEra" value="${esc(b.biography_era || "")}" /></div>
            <div class="grow"><label>Nacionalidad</label><input type="text" id="bNat" value="${esc(b.biography_nationality || "")}" /></div>
          </div>
          <label>Obras clave (separadas por |)</label>
          <input type="text" id="bWorks" value="${esc((b.biography_key_works || []).join(" | "))}" />
          <label>Dato clave</label>
          <input type="text" id="bFact" value="${esc(b.biography_key_fact || "")}" />
          <label>Referencias (fuente|URL, una por línea)</label>
          <textarea id="bRefs">${esc((b.biography_references || []).map((r) => (r.source ? r.source + "|" : "") + (r.url || "")).join("\n"))}</textarea>
          <button onclick="saveBiography('${esc(d.id)}')">Guardar biografía</button>
        </div>
      </div>
      <div class="card">
        <label>Alias</label>
        <div class="muted">${aliases || "(sin alias)"}</div>
        <div class="row" style="margin-top:8px">
          <input class="grow" type="text" id="newAlias" placeholder="nuevo alias" />
          <button onclick="addAlias('${esc(d.id)}')">Añadir alias</button>
        </div>
      </div>
      <div class="card">
        <label>Identificadores externos</label>
        <div class="muted">${ids || "(sin identificadores)"}</div>
      </div>
      <div class="card">
        <label>Obras asociadas</label>
        <button class="ghost" onclick="loadComposerWorks('${esc(d.id)}')">Cargar obras</button>
        <div id="cWorksArea"></div>
      </div>
      <div class="row">
        <button class="ghost" onclick="loadComposers()">← Volver al listado</button>
      </div>`;
  } catch (e) { msg(e.message, true); }
};

window.saveComposer = async (id) => {
  const body = {
    name: $("eName").value,
    birth_year: $("eBirth").value || null,
    death_year: $("eDeath").value || null,
    status: $("eStatus").value,
    visible: $("eVisible").value === "1",
    review_status: $("eReview").value || null,
    cluster_id: $("eCluster").value || null,
    musicbrainz_id: $("eMbid").value || null,
  };
  try {
    await api("/api/admin/composers/" + encodeURIComponent(id), { method: "PUT", headers: auth(), body: JSON.stringify(body) });
    msg("Compositor guardado.");
    openComposer(id);
  } catch (e) { msg(e.message, true); }
};

window.saveBiography = async (id) => {
  const body = {
    summary: $("bSummary").value,
    era: $("bEra").value || null,
    nationality: $("bNat").value || null,
    key_works: $("bWorks").value.split("|").map((s) => s.trim()).filter(Boolean),
    key_fact: $("bFact").value || null,
    references: $("bRefs").value.split("\n").map((l) => l.trim()).filter(Boolean)
      .map((l) => {
        const i = l.indexOf("|");
        if (i === -1) return { source: "", url: l };
        return { source: l.slice(0, i).trim(), url: l.slice(i + 1).trim() };
      }),
  };
  try {
    await api("/api/admin/composers/" + encodeURIComponent(id) + "/biography", { method: "PUT", headers: auth(), body: JSON.stringify(body) });
    msg("Biografía guardada.");
    openComposer(id);
  } catch (e) { msg(e.message, true); }
};

window.addAlias = async (id) => {
  const alias = $("newAlias").value.trim();
  if (!alias) return msg("Escribe un alias.", true);
  try {
    await api("/api/admin/composers/" + encodeURIComponent(id) + "/aliases", { method: "POST", headers: auth(), body: JSON.stringify({ alias }) });
    msg("Alias añadido.");
    openComposer(id);
  } catch (e) { msg(e.message, true); }
};

window.loadComposerWorks = async (id) => {
  try {
    const data = await api("/api/admin/composers/" + encodeURIComponent(id) + "/works?limit=20&offset=0", { headers: auth() });
    const area = $("cWorksArea");
    if (!data.items || !data.items.length) { area.innerHTML = '<div class="muted">Sin obras.</div>'; return; }
    area.innerHTML = "<table><thead><tr><th>ID</th><th>Título</th></tr></thead><tbody>" +
      data.items.map((w) => `<tr><td>${w.work_id}</td><td>${esc(w.title || "")}</td></tr>`).join("") +
      "</tbody></table>";
  } catch (e) { msg(e.message, true); }
};

// ---------- Detalle / edición de obra ----------
window.openWork = async (id) => {
  try {
    const d = await api("/api/admin/works/" + id, { headers: auth() });
    const w = d;
    const area = $("wArea");
    area.innerHTML = `
      <h3 style="margin-top:0">#${w.id} ${esc(w.title || "")} <span class="muted">(${esc(w.composer || "")})</span></h3>
      <div class="card">
        <label>Metadatos</label>
        <div class="row">
          <div class="grow"><label>Título</label><input type="text" id="wTitle" value="${esc(w.title || "")}" /></div>
          <div class="grow"><label>Subtítulo</label><input type="text" id="wSubtitle" value="${esc(w.subtitle || "")}" /></div>
        </div>
        <div class="row">
          <div class="grow"><label>Compositor (texto)</label><input type="text" id="wComposer" value="${esc(w.composer || "")}" /></div>
          <div class="grow"><label>composer_id</label><input type="text" id="wComposerId" value="${esc(w.composer_id || "")}" /></div>
        </div>
        <div class="row">
          <div class="grow"><label>Género</label><input type="text" id="wGenre" value="${esc(w.genre || "")}" /></div>
          <div class="grow"><label>Opus</label><input type="text" id="wOpus" value="${esc(w.opus || "")}" /></div>
          <div class="grow"><label>Catálogo</label><input type="text" id="wCatalogue" value="${esc(w.catalogue || "")}" /></div>
        </div>
        <div class="row">
          <div class="grow"><label>Tonalidad</label><input type="text" id="wKey" value="${esc(w.musical_key || "")}" /></div>
          <div class="grow"><label>Año</label><input type="number" id="wYear" value="${esc(w.year ?? "")}" /></div>
          <div class="grow"><label>Idioma</label><input type="text" id="wLang" value="${esc(w.language || "")}" /></div>
        </div>
        <div class="row">
          <div class="grow"><label>Instrumentación</label><input type="text" id="wInstr" value="${esc(w.instrumentation || "")}" /></div>
          <div class="grow"><label>Licencia</label><input type="text" id="wLicense" value="${esc(w.license || "")}" /></div>
          <div class="grow"><label>Dominio público</label>
            <select id="wPd"><option value="1" ${w.public_domain?"selected":""}>sí</option><option value="0" ${w.public_domain?"":"selected"}>no</option></select>
          </div>
        </div>
        <label>Descripción</label>
        <textarea id="wDesc">${esc(w.description || "")}</textarea>
        <button onclick="saveWork('${w.id}')">Guardar obra</button>
      </div>
      <div class="grid2">
        <div class="card">
          <label>Tags</label>
          <input type="text" id="wTags" value="${esc((w.tags || []).join(" | "))}" />
          <button class="ghost" onclick="saveWorkLists('${w.id}')">Guardar listas</button>
        </div>
        <div class="card">
          <label>Géneros · Instrumentos · Partes</label>
          <input type="text" id="wGenres" placeholder="géneros (|)" value="${esc((w.genres || []).join(" | "))}" />
          <input type="text" id="wInstruments" placeholder="instrumentos (|)" value="${esc((w.instruments || []).join(" | "))}" />
          <input type="text" id="wParts" placeholder="partes (|)" value="${esc((w.parts_names || []).join(" | "))}" />
          <button class="ghost" onclick="saveWorkLists('${w.id}')">Guardar listas</button>
        </div>
      </div>
      <div class="row">
        <button class="ghost" onclick="loadWorks()">← Volver al listado</button>
      </div>`;
  } catch (e) { msg(e.message, true); }
};

window.saveWork = async (id) => {
  const body = {
    title: $("wTitle").value,
    subtitle: $("wSubtitle").value || null,
    composer: $("wComposer").value || null,
    composer_id: $("wComposerId").value || null,
    genre: $("wGenre").value || null,
    opus: $("wOpus").value || null,
    catalogue: $("wCatalogue").value || null,
    musical_key: $("wKey").value || null,
    year: $("wYear").value ? parseInt($("wYear").value, 10) : null,
    language: $("wLang").value || null,
    instrumentation: $("wInstr").value || null,
    license: $("wLicense").value || null,
    public_domain: $("wPd").value === "1",
    description: $("wDesc").value || null,
  };
  try {
    await api("/api/admin/works/" + id, { method: "PUT", headers: auth(), body: JSON.stringify(body) });
    msg("Obra guardada.");
    openWork(id);
  } catch (e) { msg(e.message, true); }
};

window.saveWorkLists = async (id) => {
  const split = (v) => v.split("|").map((s) => s.trim()).filter(Boolean);
  const body = {
    tags: split($("wTags").value),
    genres: split($("wGenres").value),
    instruments: split($("wInstruments").value),
    parts_names: split($("wParts").value),
  };
  try {
    await api("/api/admin/works/" + id, { method: "PUT", headers: auth(), body: JSON.stringify(body) });
    msg("Listas guardadas.");
    openWork(id);
  } catch (e) { msg(e.message, true); }
};

// ---------- CRUD genérico de tablas ----------
let currentTable = null;
let pkCol = "id";
function tableUrl() {
  const s = state.tables;
  return `/api/admin/tables/${encodeURIComponent(currentTable)}?limit=${s.limit}&offset=${s.offset}`;
}
async function loadTables() {
  if (!token()) return msg("Introduce el service token.", true);
  try {
    const data = await api("/api/admin/tables", { headers: auth() });
    const sel = $("tableSelect");
    sel.innerHTML = '<option value="">(elige tabla)</option>';
    (data.tables || []).forEach((t) => {
      const o = document.createElement("option"); o.value = t; o.textContent = t; sel.appendChild(o);
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
    const data = await api(tableUrl(), { headers: auth() });
    renderRows(data.rows || []);
    $("tPage").textContent = `página ${Math.floor(state.tables.offset / state.tables.limit) + 1} · ${(data.rows||[]).length} filas`;
    msg("");
  } catch (e) { msg(e.message, true); }
}
function renderRows(rows) {
  const area = $("tArea");
  if (!rows.length) { area.innerHTML = '<div class="empty">Sin filas.</div>'; return; }
  const cols = Object.keys(rows[0]);
  let html = "<table><thead><tr>" + cols.map((c) => "<th>" + esc(c) + "</th>").join("") + "<th></th></tr></thead><tbody>";
  rows.forEach((row, i) => {
    html += "<tr>" + cols.map((c) => {
      const v = row[c];
      const s = (v === null || v === undefined) ? "" : (typeof v === "object" ? JSON.stringify(v) : String(v));
      return "<td><pre>" + esc(s) + "</pre></td>";
    }).join("") + `<td><div class="tools"><button class="ghost" onclick="editRow(${i})">Editar</button><button class="danger" onclick="delRow(${i})">Borrar</button></div></td></tr>`;
  });
  html += "</tbody></table>";
  area.innerHTML = html;
  window.__rows = rows;
  window.__cols = cols;
}
function findPk(row) {
  const names = Object.keys(row);
  return names.find((n) => n === "id" || n.endsWith("_id")) || names[0];
}
window.editRow = (i) => {
  const row = window.__rows[i];
  const pk = findPk(row);
  const data = Object.fromEntries(Object.entries(row).filter(([k]) => k !== pk));
  $("jsonEditor").value = JSON.stringify(data, null, 2);
  $("editPk").textContent = `editando PK ${pk}=${JSON.stringify(row[pk])} de ${currentTable}`;
};
window.delRow = (i) => {
  const row = window.__rows[i];
  const pk = findPk(row);
  if (!confirm(`¿Borrar fila con ${pk}=${JSON.stringify(row[pk])} en ${currentTable}?`)) return;
  api(`/api/admin/tables/${encodeURIComponent(currentTable)}/${encodeURIComponent(row[pk])}`, { method: "DELETE", headers: auth() })
    .then(() => { msg("Fila borrada."); viewRows(); })
    .catch((e) => msg(e.message, true));
};
window.createRow = () => {
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
};

// ---------- Init ----------
function init() {
  const q = new URLSearchParams(location.search).get("token");
  if (q) $("token").value = q;
  $("btnApply").onclick = () => { loadComposers(); loadTables(); };
  $("cSearch").onclick = () => { state.composers.offset = 0; loadComposers(); };
  $("cQ").onkeydown = (e) => { if (e.key === "Enter") { state.composers.offset = 0; loadComposers(); } };
  $("cPrev").onclick = () => { if (state.composers.offset >= state.composers.limit) { state.composers.offset -= state.composers.limit; loadComposers(); } };
  $("cNext").onclick = () => { state.composers.offset += state.composers.limit; loadComposers(); };
  $("cLimit").onchange = () => { state.composers.limit = parseInt($("cLimit").value, 10); state.composers.offset = 0; loadComposers(); };
  $("wSearch").onclick = () => { state.works.offset = 0; loadWorks(); };
  $("wQ").onkeydown = (e) => { if (e.key === "Enter") { state.works.offset = 0; loadWorks(); } };
  $("wPrev").onclick = () => { if (state.works.offset >= state.works.limit) { state.works.offset -= state.works.limit; loadWorks(); } };
  $("wNext").onclick = () => { state.works.offset += state.works.limit; loadWorks(); };
  $("wLimit").onchange = () => { state.works.limit = parseInt($("wLimit").value, 10); state.works.offset = 0; loadWorks(); };
  $("btnView").onclick = viewRows;
  $("btnCreate").onclick = window.createRow;
  $("btnClear").onclick = () => { $("jsonEditor").value = ""; $("editPk").textContent = ""; };
  $("tPrev").onclick = () => { if (state.tables.offset >= state.tables.limit) { state.tables.offset -= state.tables.limit; viewRows(); } };
  $("tNext").onclick = () => { state.tables.offset += state.tables.limit; viewRows(); };
  $("tLimit").onchange = () => { state.tables.limit = parseInt($("tLimit").value, 10); state.tables.offset = 0; viewRows(); };
  $("token").onkeydown = (e) => { if (e.key === "Enter") { loadComposers(); loadTables(); } };
}
init();
</script>
</body>
</html>
"""


def admin_maintenance_page(token: str = "") -> str:
    return _PAGE
