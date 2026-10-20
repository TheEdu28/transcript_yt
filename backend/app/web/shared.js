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
    <summary class="user-menu-trigger">${escapeHtml(user.nombre)} <svg class="ui-icon" aria-hidden="true" style="margin-left:4px" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg></summary>
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

export async function runWithButtonDisabled(button, operation, { cancellable = false } = {}) {
  if (button.dataset.pending === "true") return;
  button.dataset.pending = "true";
  button.disabled = true;

  const controller = new AbortController();
  let cancelBtn = null;
  if (cancellable && button.parentElement) {
    cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "secondary";
    cancelBtn.style.cssText = "margin-left:8px; background:#fee2e2; color:#991b1b; border:1px solid #fca5a5;";
    cancelBtn.textContent = "✕ Cancelar";
    cancelBtn.addEventListener("click", () => controller.abort());
    button.insertAdjacentElement("afterend", cancelBtn);
  }

  try { return await operation(controller.signal); }
  finally {
    if (cancelBtn) cancelBtn.remove();
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

    const providerLabels = { gemini: "Google Gemini", openai: "OpenAI", groq: "Groq", nvidia: "NVIDIA NIM" };

    const optgroups = Object.entries(byProvider).map(([provider, providerModels]) => {
      const options = providerModels.map((m) => {
        const quota = m.quota_exhausted ? " [Cuota agotada]" : "";
        const unavailable = !m.available ? " (sin API key)" : "";
        return `<option value="${escapeHtml(m.model_id)}"
          ${m.model_id === default_model_id ? "selected" : ""}
          ${!m.available || m.quota_exhausted ? "disabled" : ""}>
          ${escapeHtml(m.label)}${quota}${unavailable}
        </option>`;
      }).join("");
      return `<optgroup label="${escapeHtml(providerLabels[provider] || provider)}">${options}</optgroup>`;
    }).join("");

    const getBadgeStyle = (prov) => {
      if (prov === "gemini") return { bg: "#e0f2fe", text: "#0369a1", label: "Google Gemini" };
      if (prov === "groq") return { bg: "#fef3c7", text: "#92400e", label: "Groq Cloud" };
      if (prov === "openai") return { bg: "#dcfce7", text: "#166534", label: "OpenAI" };
      if (prov === "nvidia") return { bg: "#ecfdf5", text: "#047857", label: "NVIDIA NIM" };
      return { bg: "#f1f5f9", text: "#475569", label: prov };
    };

    const initialModel = models.find((m) => m.model_id === default_model_id) || models[0];
    const initialBadge = initialModel ? getBadgeStyle(initialModel.provider) : getBadgeStyle("gemini");

    container.innerHTML = `
      <div class="model-selector">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
          <label class="model-selector-label" for="model-select">Modelo de IA</label>
          <span id="model-provider-badge" style="font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:999px; background:${initialBadge.bg}; color:${initialBadge.text};">${escapeHtml(initialBadge.label)}</span>
        </div>
        <select id="model-select" class="model-select">${optgroups}</select>
        <div id="model-selector-hint" style="font-size:0.78rem; margin-top:6px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 9px; line-height:1.4;">
          💡 <strong>Guía de cuota:</strong> Si la cuota gratuita de Gemini (~100 req/día) se agota, selecciona <strong>Groq (Llama 3.1)</strong> para continuar sin interrupciones.
        </div>
      </div>`;

    const select = container.querySelector("#model-select");
    const badge = container.querySelector("#model-provider-badge");
    select.addEventListener("change", () => {
      selectedModelId = select.value;
      const current = models.find((m) => m.model_id === select.value);
      if (current && badge) {
        const style = getBadgeStyle(current.provider);
        badge.textContent = style.label;
        badge.style.background = style.bg;
        badge.style.color = style.text;
      }
    });
  }).catch(() => { container.innerHTML = ""; });

  return { getSelectedModelId: () => selectedModelId };
}
