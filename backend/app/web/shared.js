import { auth } from "/ui/api.js";

/** Redirige a /ui/auth/ si no hay sesión activa. Llamar al inicio de páginas protegidas. */
export function requireAuth() {
  if (!auth.isLoggedIn()) {
    window.location.assign("/ui/auth/");
  }
}

/** Inyecta el nombre del usuario y un menú desplegable de sesión con navegación completa. */
export function renderUserBar() {
  const bar = document.getElementById("user-bar");
  if (!bar) return;
  const user = auth.user();
  if (!user) return;

  bar.innerHTML = `
    <details class="user-menu">
      <summary class="user-menu-trigger" aria-haspopup="true" aria-label="Menú de usuario">
        <span class="user-avatar-badge">${escapeHtml((user.nombre || "U").charAt(0).toUpperCase())}</span>
        <span class="user-menu-name">${escapeHtml(user.nombre)}</span>
        <svg class="ui-icon" aria-hidden="true" style="margin-left:4px" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
      </summary>
      <div class="user-menu-panel" role="menu">
        <div class="user-menu-header">
          <strong>${escapeHtml(user.nombre)}</strong>
          <small>${escapeHtml(user.email || "")}</small>
        </div>
        <hr class="user-menu-divider">
        <a href="/ui/groups/" role="menuitem">
          <svg class="ui-icon" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          Mis grupos
        </a>
        <a href="/ui/videos/" role="menuitem">
          <svg class="ui-icon" viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
          Mis videos
        </a>
        <a href="/ui/video/" role="menuitem">
          <svg class="ui-icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Procesar nuevo video
        </a>
        <hr class="user-menu-divider">
        <button id="logout-btn" type="button" role="menuitem">
          <svg class="ui-icon" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Cerrar sesión
        </button>
      </div>
    </details>`;

  bar.querySelector("#logout-btn")?.addEventListener("click", () => {
    auth.clear();
    window.location.assign("/ui/auth/");
  });
}

export function getPositiveIntParam(name) {
  const value = Number(new URLSearchParams(window.location.search).get(name));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function urlFor(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  }
  return `${url.pathname}${url.search}`;
}

export function goTo(path, params = {}) {
  window.location.assign(urlFor(path, params));
}

export function replaceUrl(path, params = {}) {
  window.history.replaceState({}, "", urlFor(path, params));
}

/**
 * Muestra un aviso en el contenedor #notice y emite un toast no intrusivo si corresponde.
 * Garantiza que notice se haga visible si contiene texto, o se oculte si está vacío.
 */
export function showNotice(message, type = "") {
  const notice = document.querySelector("#notice");
  if (notice) {
    if (!message) {
      notice.textContent = "";
      notice.style.display = "none";
      return;
    }
    notice.textContent = message;
    notice.className = `notice ${type}`.trim();
    notice.style.display = "";
    notice.setAttribute("role", type === "error" ? "alert" : "status");
  }

  // Notificar también como toast flotante para que el usuario siempre reciba retroalimentación
  if (message && (type === "success" || type === "error" || type === "info")) {
    showToast(message, type);
  }
}

/**
 * Notificación tipo Toast emergente flotante, no bloqueante y auto-descartable.
 *
 * @param {string} message
 * @param {"info" | "success" | "error" | "warning"} type
 * @param {number} duration Duración en milisegundos (default 4000)
 */
export function showToast(message, type = "info", duration = 4000) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.setAttribute("role", type === "error" ? "alert" : "status");

  let iconSvg = "";
  if (type === "success") {
    iconSvg = `<svg class="ui-icon icon-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>`;
  } else if (type === "error") {
    iconSvg = `<svg class="ui-icon icon-close" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
  } else if (type === "warning") {
    iconSvg = `<svg class="ui-icon icon-tip" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
  } else {
    iconSvg = `<svg class="ui-icon icon-video" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
  }

  toast.innerHTML = `
    <span class="toast-icon">${iconSvg}</span>
    <span class="toast-text">${escapeHtml(message)}</span>
    <button type="button" class="toast-close" aria-label="Cerrar notificación">&times;</button>
  `;

  const removeToast = () => {
    toast.classList.add("toast--exit");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  };

  toast.querySelector(".toast-close")?.addEventListener("click", removeToast);

  if (duration > 0) {
    setTimeout(removeToast, duration);
  }

  container.appendChild(toast);
}

/**
 * Cuadro de diálogo modal accesible para confirmar acciones importantes.
 * Sustituye el confirm() nativo del navegador por una interfaz coherente.
 *
 * @param {object} options
 * @param {string} options.title Título del diálogo
 * @param {string} options.message Mensaje explicativo de la acción
 * @param {string} [options.confirmText="Confirmar"] Texto del botón de confirmación
 * @param {string} [options.cancelText="Cancelar"] Texto del botón cancelar
 * @param {boolean} [options.danger=false] Si la acción es destructiva (botón rojo)
 * @returns {Promise<boolean>}
 */
export function confirmModal({
  title = "Confirmar acción",
  message = "¿Estás seguro de que deseas continuar?",
  confirmText = "Confirmar",
  cancelText = "Cancelar",
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop confirm-modal-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-labelledby", "confirm-dialog-title");

    const confirmBtnClass = danger ? "btn-danger" : "";
    const dangerIcon = danger
      ? `<div class="confirm-icon-box confirm-icon-box--danger">
           <svg class="ui-icon" style="width:20px;height:20px" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
         </div>`
      : `<div class="confirm-icon-box confirm-icon-box--info">
           <svg class="ui-icon" style="width:20px;height:20px" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
         </div>`;

    backdrop.innerHTML = `
      <div class="modal confirm-modal" style="max-width:440px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          ${dangerIcon}
          <h3 id="confirm-dialog-title" style="margin:0;font-size:18px;color:var(--ink)">${escapeHtml(title)}</h3>
        </div>
        <p style="font-size:13px;color:var(--muted);line-height:1.5;margin:0 0 20px">
          ${escapeHtml(message)}
        </p>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" class="secondary" id="confirm-cancel-btn">${escapeHtml(cancelText)}</button>
          <button type="button" class="${confirmBtnClass}" id="confirm-action-btn">${escapeHtml(confirmText)}</button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    const cleanup = (result) => {
      document.removeEventListener("keydown", handleKeyDown);
      backdrop.remove();
      resolve(result);
    };

    const handleKeyDown = (e) => {
      if (e.key === "Escape") cleanup(false);
    };

    document.addEventListener("keydown", handleKeyDown);
    backdrop.querySelector("#confirm-cancel-btn")?.addEventListener("click", () => cleanup(false));
    backdrop.querySelector("#confirm-action-btn")?.addEventListener("click", () => cleanup(true));
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) cleanup(false);
    });

    // Poner foco en el botón de cancelar para evitar pulsaciones accidentales en acciones destructivas
    const focusTarget = danger
      ? backdrop.querySelector("#confirm-cancel-btn")
      : backdrop.querySelector("#confirm-action-btn");
    focusTarget?.focus();
  });
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

  try {
    return await operation(controller.signal);
  } finally {
    if (cancelBtn) cancelBtn.remove();
    delete button.dataset.pending;
    button.disabled = false;
  }
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
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

  container.innerHTML = `<div class="model-selector-loading">Cargando modelos de IA disponibles…</div>`;

  fetchModels().then(({ models, default_model_id }) => {
    selectedModelId = default_model_id;

    // Agrupar por proveedor
    const byProvider = {};
    for (const m of models) {
      if (!byProvider[m.provider]) byProvider[m.provider] = [];
      byProvider[m.provider].push(m);
    }

    const providerLabels = {
      gemini: "Google Gemini",
      openai: "OpenAI",
      groq: "Groq Cloud",
      nvidia: "NVIDIA NIM",
    };

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
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; width:100%">
          <label class="model-selector-label" for="model-select">Modelo de IA para generación</label>
          <span id="model-provider-badge" style="font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:999px; background:${initialBadge.bg}; color:${initialBadge.text};">${escapeHtml(initialBadge.label)}</span>
        </div>
        <select id="model-select" class="model-select">${optgroups}</select>
        <div id="model-selector-hint" class="model-selector-hint">
          💡 <strong>Guía de cuota:</strong> Si la cuota gratuita de Gemini (~100 req/día) se agota, conmuta a <strong>Groq (Llama 3.1)</strong> para continuar sin interrupciones.
        </div>
      </div>`;

    const select = container.querySelector("#model-select");
    const badge = container.querySelector("#model-provider-badge");
    select?.addEventListener("change", () => {
      selectedModelId = select.value;
      const current = models.find((m) => m.model_id === select.value);
      if (current && badge) {
        const style = getBadgeStyle(current.provider);
        badge.textContent = style.label;
        badge.style.background = style.bg;
        badge.style.color = style.text;
      }
    });
  }).catch(() => {
    container.innerHTML = "";
  });

  return { getSelectedModelId: () => selectedModelId };
}
