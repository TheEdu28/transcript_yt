import { auth } from "/ui/api.js";

/** Redirige a /ui/auth/ si no hay sesión activa. Llamar al inicio de páginas protegidas. */
export function requireAuth() {
  if (!auth.isLoggedIn()) { window.location.assign("/ui/auth/"); }
}

/** Inyecta el nombre del usuario y un menú desplegable de sesión. */
export function renderUserBar() {
  const bar = document.getElementById("user-bar");
  if (!bar) return;
  const user = auth.user();
  if (!user) return;
  bar.innerHTML = `<details class="user-menu">
    <summary class="user-menu-trigger">${escapeHtml(user.nombre)} <span aria-hidden="true">⌄</span></summary>
    <div class="user-menu-panel">
      <a href="/ui/groups/">Mis grupos</a>
      <a href="/ui/video/">Procesar video</a>
      <button id="logout-btn" type="button">Cerrar sesión</button>
    </div>
  </details>`;
  bar.querySelector("#logout-btn").addEventListener("click", () => { auth.clear(); window.location.assign("/ui/auth/"); });
}

export function getPositiveIntParam(name) {
  const value = Number(new URLSearchParams(window.location.search).get(name));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function urlFor(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined) url.searchParams.set(key, String(value));
  return `${url.pathname}${url.search}`;
}

export function goTo(path, params = {}) { window.location.assign(urlFor(path, params)); }
export function replaceUrl(path, params = {}) { window.history.replaceState({}, "", urlFor(path, params)); }

export function showNotice(message, type = "") {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.className = `notice ${type}`.trim();
}

export async function runWithButtonDisabled(button, operation) {
  if (button.dataset.pending === "true") return;
  button.dataset.pending = "true";
  button.disabled = true;
  try { return await operation(); }
  finally {
    delete button.dataset.pending;
    button.disabled = false;
  }
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

/**
 * Carga los modelos desde /api/v1/models y renderiza un <select> agrupado por proveedor.
 * Devuelve getSelectedModelId() para leer la elección al enviar el formulario.
 *
 * @param {string} containerId
 * @param {Function} fetchModels
 * @returns {{ getSelectedModelId: () => string | null }}
 */
export function initModelSelector(containerId, fetchModels) {
  let selectedModelId = null;

  const container = document.getElementById(containerId);
  if (!container) return { getSelectedModelId: () => null };

  container.innerHTML = `<div class="model-selector-loading">Cargando modelos…</div>`;

  fetchModels().then(({ models, default_model_id }) => {
    selectedModelId = default_model_id;

    // Agrupar por proveedor
    const byProvider = {};
    for (const m of models) {
      if (!byProvider[m.provider]) byProvider[m.provider] = [];
      byProvider[m.provider].push(m);
    }

    const providerLabels = { gemini: "Google Gemini", openai: "OpenAI", groq: "Groq" };

    const optgroups = Object.entries(byProvider).map(([provider, providerModels]) => {
      const options = providerModels.map((m) => {
        const quota = m.quota_exhausted ? " ⚠️ Cuota agotada" : "";
        const unavailable = !m.available ? " (sin API key)" : "";
        return `<option value="${escapeHtml(m.model_id)}"
          ${m.model_id === default_model_id ? "selected" : ""}
          ${!m.available || m.quota_exhausted ? "disabled" : ""}>
          ${escapeHtml(m.label)}${quota}${unavailable}
        </option>`;
      }).join("");
      return `<optgroup label="${escapeHtml(providerLabels[provider] || provider)}">${options}</optgroup>`;
    }).join("");

    container.innerHTML = `
      <div class="model-selector">
        <label class="model-selector-label" for="model-select">Modelo de IA</label>
        <select id="model-select" class="model-select">${optgroups}</select>
      </div>`;

    const select = container.querySelector("#model-select");
    select.addEventListener("change", () => { selectedModelId = select.value; });
  }).catch(() => { container.innerHTML = ""; });

  return { getSelectedModelId: () => selectedModelId };
}
