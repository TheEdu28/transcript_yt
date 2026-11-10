import { apiDeleteVideo, apiListGroups, apiListMyVideos, apiPublishVideoAsTopic } from "/ui/api.js?v=2";
import { confirmModal, escapeHtml, renderUserBar, requireAuth, runWithButtonDisabled, showNotice, urlFor } from "/ui/shared.js?v=2";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
let currentPage = 1;
const PAGE_SIZE = 20;
let myGroups = [];
let pendingVideoId = null;
let currentStatus = "";
let currentSearch = "";
let currentOrder = "desc";
let searchDebounceTimer = null;

// Filtro de status
byId("status-filter")?.addEventListener("change", () => {
  currentStatus = byId("status-filter").value;
  loadPage(1);
});

// Filtro de búsqueda por título con debounce
byId("video-search-input")?.addEventListener("input", (e) => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    currentSearch = e.target.value.trim();
    loadPage(1);
  }, 250);
});

// Selector de orden cronológico
byId("sort-order-toggle")?.addEventListener("click", (e) => {
    currentOrder = currentOrder === "desc" ? "asc" : "desc";
    e.currentTarget.textContent = currentOrder === "desc" ? "↓ Más recientes primero" : "↑ Más antiguos primero";
    loadPage(1);
  });

function formatDuration(secs) {
  if (!secs && secs !== 0) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function renderBadges(item) {
  const badges = [];
  if (item.has_summary) {
    badges.push(`<span class="vid-badge vid-badge--summary" title="Resumen didáctico generado">Resumen</span>`);
  }
  if (item.has_quiz) {
    badges.push(`<span class="vid-badge vid-badge--quiz" title="Cuestionario generado">Quiz</span>`);
  }
  if (item.published_in_groups && item.published_in_groups.length) {
    badges.push(`<span class="vid-badge vid-badge--published" title="Publicado en ${item.published_in_groups.length} grupo(s)">Publicado (${item.published_in_groups.length})</span>`);
  }
  return badges.join("");
}

function renderList(items) {
  const list = byId("videos-list");
  if (!list) return;

  if (!items.length) {
    list.className = "empty-state";
    list.innerHTML = `
      <div style="max-width:420px;margin:12px auto;text-align:center">
        <svg class="ui-icon icon-video" style="width:36px;height:36px;margin-bottom:8px" viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
        <p style="margin:0 0 12px;font-weight:600;color:var(--ink)">
          ${currentStatus ? "No se encontraron videos con el filtro seleccionado." : "Aún no has procesado ningún video."}
        </p>
        <p style="margin:0 0 18px;font-size:13px;color:var(--muted)">
          Importa una URL de YouTube para transcribir el audio con Whisper y generar resúmenes o cuestionarios interactivos.
        </p>
        <a href="/ui/video/" class="primary-action" style="margin:0 auto">
          + Procesar mi primer video
        </a>
      </div>
    `;
    return;
  }

  list.className = "vid-list";
  list.innerHTML = items.map((v) => `
    <article class="vid-card" data-id="${v.id}">
      <div class="vid-card-main">
        <strong class="vid-title" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</strong>
        <span class="vid-meta">
          ${(v.language || "es").toUpperCase()} · ${formatDuration(v.duration_seconds)} · ${v.created_at ? new Date(v.created_at).toLocaleDateString("es") : "Fecha no disp."}
        </span>
        <div class="vid-badges">${renderBadges(v)}</div>
      </div>
      <div class="vid-actions">
        <a class="topic-link" href="${urlFor("/ui/resumen/", { video: v.id })}">
          <svg class="ui-icon icon-book" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
          Resumen
        </a>
        <a class="topic-link" href="${urlFor("/ui/quiz/", { video: v.id })}">
          <svg class="ui-icon icon-pencil" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          Quiz
        </a>
        <button class="secondary vid-publish-btn" data-id="${v.id}" data-title="${escapeHtml(v.title)}" type="button">
          Publicar en grupo
        </button>
        <button class="vid-delete-btn btn-icon" data-id="${v.id}" data-title="${escapeHtml(v.title)}" type="button" title="Eliminar video y sus vectores">
          <svg class="ui-icon icon-trash" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
        </button>
      </div>
    </article>`).join("");

  list.querySelectorAll(".vid-publish-btn").forEach((btn) => {
    btn.addEventListener("click", () => openPublishModal(Number(btn.dataset.id), btn.dataset.title));
  });

  list.querySelectorAll(".vid-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const vidTitle = btn.dataset.title || "este video";
      const confirmed = await confirmModal({
        title: "Eliminar video",
        message: `¿Estás seguro de que deseas eliminar «${vidTitle}» y todos sus vectores de ChromaDB? Esta acción no se puede deshacer.`,
        confirmText: "Sí, eliminar video",
        cancelText: "Conservar video",
        danger: true,
      });
      if (!confirmed) return;

      try {
        await apiDeleteVideo(Number(btn.dataset.id));
        showNotice("Video y vectores eliminados exitosamente.", "success");
        await loadPage(currentPage);
      } catch (err) {
        showNotice(err.message, "error");
      }
    });
  });
}

function renderPagination(total, page) {
  const pages = Math.ceil(total / PAGE_SIZE);
  const el = byId("pagination");
  if (!el) return;
  if (pages <= 1) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `
    <button class="secondary" id="prev-btn" ${page <= 1 ? "disabled" : ""}>← Anterior</button>
    <span class="page-info">Página <strong>${page}</strong> de ${pages} (${total} videos)</span>
    <button class="secondary" id="next-btn" ${page >= pages ? "disabled" : ""}>Siguiente →</button>`;
  el.querySelector("#prev-btn")?.addEventListener("click", () => loadPage(page - 1));
  el.querySelector("#next-btn")?.addEventListener("click", () => loadPage(page + 1));
}

async function loadPage(page) {
  currentPage = page;
  try {
    const { items, total } = await apiListMyVideos(
      page,
      PAGE_SIZE,
      currentStatus || null,
      currentSearch || null,
      currentOrder
    );
    renderList(items);
    renderPagination(total, page);
  } catch (err) {
    showNotice(err.message, "error");
  }
}

// --- Modal publicar ---
function openPublishModal(videoId, videoTitle) {
  pendingVideoId = videoId;
  byId("modal-video-name").textContent = `Video: ${videoTitle}`;
  byId("publish-title").value = videoTitle;
  byId("publish-desc").value = "";

  const sel = byId("publish-group");
  sel.innerHTML = myGroups.length
    ? myGroups.map((g) => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("")
    : `<option disabled>No tienes grupos creados (crea uno en Mis Grupos primero)</option>`;

  byId("publish-modal").style.display = "grid";
  byId("publish-title")?.focus();
}

function closePublishModal() {
  byId("publish-modal").style.display = "none";
  pendingVideoId = null;
}

byId("modal-cancel")?.addEventListener("click", closePublishModal);
byId("modal-close-x")?.addEventListener("click", closePublishModal);
byId("publish-modal")?.addEventListener("click", (e) => {
  if (e.target === byId("publish-modal")) closePublishModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && byId("publish-modal")?.style.display !== "none") {
    closePublishModal();
  }
});

byId("publish-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const selectVal = byId("publish-group").value;
  if (!selectVal) {
    showNotice("Debes seleccionar un grupo para publicar.", "error");
    return;
  }

  await runWithButtonDisabled(byId("modal-submit"), async () => {
    try {
      const groupId = Number(selectVal);
      await apiPublishVideoAsTopic(
        groupId,
        pendingVideoId,
        byId("publish-title").value.trim(),
        byId("publish-desc").value.trim()
      );
      closePublishModal();
      showNotice("¡Video publicado exitosamente como tema en el grupo!", "success");
      await loadPage(currentPage); // refrescar badges
    } catch (err) {
      showNotice(err.message, "error");
    }
  });
});

// Cargar grupos del usuario para el modal (solo los que administra)
apiListGroups().then((groups) => {
  myGroups = groups || [];
}).catch(() => {});

loadPage(1);
