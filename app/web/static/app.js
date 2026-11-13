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
  if (name === "config") refreshConfig();
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

async function refreshConfig() {
  try {
    const cfg = await api("/api/config");
    state.config = cfg;
    const container = $("#config-container");
    container.innerHTML = Object.entries(cfg).map(([name, mod]) => {
      const fields = Object.entries(mod).filter(([k]) => k !== "enabled").map(([k, v]) => {
        const value = typeof v === "object" ? JSON.stringify(v) : v;
        return `<label>${k}<input data-module="${name}" data-key="${k}" value='${String(value).replace(/'/g, "&#39;")}'></label>`;
      }).join("");
      return `<div class="card">
        <div class="toggle">
          <input type="checkbox" data-module="${name}" data-key="enabled" ${mod.enabled ? "checked" : ""}>
          <b>${name}</b>
        </div>
        <div class="config-row">${fields}</div>
      </div>`;
    }).join("");
  } catch (e) { console.error(e); }
}

$("#btn-save-config").addEventListener("click", async () => {
  const config = {};
  $$("#config-container [data-module]").forEach((el) => {
    const mod = config[el.dataset.module] = config[el.dataset.module] || {};
    const key = el.dataset.key;
    let value = el.type === "checkbox" ? el.checked : el.value;
    if (el.type !== "checkbox") {
      try { value = JSON.parse(value); } catch { const num = Number(value); if (!isNaN(num) && value !== "") value = num; }
    }
    mod[key] = value;
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
      }),
    });
    toast("Cuenta guardada. Ya puedes iniciar el bot.", "success");
    refreshStatus();
  } catch (e) { toast("Error: " + e.message, "error"); }
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

$("#btn-start").addEventListener("click", async () => {
  try {
    await api("/api/bot/start", { method: "POST" });
    toast("Bot iniciado 🚀", "success");
  } catch (e) { toast("Error: " + e.message, "error"); }
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
  api("/api/config").then((cfg) => { state.config = cfg; renderStatus(); }).catch(() => {});
}

connectStream();
refreshAll();
setInterval(refreshStatus, 5000);
setInterval(refreshSummary, 15000);
setInterval(drawChart, 60000);
setInterval(() => {
  if (document.querySelector("#tab-fleet.active")) refreshFleets();
  if (document.querySelector("#tab-planets.active")) refreshPlanets();
  if (document.querySelector("#tab-farmer.active")) refreshTargets();
}, 10000);
