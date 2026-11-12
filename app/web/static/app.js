const state = {
  status: null,
  planets: null,
  fleets: null,
  config: null,
  logs: [],
  liveLogs: [],
};

const $ = (sel) => document.querySelector(sel);
const fmt = (n) => (typeof n === "number" ? Math.round(n).toLocaleString("es-ES") : n);
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("es-ES");

function tab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "planets") refreshPlanets();
  if (name === "fleet") refreshFleets();
  if (name === "farmer") refreshTargets();
  if (name === "config") refreshConfig();
  if (name === "logs") refreshLogs();
  if (name === "account") refreshAccount();
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => tab(b.dataset.tab)));

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || resp.statusText);
  }
  return resp.json();
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    state.status = s;
    renderStatus();
  } catch (e) { console.error(e); }
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  const pill = $("#status-pill");
  const pillState = s.running ? (s.paused ? "paused" : "running") : "stopped";
  pill.className = `pill ${pillState}`;
  pill.textContent = s.running ? (s.paused ? "Pausado" : "En marcha") : "Detenido";
  $("#btn-pause").disabled = !s.running;
  $("#btn-start").disabled = s.running;
  $("#account-line").textContent = s.has_account
    ? `${s.account ? s.account.universe : s.universe}${s.demo ? " · DEMO" : ""} — ${s.account ? s.account.username : ""}`
    : "Sin cuenta configurada";

  const box = s.event_box || {};
  const alerts = $("#alerts");
  const items = [];
  if (box.hostile > 0) items.push(`<div class="alert danger">⚠️ ¡Ataque hostil detectado! (${box.hostile} flotas)</div>`);
  if (s.last_results && s.last_results.fleetsave && Date.now() / 1000 - s.last_results.fleetsave.ts < 600)
    items.push(`<div class="alert danger">Fleet-save: ${s.last_results.fleetsave.detail}</div>`);
  if (!items.length) items.push('<div class="alert ok">Sin amenazas. Todo en orden.</div>');
  alerts.innerHTML = items.join("");

  const bs = $("#bot-state");
  const uptime = s.started_at ? Math.floor(Date.now() / 1000 - s.started_at) : 0;
  bs.innerHTML = `
    <span class="k">Ciclos</span><span>${s.ticks || 0}</span>
    <span class="k">Tiempo activo</span><span>${Math.floor(uptime / 60)}m ${uptime % 60}s</span>
    <span class="k">Modo</span><span>${s.demo ? "Demo (simulado)" : "Real"}</span>
    <span class="k">Acción actual</span><span>${s.current || "—"}</span>`;

  const tbody = $("#modules-table tbody");
  const catalog = s.module_catalog || [];
  const results = s.last_results || {};
  const nextRuns = s.next_runs || {};
  tbody.innerHTML = catalog.map((m) => {
    const r = results[m.name];
    const next = nextRuns[m.name];
    return `<tr>
      <td>${m.label}</td>
      <td>${r ? (r.status === "ok" ? "✅" : "❌ " + r.status) : "—"}</td>
      <td>${r ? r.detail : "—"}</td>
      <td>${next ? fmtTime(next) : "—"}</td>
    </tr>`;
  }).join("");
}

async function refreshPlanets() {
  try {
    const data = await api("/api/planets");
    const container = $("#planets-container");
    container.innerHTML = data.planets.map((p) => {
      const res = data.resources[p.id] || {};
      const store = res.storage || [1, 1, 1];
      const pct = (v, s) => Math.min(100, (v / Math.max(s, 1)) * 100);
      const b = data.buildings[p.id] || {};
      const queueHtml = (b._queue || []).map((q) => `<div class="res-row"><span class="k">En cola: ${q.tech || "?"}</span><span>${q.time_left != null ? q.time_left + "s" : ""}</span></div>`).join("");
      const keyBuildings = [1, 2, 3, 4, 14, 21, 31].map((id) => b[id] ? `${b[id].name}: <b>${b[id].level}</b>` : "").filter(Boolean).join(" · ");
      const shipList = Object.values(data.ships[p.id] || {}).filter((s) => s.amount > 0)
        .map((s) => `<span class="res-row"><span>${s.name}</span><span class="val">${fmt(s.amount)}</span></span>`).join("");
      return `<div class="planet-card">
        <h4>${p.name}</h4>
        <div class="coords">[${p.coords.join(":")}] · ${p.type === "moon" ? "Luna" : "Planeta"}</div>
        <div class="res-row"><span>Metal</span><span class="val metal">${fmt(res.metal)}</span></div>
        <div class="bar"><div style="width:${pct(res.metal, store[0])}%"></div></div>
        <div class="res-row"><span>Cristal</span><span class="val crystal">${fmt(res.crystal)}</span></div>
        <div class="bar"><div style="width:${pct(res.crystal, store[1])}%"></div></div>
        <div class="res-row"><span>Deuterio</span><span class="val deut">${fmt(res.deuterium)}</span></div>
        <div class="bar"><div style="width:${pct(res.deuterium, store[2])}%"></div></div>
        <div class="res-row"><span>Energía</span><span class="val energy">${fmt(res.energy)}</span></div>
        ${queueHtml}
        <p class="muted" style="font-size:12px">${keyBuildings}</p>
        ${shipList}
      </div>`;
    }).join("");
  } catch (e) {
    $("#planets-container").innerHTML = `<div class="card">No disponible: ${e.message}. ¿Está el bot iniciado?</div>`;
  }
}

async function refreshFleets() {
  try {
    const data = await api("/api/fleets");
    $("#fleet-slots").innerHTML = `
      <span class="k">Flota</span><span>${data.slots.fleet.used} / ${data.slots.fleet.total}</span>
      <span class="k">Expediciones</span><span>${data.slots.expedition.used} / ${data.slots.expedition.total}</span>`;
    const missions = { 1: "Ataque", 3: "Transporte", 4: "Despliegue", 6: "Espionaje", 8: "Reciclaje", 15: "Expedición" };
    $("#fleets-table tbody").innerHTML = (data.fleets || []).map((f) => `<tr>
      <td>${missions[f.mission] || f.mission}</td>
      <td>[${(f.origin || []).join(":")}]</td>
      <td>[${(f.destination || []).join(":")}]</td>
      <td>${fmtTime(f.arrival)}</td>
      <td>${f.return_flight ? "sí" : "no"}</td>
    </tr>`).join("") || '<tr><td colspan="5" class="muted">Sin flotas en movimiento</td></tr>';
  } catch (e) {
    $("#fleet-slots").innerHTML = `<span class="k">No disponible: ${e.message}</span><span></span>`;
  }
}

async function refreshTargets() {
  try {
    const data = await api("/api/targets");
    $("#targets-table tbody").innerHTML = (data.targets || []).map((t) => `<tr>
      <td>[${t.galaxy}:${t.system}:${t.position}]</td>
      <td>${t.player || "—"}</td>
      <td>${t.inactive ? "✔️" : "—"}</td>
      <td>${fmt(t.metal + t.crystal + t.deuterium)}</td>
      <td>${t.last_spied ? fmtTime(t.last_spied) : "—"}</td>
      <td>${t.attacks}</td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">Sin objetivos. Activa el módulo Farmer para escanear galaxias.</td></tr>';
  } catch (e) {
    console.error(e);
  }
}

async function refreshConfig() {
  try {
    const cfg = await api("/api/config");
    state.config = cfg;
    const container = $("#config-container");
    container.innerHTML = Object.entries(cfg).map(([name, mod]) => {
      const fields = Object.entries(mod).filter(([k]) => k !== "enabled").map(([k, v]) => {
        const value = typeof v === "object" ? JSON.stringify(v) : v;
        return `<label>${k}<input data-module="${name}" data-key="${k}" value='${value}'></label>`;
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
  document.querySelectorAll("#config-container [data-module]").forEach((el) => {
    const mod = config[el.dataset.module] = config[el.dataset.module] || {};
    const key = el.dataset.key;
    let value = el.type === "checkbox" ? el.checked : el.value;
    if (el.type !== "checkbox") {
      try { value = JSON.parse(value); } catch { try { value = Number(value); } catch {} }
    }
    mod[key] = value;
  });
  try {
    await api("/api/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config }) });
    alert("Configuración guardada");
  } catch (e) { alert("Error: " + e.message); }
});

async function refreshAccount() {
  const acc = await api("/api/account");
  const form = $("#account-form");
  form.universe.value = acc.universe;
  form.language.value = acc.language || "es";
  form.username.value = acc.username;
  form.demo.checked = !!acc.demo;
}

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
    alert("Cuenta guardada. Ya puedes iniciar el bot.");
    refreshStatus();
  } catch (e) { alert("Error: " + e.message); }
});

$("#btn-start").addEventListener("click", async () => {
  try { await api("/api/bot/start", { method: "POST" }); } catch (e) { alert("Error: " + e.message); }
  refreshStatus();
});

$("#btn-stop").addEventListener("click", async () => {
  await api("/api/bot/stop", { method: "POST" });
  refreshStatus();
});

$("#btn-pause").addEventListener("click", async () => {
  const paused = !(state.status && state.status.paused);
  await api("/api/bot/pause", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paused }) });
  refreshStatus();
});

function logLine(level, module, message, ts) {
  return `<div class="log-line ${level}"><span class="ts">${fmtTime(ts)}</span><span class="mod">[${module}]</span><span class="msg">${escapeHtml(message)}</span></div>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function refreshLogs() {
  const logs = (await api("/api/logs?limit=300")).reverse();
  const level = $("#log-level").value;
  const filtered = level ? logs.filter((l) => l.level === level) : logs;
  $("#logs").innerHTML = filtered.map((l) => logLine(l.level, l.module, l.message, l.ts)).join("") || '<div class="log-line"><span class="msg muted">Sin registros</span></div>';
}

$("#log-level").addEventListener("change", refreshLogs);

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.kind === "log") {
      state.liveLogs.unshift(logLine(data.level, data.module, data.message, data.ts));
      state.liveLogs = state.liveLogs.slice(0, 80);
      $("#live-log").innerHTML = state.liveLogs.join("");
    }
    if (data.kind === "module" || data.kind === "status" || data.kind === "attack" || data.kind === "config") {
      refreshStatus();
    }
  };
  es.onerror = () => { es.close(); setTimeout(connectStream, 3000); };
}

connectStream();
refreshStatus();
setInterval(refreshStatus, 5000);
setInterval(() => {
  if (document.querySelector("#tab-fleet.active")) refreshFleets();
  if (document.querySelector("#tab-planets.active")) refreshPlanets();
}, 10000);
