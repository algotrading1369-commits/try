const state = {
  status: null,
  planets: null,
  fleets: null,
  config: null,
  liveLogs: [],
  password: localStorage.getItem("panel_password") || "",
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const fmt = (n) => (typeof n === "number" ? Math.round(n).toLocaleString("es-ES") : n);
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("es-ES");
const fmtDateTime = (ts) => new Date(ts * 1000).toLocaleString("es-ES");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function toast(message, type = "info", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

async function api(path, options = {}) {
  options.headers = { ...(options.headers || {}), "X-Panel-Password": state.password };
  const resp = await fetch(path, options);
  if (resp.status === 401) {
    showAuth();
    throw new Error("Contraseña requerida");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || resp.statusText);
  }
  return resp.json();
}

function showAuth() {
  $("#auth-overlay").classList.remove("hidden");
}

$("#auth-submit").addEventListener("click", () => {
  state.password = $("#auth-password").value;
  localStorage.setItem("panel_password", state.password);
  $("#auth-overlay").classList.add("hidden");
  refreshAll();
});

$("#auth-password").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#auth-submit").click();
});

function tab(name) {
  $$(".tab-btn, .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-page").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "planets") refreshPlanets();
  if (name === "fleet") refreshFleets();
  if (name === "farmer") refreshTargets();
  if (name === "hunt") refreshHunt();
  if (name === "galaxy") refreshGalaxy();
  if (["build", "research", "hangar", "farmer", "hunt", "expeditions", "fleetsave", "colonies", "transports", "config"].includes(name)) refreshConfig();
  if (name === "build" || name === "research") refreshQueue();
  if (name === "expeditions") refreshExpeditions();
  if (name === "build" || name === "research" || name === "hangar") refreshPlanets();
  if (name === "logs") refreshLogs();
  if (name === "account") refreshAccount();
}

$$(".tab").forEach((b) => b.addEventListener("click", () => tab(b.dataset.tab)));

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    state.status = s;
    renderStatus();
  } catch (e) { console.error(e); }
}

async function refreshSummary() {
  try {
    const sum = await api("/api/summary");
    $("#stat-metal").textContent = fmt(sum.totals.metal);
    $("#stat-crystal").textContent = fmt(sum.totals.crystal);
    $("#stat-deut").textContent = fmt(sum.totals.deuterium);
  } catch (e) { console.error(e); }
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  const pill = $("#status-pill");
  const pillState = s.running ? (s.paused ? "paused" : "running") : "stopped";
  pill.className = `pill ${pillState}`;
  pill.textContent = s.running ? (s.paused ? "⏸ Pausado" : "● En marcha") : "○ Detenido";
  $("#sleep-pill").classList.toggle("hidden", !s.sleeping);
  $("#session-pill").classList.toggle("hidden", !s.session_error);
  $("#btn-pause").disabled = !s.running;
  $("#btn-start").disabled = s.running;
  $("#account-line").textContent = s.has_account
    ? `${s.universe}${s.demo ? " · DEMO" : ""} — ${s.account ? s.account.username : ""}`
    : "Sin cuenta configurada";

  $("#stat-attacks").textContent = fmt(s.stats ? s.stats.farmer_attacks || 0 : 0);
  $("#stat-loot").textContent = fmt(s.farmer_loot || 0);

  const box = s.event_box || {};
  const alerts = $("#alerts");
  const items = [];
  if (box.hostile > 0) items.push(`<div class="alert danger">⚠️ ¡Ataque hostil detectado! (${box.hostile} flotas)</div>`);
  if (s.sleeping) items.push('<div class="alert night">🌙 Modo noche activo: solo se vigilan ataques</div>');
  if (s.powered_off) items.push('<div class="alert night">⏻ Apagado programado activo: el bot no hace nada en esta franja horaria</div>');
  if (s.session_error) items.push(`<div class="alert danger">⚠️ <b>Sesión caducada</b>: renueva la cookie en la pestaña 👤 Cuenta. El bot sigue reintentando solo. (${escapeHtml(s.session_error)})</div>`);
  if (s.last_results && s.last_results.fleetsave && Date.now() / 1000 - s.last_results.fleetsave.ts < 600)
    items.push(`<div class="alert danger">🚨 Fleet-save ejecutado: ${escapeHtml(s.last_results.fleetsave.detail)}</div>`);
  if (!items.length) items.push('<div class="alert ok">✓ Sin amenazas. Todo en orden.</div>');
  alerts.innerHTML = items.join("");

  const uptime = s.started_at ? Math.floor(Date.now() / 1000 - s.started_at) : 0;
  $("#bot-state").innerHTML = `
    <span class="k">Ciclos</span><span>${s.ticks || 0}</span>
    <span class="k">Tiempo activo</span><span>${Math.floor(uptime / 60)}m ${uptime % 60}s</span>
    <span class="k">Modo</span><span>${s.demo ? "Demo (simulado)" : "Real"}</span>
    <span class="k">Acción actual</span><span>${s.current || "—"}</span>`;

  renderModules();
}

function renderModules() {
  const s = state.status;
  const catalog = s.module_catalog || [];
  const results = s.last_results || {};
  const nextRuns = s.next_runs || {};
  const cfg = state.config || {};
  $("#modules-grid").innerHTML = catalog.map((m) => {
    const r = results[m.name];
    const next = nextRuns[m.name];
    const enabled = cfg[m.name] ? cfg[m.name].enabled : false;
    const badge = !enabled
      ? '<span class="badge idle">off</span>'
      : r ? (r.status === "ok" ? '<span class="badge ok">ok</span>' : '<span class="badge err">error</span>') : '<span class="badge idle">esperando</span>';
    return `<div class="module-card">
      <div class="module-head">
        <b>${m.label}</b>
        <label class="switch">
          <input type="checkbox" data-module="${m.name}" ${enabled ? "checked" : ""}>
          <span class="slider"></span>
        </label>
      </div>
      <div class="module-detail">${badge} ${r ? escapeHtml(r.detail) : "sin ejecutar aún"}</div>
      <div class="module-next">Próxima: ${next ? fmtTime(next) : "—"}</div>
    </div>`;
  }).join("");

  $$("#modules-grid .switch input").forEach((input) => {
    input.addEventListener("change", async () => {
      try {
        await api("/api/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: { [input.dataset.module]: { enabled: input.checked } } }),
        });
        toast(`Módulo <b>${input.dataset.module}</b> ${input.checked ? "activado" : "desactivado"}`, "success");
        state.config[input.dataset.module].enabled = input.checked;
      } catch (e) {
        toast("Error: " + e.message, "error");
        input.checked = !input.checked;
      }
    });
  });
}

const SHIP_NAMES = {202:"Carguero pequeño",203:"Carguero grande",204:"Cazador ligero",205:"Cazador pesado",206:"Crucero",207:"Nave de batalla",208:"Colono",209:"Reciclador",210:"Sonda de espionaje",211:"Bombardero",213:"Destructor",214:"Estrella de la muerte",215:"Acorazado",218:"Crawler",219:"Explorador"};
const DEF_NAMES = {401:"Lanzamisiles",402:"Láser pequeño",403:"Láser grande",404:"Cañón Gauss",405:"Cañón de iones",406:"Cañón de plasma",407:"Cúpula pequeña",408:"Cúpula grande",502:"Misil interceptor",503:"Misil interplanetario"};
const TECH_NAMES = Object.assign({}, SHIP_NAMES, DEF_NAMES, {
  1:"Mina de metal",2:"Mina de cristal",3:"Sintetizador de deuterio",4:"Planta solar",12:"Planta de fusión",
  14:"Fábrica de robots",15:"Fábrica de nanites",21:"Hangar",22:"Almacén de metal",23:"Almacén de cristal",24:"Tanque de deuterio",
  31:"Laboratorio de investigación",36:"Astillero orbital",41:"Base lunar",42:"Sensor de falange",43:"Puerta de salto",44:"Silo de misiles",
  106:"Tecnología de espionaje",108:"Computación cuántica",109:"Tecnología de armas",110:"Tecnología de escudos",111:"Tecnología de blindaje",
  113:"Tecnología de energía",115:"Propulsor de combustión",117:"Propulsor de impulso",118:"Propulsor de hiperespacio",
  120:"Tecnología láser",121:"Tecnología de iones",122:"Tecnología de plasma",123:"Red de investigación intergaláctica",124:"Astrofísica"
});

const CONFIG_META = {
  buildings: { icon: "🏗️", label: "Edificios y minas", desc: "Sube las minas y edificios de tus planetas sin que toques nada.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    smart: { label: "Modo inteligente", type: "bool", desc: "Elige la mejora más rentable (ROI con tu ratio comercial) y respeta el equilibrio de minas, en vez de seguir el orden fijo." },
    facilities: { label: "Construir instalaciones automáticamente", type: "bool", desc: "APAGADO por defecto: el bot solo sube minas, energía y almacenes. Actívalo si quieres que también suba laboratorio, astillero, etc. por su cuenta (mejor dejarlo manual desde la pestaña Construir)." },
    order: { label: "Orden fijo de construcción", type: "list", desc: "Solo se usa si apagas el modo inteligente. IDs separados por comas: " + Object.entries({1:1,2:1,3:1,4:1,12:1,14:1,15:1,21:1,22:1,23:1,24:1,31:1,36:1}).map(([id]) => id + "=" + TECH_NAMES[id]).join(", ") },
    roi_ratio: { label: "Ratio comercial (metal, cristal, deuterio)", type: "list", desc: "Cuánto vale cada recurso al cambiarlo. Estándar: 2.5, 1.5, 1. Se usa para calcular qué mina se paga antes." },
    mine_balance: { label: "Equilibrio de minas", type: "dict", keyNames: {metal:"Metal (+niveles sobre cristal)", crystal:"Cristal (base)", deuterium:"Deuterio (+niveles sobre cristal)"}, desc: "Diferencia de niveles entre minas. Con 0 / 0 / -3: metal y cristal al mismo nivel, deuterio 3 niveles por debajo." },
    max_levels: { label: "Niveles máximos", type: "dict", keyNames: {metal_mine:"Mina de metal", crystal_mine:"Mina de cristal", deuterium_mine:"Sintetizador de deuterio"}, desc: "El bot no sube ninguna mina más allá de estos niveles. Deja vacío para no limitar." },
    reserves: { label: "Reservas que nunca gasta", type: "dict", keyNames: {metal:"Metal", crystal:"Cristal", deuterium:"Deuterio"}, desc: "Antes de construir, el bot deja siempre esta cantidad en el planeta." },
  }},
  research: { icon: "🔬", label: "Investigaciones", desc: "Pone investigaciones en cola una tras otra siguiendo el orden que definas.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    order: { label: "Orden de investigación", type: "list", desc: "IDs separados por comas, se investigan en este orden: " + [106,108,109,110,111,113,115,117,120,121,124,123].map(id => id + "=" + TECH_NAMES[id]).join(", ") },
    max_levels: { label: "Niveles máximos", type: "dict", keyNames: TECH_NAMES, desc: "Escribe id: nivel para no pasar de ahí. Ejemplo: 120: 12" },
  }},
  shipyard: { icon: "🚢", label: "Hangar y defensas", desc: "Construye naves y defensas hasta alcanzar las cantidades que pongas aquí (cuotas).", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    ship_quotas: { label: "Naves — cuántas tener en total", type: "dict", keyNames: SHIP_NAMES, desc: "Una línea por nave: id: cantidad. Ejemplo: 202: 200" },
    defense_quotas: { label: "Defensas — cuántas tener", type: "dict", keyNames: DEF_NAMES, desc: "Una línea por defensa: id: cantidad. Ejemplo: 401: 300" },
    batch_size: { label: "Tamaño del lote", type: "num", desc: "Cuántas unidades pide de golpe en cada pasada del hangar." },
  }},
  farmer: { icon: "⚔️", label: "Farmer (atacar inactivos)", desc: "Espía jugadores inactivos cercanos y ataca a los que tienen recursos que robar.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    origin_id: { label: "ID del planeta atacante", type: "num", desc: "Déjalo en 0 para usar tu primer planeta. El ID lo ves en la pestaña Imperio." },
    galaxies: { label: "Galaxias donde buscar", type: "list", desc: "Ejemplo: 4, 5" },
    systems: { label: "Rango de sistemas", type: "list", desc: "Dos números: desde, hasta. Ejemplo: 19, 40" },
    max_rank: { label: "Puesto máximo del rival", type: "num", desc: "Solo ataca a jugadores con puesto peor (número más alto) que este. 400 = débiles." },
    min_loot: { label: "Botín mínimo para atacar", type: "num", desc: "Si el espionaje encuentra menos recursos que esto, no ataca." },
    probes: { label: "Sondas por espionaje", type: "num" },
    escorts: { label: "Naves de escolta", type: "dict", keyNames: SHIP_NAMES, desc: "Naves que acompañan a los cargueros en cada ataque. Ejemplo: 204: 30" },
    attack_cooldown: { label: "No repetir objetivo antes de… (segundos)", type: "num" },
  }},
  expedition: { icon: "🚀", label: "Expediciones", desc: "Envía flotas a la posición 16 de los sistemas que elijas a buscar recursos, naves o materia oscura.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    origin_id: { label: "ID del planeta de salida", type: "num", desc: "0 = tu primer planeta." },
    fleet: { label: "Flota de expedición", type: "dict", keyNames: SHIP_NAMES, desc: "Naves que envía en cada expedición. Ejemplo: 204: 50 grandes cantidades de cazadores + 202: 20 cargueros + 210: 1 sonda" },
    holding_time: { label: "Horas que se queda allí", type: "num" },
    coords: { label: "Coordenadas fijas (opcional)", type: "json", desc: "Formato [[galaxia, sistema, 16]]. Si lo dejas vacío usa el rango de abajo." },
    galaxy: { label: "Galaxia de expediciones", type: "num", desc: "0 = la misma galaxia que el planeta de salida." },
    system_start: { label: "Sistema inicial del rango", type: "num" },
    system_end: { label: "Sistema final del rango", type: "num" },
  }},
  fleetsave: { icon: "🛡️", label: "Fleet-save automático", desc: "Si detecta ataques entrantes, manda tu flota y recursos a escondite (expedición) para que no los pillen.", fields: {
    interval: { label: "Vigila cada… (segundos)", type: "num" },
    mode: { label: "Modo de escondite", type: "text", desc: "expedition = manda la flota a expedición (recomendado)." },
    origin_id: { label: "ID del planeta a vigilar", type: "num", desc: "0 = tu primer planeta." },
    holding_time: { label: "Horas escondido", type: "num" },
    cooldown: { label: "Espera entre fleet-saves (segundos)", type: "num" },
  }},
  colonize: { icon: "🪐", label: "Auto-colonización", desc: "Construye colonos y coloniza planetas nuevos en la zona que elijas. Al conseguirlos, empieza a subirles las minas.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    origin_id: { label: "ID del planeta de salida", type: "num", desc: "0 = tu primer planeta." },
    auto: { label: "Elegir coordenadas automáticamente", type: "bool", desc: "Busca huecos buenos dentro del rango de abajo. Si lo apagas, usa la lista de coordenadas." },
    galaxy: { label: "Galaxia donde colonizar", type: "num" },
    system_start: { label: "Sistema inicial", type: "num" },
    system_end: { label: "Sistema final", type: "num" },
    coords: { label: "Coordenadas concretas (opcional)", type: "json", desc: "Formato [[galaxia, sistema, planeta], …]. Se usan antes que el rango." },
  }},
  transport: { icon: "🚚", label: "Transportes al principal", desc: "Manda los recursos que sobran de cada planeta y luna a tu planeta principal.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    main_id: { label: "ID del planeta principal (destino)", type: "num", desc: "El ID lo ves en la pestaña Imperio." },
    threshold: { label: "Enviar cuando un planeta supere…", type: "num", desc: "Suma de recursos a partir de la cual se organiza un transporte." },
    keep: { label: "Dejar en cada planeta", type: "num", desc: "Cantidad que el bot nunca se lleva del origen." },
    include_moons: { label: "Incluir lunas", type: "bool" },
  }},
  sleep: { icon: "🌙", label: "Modo noche", desc: "Deja el juego tranquilo en esas horas (solo se mantiene el fleet-save por si hay ataques).", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    start_hour: { label: "Hora de empezar a dormir (0-23)", type: "num" },
    end_hour: { label: "Hora de despertar (0-23)", type: "num" },
  }},
  mapper: { icon: "🗺️", label: "Mapeo galáctico", desc: "Escanea la galaxia poco a poco y apunta en el mapa los inactivos y campos de escombros que encuentra.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    galaxies: { label: "Galaxias a escanear", type: "list", desc: "Ejemplo: 1, 2, 3, 4" },
    system_start: { label: "Sistema inicial", type: "num" },
    system_end: { label: "Sistema final", type: "num" },
    systems_per_run: { label: "Sistemas por pasada", type: "num", desc: "Cuántos sistemas escanea cada vez (bajo = más discreto)." },
  }},
  hunt: { icon: "🎯", label: "Caza", desc: "Revisa las posiciones del mapa y registra cuándo está activo cada jugador: así descubres los horarios de tus objetivos.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    rescan_per_run: { label: "Posiciones a revisar por pasada", type: "num" },
  }},
  harvest: { icon: "♻️", label: "Recolección de escombros", desc: "Envía recicladores a los campos de escombros que el mapeo haya encontrado.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    origin_id: { label: "ID del planeta de salida", type: "num", desc: "0 = tu primer planeta." },
    recyclers_max: { label: "Recicladores por envío", type: "num" },
    cooldown: { label: "No repetir escombro antes de… (segundos)", type: "num" },
    max_targets: { label: "Máximo de escombros por pasada", type: "num" },
  }},
  watch: { icon: "👁️", label: "Vigilancia", desc: "Te avisa (panel y Telegram) si un objetivo cazado se conecta o si un inactivo vuelve a estar activo.", fields: {
    interval: { label: "Comprueba cada… (segundos)", type: "num" },
    alert_hunted: { label: "Avisar cuando un objetivo se conecta", type: "bool" },
    hunted_online_minutes: { label: "Considerar conectado si estuvo activo hace menos de… (minutos)", type: "num" },
    alert_inactive_recovered: { label: "Avisar cuando un inactivo reaparece", type: "bool" },
    repeat_cooldown: { label: "No repetir el mismo aviso antes de… (segundos)", type: "num" },
  }},
  schedule: { icon: "⏰", label: "Apagado programado", desc: "Apaga TODOS los módulos en esa franja horaria (ni expediciones ni fleet-save).", fields: {
    start_hour: { label: "Hora de apagar (0-23)", type: "num" },
    end_hour: { label: "Hora de encender (0-23)", type: "num" },
  }},
};

function cfgFieldValue(type, value, keyNames) {
  if (type === "bool") return !!value;
  if (type === "num") return Number(value) || 0;
  if (type === "list") return Array.isArray(value) ? value.join(", ") : String(value || "");
  if (type === "dict") {
    const obj = value && typeof value === "object" ? value : {};
    return Object.entries(obj).map(([k, v]) => `${k}: ${v}`).join("\n");
  }
  if (type === "json") return Array.isArray(value) && value.length ? JSON.stringify(value) : "";
  return String(value ?? "");
}

function cfgParseValue(type, raw) {
  const text = (raw || "").trim();
  if (type === "bool") return true;
  if (type === "num") { const n = Number(text); return isNaN(n) ? 0 : n; }
  if (type === "list") return text.split(",").map(x => x.trim()).filter(x => x !== "").map(x => { const n = Number(x); return isNaN(n) ? x : n; });
  if (type === "dict") {
    const obj = {};
    for (const line of text.split("\n")) {
      const i = line.indexOf(":");
      if (i <= 0) continue;
      const k = line.slice(0, i).trim();
      const v = line.slice(i + 1).trim();
      if (!k) continue;
      const n = Number(v.replace(/[_.]/g, ""));
      obj[k] = isNaN(n) || v === "" ? v : n;
    }
    return obj;
  }
  if (type === "json") {
    try { return JSON.parse(text); } catch { return []; }
  }
  return text;
}

function cfgModuleCard(name, meta, mod) {
  const fields = Object.entries(meta.fields).map(([key, f]) => {
    const value = cfgFieldValue(f.type, mod[key], f.keyNames);
    const desc = f.desc ? `<div class="cfg-desc">${f.desc}</div>` : "";
    let input;
    if (f.type === "bool") {
      input = `<label class="switch"><input type="checkbox" data-module="${name}" data-key="${key}" data-type="bool" ${value ? "checked" : ""}><span class="slider"></span></label>`;
      return `<div class="cfg-field"><div class="cfg-label"><b>${f.label}</b>${desc}</div>${input}</div>`;
    }
    if (f.type === "dict" || f.type === "json") {
      input = `<textarea rows="3" data-module="${name}" data-key="${key}" data-type="${f.type}">${escapeHtml(value)}</textarea>`;
    } else {
      input = `<input data-module="${name}" data-key="${key}" data-type="${f.type}" value="${escapeHtml(String(value))}">`;
    }
    return `<div class="cfg-field"><div class="cfg-label"><b>${f.label}</b>${desc}</div>${input}</div>`;
  }).join("");
  return `<div class="card config-mod">
    <div class="module-head">
      <div><b>${meta.icon} ${meta.label}</b><div class="muted small">${meta.desc}</div></div>
      <label class="switch"><input type="checkbox" data-module="${name}" data-key="enabled" data-type="bool" ${mod.enabled ? "checked" : ""}><span class="slider"></span></label>
    </div>
    <div class="config-fields">${fields}</div>
  </div>`;
}

function renderConfigInto(container, moduleNames) {
  const cfg = state.config || {};
  container.innerHTML = moduleNames.filter((n) => CONFIG_META[n]).map((n) => cfgModuleCard(n, CONFIG_META[n], cfg[n] || {})).join("");
}

function renderAllCfgMounts() {
  $$(".cfg-mount").forEach((el) => renderConfigInto(el, el.dataset.modules.split(",")));
}

function renderConfig() {
  renderConfigInto($("#config-container"), ["buildings", "sleep", "schedule"]);
}

async function refreshConfig() {
  try {
    state.config = await api("/api/config");
    renderConfig();
    renderAllCfgMounts();
  } catch (e) { console.error(e); }
}

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest(".btn-save-cfg");
  if (!btn) return;
  const section = btn.closest(".tab-page");
  if (!section) return;
  const config = {};
  section.querySelectorAll("[data-module]").forEach((el) => {
    const mod = config[el.dataset.module] = config[el.dataset.module] || {};
    mod[el.dataset.key] = cfgParseValue(el.dataset.type, el.type === "checkbox" ? (el.checked ? "1" : "") : el.value);
  });
  try {
    await api("/api/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config }) });
    toast("Configuración guardada ✓", "success");
  } catch (e) { toast("Error: " + e.message, "error"); }
});

async function refreshPlanets() {
  try {
    const data = await api("/api/planets");
    state.planets = data;
    const container = $("#planets-container");
    if (!data.planets.length) {
      container.innerHTML = '<div class="card">Inicia el bot para ver tu imperio.</div>';
      return;
    }
    container.innerHTML = data.planets.map((p) => {
      const res = data.resources[p.id] || {};
      const store = res.storage || [1, 1, 1];
      const pct = (v, s) => Math.min(100, (v / Math.max(s, 1)) * 100);
      const b = data.buildings[p.id] || {};
      const queueHtml = (b._queue || []).length
        ? `<div class="queue-box">${(b._queue || []).map((q) => `<div class="res-row"><span>⏳ ${q.tech || "?"}</span><span class="queue-timer">${q.time_left != null ? q.time_left + "s" : ""}</span></div>`).join("")}</div>`
        : "";
      const keyBuildings = [1, 2, 3, 4, 14, 21, 31].map((id) => b[id] ? `${b[id].name}: <b>${b[id].level}</b>` : "").filter(Boolean).join(" · ");
      const shipList = Object.values(data.ships[p.id] || {}).filter((s) => typeof s === "object" && s.amount > 0)
        .map((s) => `<span class="res-row"><span>${s.name}</span><span class="val">${fmt(s.amount)}</span></span>`).join("");
      const bar = (v, s) => `<div class="bar ${pct(v, s) > 90 ? "danger" : ""}"><div style="width:${pct(v, s)}%"></div></div>`;
      return `<div class="planet-card">
        <h4>${p.name} ${p.type === "moon" ? "🌙" : "🪐"}</h4>
        <div class="coords">[${p.coords.join(":")}]</div>
        <div class="res-row"><span>Metal</span><span class="val metal">${fmt(res.metal)}</span></div>
        ${bar(res.metal, store[0])}
        <div class="res-row"><span>Cristal</span><span class="val crystal">${fmt(res.crystal)}</span></div>
        ${bar(res.crystal, store[1])}
        <div class="res-row"><span>Deuterio</span><span class="val deut">${fmt(res.deuterium)}</span></div>
        ${bar(res.deuterium, store[2])}
        <div class="res-row"><span>Energía</span><span class="val energy">${fmt(res.energy)}</span></div>
        ${queueHtml}
        <p class="muted" style="font-size:12px">${keyBuildings}</p>
        ${shipList}
      </div>`;
    }).join("");
  } catch (e) {
    $("#planets-container").innerHTML = `<div class="card">No disponible: ${escapeHtml(e.message)}</div>`;
  }
}

async function refreshFleets() {
  try {
    const data = await api("/api/fleets");
    if (!state.planets) {
      try { state.planets = await api("/api/planets"); } catch {}
    }
    populateFleetForms(state.planets || { planets: [] });
    $("#fleet-slots").innerHTML = `
      <span class="slot">🚀 Flota <b>${data.slots.fleet.used}</b> / ${data.slots.fleet.total}</span>
      <span class="slot">🌌 Expediciones <b>${data.slots.expedition.used}</b> / ${data.slots.expedition.total}</span>`;
    const missions = { 1: "⚔️ Ataque", 3: "📦 Transporte", 4: "📍 Despliegue", 6: "🕵️ Espionaje", 7: "🪐 Colonizar", 8: "♻️ Reciclaje", 15: "🌌 Expedición" };
    $("#fleets-table tbody").innerHTML = (data.fleets || []).map((f) => `<tr>
      <td><span class="badge mission">${missions[f.mission] || f.mission}</span></td>
      <td>[${(f.origin || []).join(":")}]</td>
      <td>[${(f.destination || []).join(":")}]</td>
      <td>${fmtTime(f.arrival)}</td>
      <td>${f.return_flight ? "sí" : "no"}</td>
    </tr>`).join("") || '<tr><td colspan="5" class="muted">Sin flotas en movimiento</td></tr>';
  } catch (e) {
    $("#fleet-slots").innerHTML = `<span class="slot muted">${escapeHtml(e.message)}</span>`;
  }
}

async function refreshTargets() {
  try {
    const data = await api("/api/targets");
    $("#targets-table tbody").innerHTML = (data.targets || []).map((t) => `<tr>
      <td>[${t.galaxy}:${t.system}:${t.position}]</td>
      <td>${escapeHtml(t.player || "—")}</td>
      <td>${t.inactive ? '<span class="badge inactive">inactivo</span>' : "—"}</td>
      <td>${fmt(t.metal + t.crystal + t.deuterium)}</td>
      <td>${t.last_spied ? fmtTime(t.last_spied) : "—"}</td>
      <td>${t.attacks || 0}</td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">Sin objetivos. Activa el módulo Farmer o escanea un sistema manualmente.</td></tr>';
  } catch (e) { console.error(e); }
}

async function refreshHunt() {
  try {
    const [mapData, huntData] = await Promise.all([
      api(`/api/map?inactive=${$("#map-inactive").checked}&search=${encodeURIComponent($("#map-search").value)}&limit=500`),
      api("/api/hunt"),
    ]);
    const st = mapData.stats;
    $("#map-stats").innerHTML = `
      <div class="stat-card"><span class="stat-value">${fmt(st.positions)}</span><span class="stat-label">Posiciones</span></div>
      <div class="stat-card"><span class="stat-value">${fmt(st.inactive)}</span><span class="stat-label">Inactivos</span></div>
      <div class="stat-card"><span class="stat-value">${fmt(st.systems)}</span><span class="stat-label">Sistemas mapeados</span></div>
      <div class="stat-card"><span class="stat-value">${fmt(st.players)}</span><span class="stat-label">Jugadores</span></div>
      <div class="stat-card"><span class="stat-value">${fmt(st.hunted)}</span><span class="stat-label">Cazados</span></div>`;
    $("#hunt-table tbody").innerHTML = (huntData.players || []).map((p) => `<tr>
      <td><b>${escapeHtml(p.player)}</b></td>
      <td>${p.last_seen ? fmtDateTime(p.last_seen) : "—"}</td>
      <td>${p.active_count || 0} / ${p.checks || 0}</td>
      <td>${p.checks || 0}</td>
      <td><button class="btn danger" data-unhunt="${escapeHtml(p.player)}">✕</button></td>
    </tr>`).join("") || '<tr><td colspan="5" class="muted">Nadie apuntado todavía.</td></tr>';
    $$("#hunt-table [data-unhunt]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api(`/api/hunt/${encodeURIComponent(btn.dataset.unhunt)}`, { method: "DELETE" });
          toast("Jugador retirado de la caza", "info");
          refreshHunt();
        } catch (e) { toast("Error: " + e.message, "error"); }
      });
    });
    const actLabel = (a) => (a === "active" ? "🟢 activo ahora" : a && a !== "None" ? `🟡 hace ${a} min` : "⚪ sin señal");
    $("#activity-table tbody").innerHTML = (huntData.activity || []).map((a) => `<tr>
      <td>${fmtDateTime(a.ts)}</td>
      <td><b>${escapeHtml(a.player)}</b></td>
      <td>[${a.galaxy}:${a.system}:${a.position}]</td>
      <td>${actLabel(a.activity)}</td>
    </tr>`).join("") || '<tr><td colspan="4" class="muted">Sin registros de actividad todavía.</td></tr>';
    $("#map-table tbody").innerHTML = (mapData.rows || []).map((r) => `<tr>
      <td>[${r.galaxy}:${r.system}:${r.position}]</td>
      <td>${escapeHtml(r.player || "—")}</td>
      <td>${r.rank ? "#" + r.rank : "—"}</td>
      <td>${r.inactive ? '<span class="badge inactive">inactivo</span>' : "—"}</td>
      <td>${actLabel(r.activity)}</td>
      <td>${r.seen_at ? fmtDateTime(r.seen_at) : "—"}</td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">Mapa vacío. Activa el módulo Mapeo Galáctico o escanea sistemas.</td></tr>';
  } catch (e) { console.error(e); }
}

$("#btn-hunt-add").addEventListener("click", async () => {
  const nick = $("#hunt-nick").value.trim();
  if (!nick) return;
  try {
    await api("/api/hunt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player: nick }),
    });
    toast(`Cazando a <b>${escapeHtml(nick)}</b> 🎯`, "success");
    $("#hunt-nick").value = "";
    refreshHunt();
  } catch (e) { toast("Error: " + e.message, "error"); }
});

$("#btn-map-refresh").addEventListener("click", refreshHunt);
$("#map-inactive").addEventListener("change", refreshHunt);
$("#map-search").addEventListener("keydown", (e) => { if (e.key === "Enter") refreshHunt(); });

async function refreshGalaxy() {
  const galaxy = parseInt($("#gv-galaxy").value) || 1;
  const system = parseInt($("#gv-system").value) || 1;
  await loadGalaxy(galaxy, system);
}

async function loadGalaxy(galaxy, system) {
  try {
    const data = await api(`/api/galaxy?galaxy=${galaxy}&system=${system}`);
    const actLabel = (a) => (a === "active" ? "🟢 activo ahora" : a && a !== "None" ? `🟡 hace ${a} min` : "⚪ sin señal");
    $("#gv-meta").textContent = `Sistema ${data.galaxy}:${data.system} — ${data.rows.length} posiciones ocupadas`;
    $("#galaxy-table tbody").innerHTML = data.rows.map((r) => `<tr>
      <td>${r.position}</td>
      <td><b>${escapeHtml(r.player || "")}</b></td>
      <td>${r.rank ? "#" + r.rank : "—"}</td>
      <td>${actLabel(r.activity)}</td>
      <td>${r.moon ? "🌙" : "—"}</td>
      <td>${r.debris ? "⚙️" : "—"}</td>
      <td>${r.inactive ? '<span class="badge inactive">inactivo</span>' : ""}</td>
    </tr>`).join("") || '<tr><td colspan="7" class="muted">Sistema vacío.</td></tr>';
  } catch (e) {
    $("#gv-meta").textContent = "Error: " + e.message;
  }
}

$("#btn-gv-scan").addEventListener("click", refreshGalaxy);
$$("#tab-galaxy input[type=number]").forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") refreshGalaxy(); }));

function fillSelect(select, items, labelFn) {
  select.innerHTML = items.map((it) => `<option value="${it.value}">${escapeHtml(labelFn(it))}</option>`).join("");
}

function populateFleetForms(data) {
  const celestials = (data.planets || []).map((p) => ({
    value: p.id,
    label: `${p.type === "moon" ? "🌙" : "🪐"} ${p.name} [${p.coords.join(":")}]`,
  }));
  if (celestials.length) {
    fillSelect($("#mf-origin"), celestials, (c) => c.label);
    fillSelect($("#mb-planet"), celestials, (c) => c.label);
    const bq = $("#bq-planet");
    if (bq) {
      const current = bq.value;
      fillSelect(bq, celestials, (c) => c.label);
      bq.insertAdjacentHTML("afterbegin", '<option value="0">Automático (primer planeta libre)</option>');
      bq.value = current || "0";
    }
  }
  const cat = state.status || {};
  const kind = $("#mb-kind").value;
  const items = (kind === "ships" ? cat.ships_catalog : cat.defenses_catalog) || [];
  fillSelect($("#mb-tech"), items, (it) => `#${it.id} ${it.name}`);
}

$("#mb-kind").addEventListener("change", () => populateFleetForms(state.planets || { planets: [] }));

$("#btn-mf-send").addEventListener("click", async () => {
  let ships = {};
  try { ships = JSON.parse($("#mf-ships").value || "{}"); } catch { ships = null; }
  if (!ships || !Object.keys(ships).length) {
    toast("Introduce las naves como JSON, p. ej. {\"204\": 50}", "error");
    return;
  }
  try {
    await api("/api/action/fleet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin_id: parseInt($("#mf-origin").value),
        mission: parseInt($("#mf-mission").value),
        galaxy: parseInt($("#mf-galaxy").value),
        system: parseInt($("#mf-system").value),
        position: parseInt($("#mf-position").value),
        dest_type: parseInt($("#mf-dest").value),
        ships,
        metal: parseInt($("#mf-metal").value) || 0,
        crystal: parseInt($("#mf-crystal").value) || 0,
        deuterium: parseInt($("#mf-deuterium").value) || 0,
        speed: parseInt($("#mf-speed").value) || 10,
        holding_time: parseInt($("#mf-holding").value) || 0,
      }),
    });
    toast("🚀 Flota enviada", "success");
    refreshFleets();
  } catch (e) { toast("Error: " + e.message, "error"); }
});

$("#btn-mb-build").addEventListener("click", async () => {
  const tech = $("#mb-tech").value;
  if (!tech) return;
  try {
    await api("/api/action/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        planet_id: parseInt($("#mb-planet").value),
        tech_id: parseInt(tech),
        amount: parseInt($("#mb-amount").value) || 1,
      }),
    });
    toast("🏭 Pedido enviado a la cola", "success");
  } catch (e) { toast("Error: " + e.message, "error"); }
});

const BUILD_GRID = [1, 2, 3, 4, 12, 14, 15, 21, 22, 23, 24, 31, 36, 44, 41, 42, 43];
const RESEARCH_GRID = [106, 108, 109, 110, 111, 113, 115, 117, 118, 120, 121, 122, 123, 124];

function renderBuildGrids() {
  const mk = (ids) => ids.map((id) => `<button class="btn build-btn" data-tech="${id}">${TECH_NAMES[id] || "Tech " + id}</button>`).join("");
  const bg = $("#build-grid");
  const rg = $("#research-grid");
  if (bg) bg.innerHTML = mk(BUILD_GRID);
  if (rg) rg.innerHTML = mk(RESEARCH_GRID);
}

function queueItemName(q) {
  return TECH_NAMES[q.tech_id] || "Tech " + q.tech_id;
}

function renderQueue(items) {
  const html = items.length
    ? items.map((q, i) => `<div class="queue-item"><span class="q-pos">${i + 1}</span><span class="q-name"><b>${escapeHtml(queueItemName(q))}</b>${q.amount > 1 ? " × " + q.amount : ""}</span><span class="muted small">${q.planet_id ? "planeta #" + q.planet_id : "auto"}</span><button class="btn danger btn-q-del" data-index="${i}">✕</button></div>`).join("")
    : '<div class="muted">La cola está vacía. Haz clic en un edificio o investigación para añadir un pedido.</div>';
  $$(".queue-list").forEach((el) => { el.innerHTML = html; });
  $$(".btn-q-del").forEach((btn) => btn.addEventListener("click", async () => {
    try {
      await api("/api/queue/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index: +btn.dataset.index }) });
      refreshQueue();
    } catch (e) { toast("Error: " + e.message, "error"); }
  }));
}

async function refreshQueue() {
  try {
    renderQueue((await api("/api/queue")).queue || []);
  } catch (e) { console.error(e); }
}

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest(".build-btn");
  if (!btn) return;
  const techId = +btn.dataset.tech;
  const planetSel = $("#bq-planet");
  const planetId = RESEARCH_GRID.includes(techId) ? 0 : +(planetSel && planetSel.value ? planetSel.value : 0);
  try {
    await api("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tech_id: techId, planet_id: planetId, amount: 1 }),
    });
    toast(`<b>${escapeHtml(queueItemName({ tech_id: techId }))}</b> añadido a la cola ✓`, "success");
    refreshQueue();
  } catch (e) { toast("Error: " + e.message, "error"); }
});

const EXP_OUTCOMES = {resources: "💰 Recursos", darkmatter: "✨ Materia oscura", ships: "🚠 Naves encontradas", item: "🎁 Objeto", battle: "⚔️ Combate", nothing: "🌑 Nada"};

async function refreshExpeditions() {
  try {
    const data = await api("/api/expeditions");
    const t = data.totals7 || {};
    const card = (label, value) => `<div class="stat-card"><span class="stat-value">${value}</span><span class="stat-label">${label}</span></div>`;
    $("#exp-totals").innerHTML =
      card("⚖️ Metal (7 días)", fmt(t.metal || 0)) +
      card("◆ Cristal (7 días)", fmt(t.crystal || 0)) +
      card("🐎 Deuterio (7 días)", fmt(t.deuterium || 0)) +
      card("✨ Materia oscura", fmt(t.darkmatter || 0)) +
      card("🚠 Naves encontradas", fmt(t.ships || 0)) +
      card("🎁 Objetos", fmt(t.items || 0));
    const kv = (k, v) => `<span class="k">${k}</span><span>${v}</span>`;
    const td = data.today || {};
    $("#exp-today").innerHTML =
      kv("Expediciones enviadas", fmt(td.sent || 0)) +
      kv("Exitosas", fmt(td.success || 0)) +
      kv("Metal", fmt(td.metal || 0)) +
      kv("Cristal", fmt(td.crystal || 0)) +
      kv("Deuterio", fmt(td.deuterium || 0)) +
      kv("Materia oscura", fmt(td.darkmatter || 0));
    const av = data.avg || {};
    $("#exp-avg").innerHTML =
      kv("Metal", fmt(av.metal || 0)) +
      kv("Cristal", fmt(av.crystal || 0)) +
      kv("Deuterio", fmt(av.deuterium || 0)) +
      kv("Materia oscura", fmt(av.darkmatter || 0)) +
      kv("Tasa de éxito (7 días)", `${data.sent7 ? Math.round(100 * (data.success7 || 0) / data.sent7) : 0}% de ${fmt(data.sent7 || 0)}`);
    $("#exp-systems tbody").innerHTML = (data.systems || []).map((r) => `<tr>
      <td><b>${escapeHtml(r.system)}</b></td>
      <td>${fmt(r.sent)}</td>
      <td>${r.success_rate}%</td>
      <td>${fmt(r.avg_value)}</td>
    </tr>`).join("") || '<tr><td colspan="4" class="muted">Sin expediciones todavía. Activa el módulo Expediciones.</td></tr>';
    const gain = (r) => {
      const parts = [];
      if (r.metal) parts.push(`M ${fmt(r.metal)}`);
      if (r.crystal) parts.push(`C ${fmt(r.crystal)}`);
      if (r.deuterium) parts.push(`D ${fmt(r.deuterium)}`);
      if (r.darkmatter) parts.push(`DM ${fmt(r.darkmatter)}`);
      if (r.ships) parts.push(escapeHtml(r.ships));
      if (r.item) parts.push("🎁 " + escapeHtml(r.item));
      return parts.join(" · ") || '<span class="muted">—</span>';
    };
    $("#exp-recent tbody").innerHTML = (data.recent || []).map((r) => `<tr>
      <td>${fmtDateTime(r.ts)}</td>
      <td>${escapeHtml(r.coords)}</td>
      <td>${EXP_OUTCOMES[r.outcome] || escapeHtml(r.outcome)}</td>
      <td>${gain(r)}</td>
    </tr>`).join("") || '<tr><td colspan="4" class="muted">Sin resultados todavía.</td></tr>';
  } catch (e) { console.error(e); }
}


$("#btn-scan").addEventListener("click", async () => {
  const galaxy = parseInt($("#scan-galaxy").value);
  const system = parseInt($("#scan-system").value);
  try {
    const r = await api("/api/action/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ galaxy, system }),
    });
    toast(`Escaneo ${galaxy}:${system}: ${r.found} inactivos encontrados`, "success");
    refreshTargets();
  } catch (e) { toast("Error: " + e.message, "error"); }
});

async function refreshAccount() {
  const acc = await api("/api/account");
  const form = $("#account-form");
  form.language.value = acc.language || "es";
  await loadUniverseOptions(form.language.value, acc.universe);
  form.username.value = acc.username;
  form.session_token.value = acc.session_token || "";
  form.game_cookies.value = acc.game_cookies || "";
  form.demo.checked = !!acc.demo;
  const notify = await api("/api/notify");
  const nf = $("#notify-form");
  nf.token.value = notify.token || "";
  nf.chat_id.value = notify.chat_id || "";
  nf.enabled.checked = !!notify.enabled;
}

async function loadUniverseOptions(language, selected) {
  const sel = $("#account-form").universe;
  sel.innerHTML = `<option value="">Cargando universos…</option>`;
  $("#universe-count").textContent = "";
  try {
    const data = await api(`/api/universes?language=${encodeURIComponent(language)}`);
    const list = data.universes.filter((u) => u.language === language);
    const shown = list.length ? list : data.universes;
    sel.innerHTML = shown
      .map((u) => `<option value="${escapeHtml(u.name)}">${escapeHtml(u.name)} (s${u.number})</option>`)
      .join("");
    if (selected) {
      if (![...sel.options].some((o) => o.value === selected)) {
        sel.insertAdjacentHTML("afterbegin", `<option value="${escapeHtml(selected)}">${escapeHtml(selected)} (guardado)</option>`);
      }
      sel.value = selected;
    }
    $("#universe-count").textContent = `${shown.length} universos en '${language}'`;
  } catch (e) {
    sel.innerHTML = `<option value="">(no se pudo cargar la lista)</option>`;
  }
}

const reloadUniverses = () => {
  const form = $("#account-form");
  loadUniverseOptions(form.language.value, form.universe.value);
};

$("#btn-universes").addEventListener("click", reloadUniverses);

$("#account-form").language.addEventListener("change", (ev) => {
  loadUniverseOptions(ev.target.value, "");
});

$("#account-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = $("#account-msg");
  if (!form.password.value && !form.session_token.value && !form.game_cookies.value.trim() && !form.demo.checked) {
    msg.textContent = "❌ Necesitas la contraseña, una cookie de sesión o una sesión de juego directa (o activa el modo demo)";
    return;
  }
  msg.textContent = "Guardando…";
  try {
    await api("/api/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        universe: form.universe.value,
        language: form.language.value,
        username: form.username.value,
        password: form.password.value,
        demo: form.demo.checked,
        session_token: form.session_token.value.trim(),
        game_cookies: form.game_cookies.value.trim(),
      }),
    });
    msg.textContent = "✅ Cuenta guardada y sesión validada. Pulsa Iniciar arriba.";
    toast("Cuenta guardada. Ya puedes iniciar el bot.", "success");
    refreshStatus();
  } catch (e) {
    msg.textContent = "❌ " + e.message;
    toast("Error: " + e.message, "error");
  }
});

$("#notify-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  try {
    await api("/api/notify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: form.token.value,
        chat_id: form.chat_id.value,
        enabled: form.enabled.checked,
      }),
    });
    toast("Telegram configurado. Mensaje de prueba enviado.", "success");
  } catch (e) { toast("Error: " + e.message, "error"); }
});

$("#btn-diagnose").addEventListener("click", async () => {
  const out = $("#diagnose-out");
  out.style.display = "block";
  out.textContent = "⏳ Ejecutando diagnóstico… (tarda unos segundos)";
  try {
    const res = await api("/api/diagnose", { method: "POST" });
    out.textContent = JSON.stringify(res.report, null, 2);
  } catch (e) {
    out.textContent = "❌ " + e.message;
  }
});

$("#btn-start").addEventListener("click", async () => {
  const msg = $("#start-msg");
  msg.classList.remove("hidden");
  msg.textContent = "⏳ Iniciando… conectando con el lobby de OGame";
  try {
    await api("/api/bot/start", { method: "POST" });
    msg.textContent = "✅ Bot iniciado. En unos segundos verás datos en el Panel.";
    toast("Bot iniciado 🚀", "success");
  } catch (e) {
    msg.textContent = "❌ " + e.message;
    toast("Error al iniciar: " + e.message, "error");
  }
  refreshStatus();
});

$("#btn-stop").addEventListener("click", async () => {
  if (!confirm("¿Detener el bot?")) return;
  await api("/api/bot/stop", { method: "POST" });
  toast("Bot detenido", "info");
  refreshStatus();
});

$("#btn-pause").addEventListener("click", async () => {
  const paused = !(state.status && state.status.paused);
  try {
    await api("/api/bot/pause", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paused }) });
    toast(paused ? "Bot pausado ⏸" : "Bot reanudado ▶", "info");
  } catch (e) { toast("Error: " + e.message, "error"); }
  refreshStatus();
});

function logLine(level, module, message, ts) {
  return `<div class="log-line ${level}"><span class="ts">${fmtTime(ts)}</span><span class="mod">[${module}]</span><span class="msg">${escapeHtml(message)}</span></div>`;
}

async function refreshLogs() {
  const logs = (await api("/api/logs?limit=300")).reverse();
  const level = $("#log-level").value;
  const filtered = level ? logs.filter((l) => l.level === level) : logs;
  $("#logs").innerHTML = filtered.map((l) => logLine(l.level, l.module, l.message, l.ts)).join("") || '<div class="log-line"><span class="msg muted">Sin registros</span></div>';
}

$("#log-level").addEventListener("change", refreshLogs);
$("#btn-clear-live").addEventListener("click", () => { state.liveLogs = []; $("#live-log").innerHTML = ""; });

function drawChart() {
  api("/api/history").then((data) => {
    const canvas = $("#resource-chart");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || canvas.parentElement.clientWidth;
    const height = 180;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const snaps = data.history || [];
    if (snaps.length < 2) {
      ctx.fillStyle = "#7d8aa5";
      ctx.font = "13px Segoe UI";
      ctx.fillText("Recopilando datos… (un punto cada 10 minutos)", 20, height / 2);
      return;
    }
    const byTs = {};
    snaps.forEach((s) => {
      byTs[s.ts] = byTs[s.ts] || { metal: 0, crystal: 0, deuterium: 0 };
      byTs[s.ts].metal += s.metal;
      byTs[s.ts].crystal += s.crystal;
      byTs[s.ts].deuterium += s.deuterium;
    });
    const points = Object.entries(byTs).map(([ts, v]) => ({ ts: +ts, ...v }));
    const series = [
      { key: "metal", color: "#d99a6c" },
      { key: "crystal", color: "#7ec8e3" },
      { key: "deuterium", color: "#9d8df1" },
    ];
    const maxVal = Math.max(...points.flatMap((p) => [p.metal, p.crystal, p.deuterium])) || 1;
    const minTs = points[0].ts;
    const maxTs = points[points.length - 1].ts || minTs + 1;
    const pad = 10;

    ctx.strokeStyle = "#26314a";
    ctx.beginPath();
    for (let i = 0; i <= 4; i++) {
      const y = pad + ((height - 2 * pad) * i) / 4;
      ctx.moveTo(pad, y);
      ctx.lineTo(width - pad, y);
    }
    ctx.stroke();

    series.forEach(({ key, color }) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = pad + ((width - 2 * pad) * (p.ts - minTs)) / Math.max(maxTs - minTs, 1);
        const y = height - pad - ((height - 2 * pad) * p[key]) / maxVal;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
  }).catch(() => {});
}

function connectStream() {
  const es = new EventSource("/api/stream" + (state.password ? `?key=${encodeURIComponent(state.password)}` : ""));
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.kind === "log") {
      state.liveLogs.unshift(logLine(data.level, data.module, data.message, data.ts));
      state.liveLogs = state.liveLogs.slice(0, 80);
      $("#live-log").innerHTML = state.liveLogs.join("");
      if (data.level === "attack") toast("⚔️ " + escapeHtml(data.message), "attack", 8000);
      if (data.level === "alert") toast("🚨 " + escapeHtml(data.message), "attack", 8000);
    }
    if (data.kind === "attack") toast("🚨 " + escapeHtml(data.message || "Ataque detectado"), "attack", 8000);
    if (data.kind === "module" || data.kind === "status" || data.kind === "config") refreshStatus();
  };
  es.onerror = () => { es.close(); setTimeout(connectStream, 3000); };
}

function refreshAll() {
  refreshStatus().then(() => { if (state.status) { state.config = state.config; } });
  refreshSummary();
  drawChart();
  api("/api/config").then((cfg) => { state.config = cfg; renderStatus(); renderAllCfgMounts(); }).catch(() => {});
}

renderBuildGrids();
connectStream();
refreshAll();
setInterval(refreshStatus, 5000);
setInterval(refreshSummary, 15000);
setInterval(drawChart, 60000);
setInterval(() => {
  if (document.querySelector("#tab-fleet.active")) refreshFleets();
  if (document.querySelector("#tab-planets.active")) refreshPlanets();
  if (document.querySelector("#tab-farmer.active")) refreshTargets();
  if (document.querySelector("#tab-expeditions.active")) refreshExpeditions();
}, 10000);
