import { apiDeleteVideo, apiListGroups, apiListMyVideos, apiPublishVideoAsTopic } from "/ui/api.js";
import { escapeHtml, renderUserBar, requireAuth, runWithButtonDisabled, urlFor } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
let currentPage = 1;
const PAGE_SIZE = 20;
let myGroups = [];
let pendingVideoId = null;
let currentStatus = "";

// Filtro de status
byId("status-filter").addEventListener("change", () => {
  currentStatus = byId("status-filter").value;
  loadPage(1);
});

function noticeVisible(msg, type) {
  const el = byId("notice");
  el.textContent = msg;
  el.className = `notice ${type}`.trim();
  el.style.display = "";
}

function formatDuration(secs) {
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function renderBadges(item) {
  const badges = [];
  if (item.has_summary) badges.push(`<span class="vid-badge vid-badge--summary">Resumen</span>`);
  if (item.has_quiz)    badges.push(`<span class="vid-badge vid-badge--quiz">Quiz</span>`);
  if (item.published_in_groups.length) badges.push(`<span class="vid-badge vid-badge--published">Publicado (${item.published_in_groups.length})</span>`);
  return badges.join("");
}

function renderList(items) {
  const list = byId("videos-list");
  if (!items.length) { list.className = "empty-state"; list.textContent = "Aún no has procesado ningún video."; return; }
  list.className = "vid-list";
  list.innerHTML = items.map((v) => `
    <article class="vid-card" data-id="${v.id}">
      <div class="vid-card-main">
        <strong class="vid-title">${escapeHtml(v.title)}</strong>
        <span class="vid-meta">${v.language.toUpperCase()} · ${formatDuration(v.duration_seconds)} · ${v.created_at ? new Date(v.created_at).toLocaleDateString("es") : "—"}</span>
        <div class="vid-badges">${renderBadges(v)}</div>
      </div>
      <div class="vid-actions">
        <a class="topic-link" href="${urlFor("/ui/resumen/", { video: v.id })}">Resumen</a>
        <a class="topic-link" href="${urlFor("/ui/quiz/", { video: v.id })}">Quiz</a>
        <button class="secondary vid-publish-btn" data-id="${v.id}" data-title="${escapeHtml(v.title)}" type="button">Publicar en grupo</button>
        <button class="vid-delete-btn" data-id="${v.id}" type="button" title="Eliminar video y sus vectores">🗑</button>
      </div>
    </article>`).join("");

  list.querySelectorAll(".vid-publish-btn").forEach((btn) => {
    btn.addEventListener("click", () => openPublishModal(Number(btn.dataset.id), btn.dataset.title));
  });

  list.querySelectorAll(".vid-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este video y todos sus vectores de ChromaDB? Esta acción no se puede deshacer.")) return;
      try {
        await apiDeleteVideo(Number(btn.dataset.id));
        noticeVisible("Video eliminado.", "success");
        await loadPage(currentPage);
      } catch (err) { noticeVisible(err.message, "error"); }
    });
  });
}

function renderPagination(total, page) {
  const pages = Math.ceil(total / PAGE_SIZE);
  const el = byId("pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <button class="secondary" id="prev-btn" ${page <= 1 ? "disabled" : ""}>← Anterior</button>
    <span class="page-info">Página ${page} de ${pages}</span>
    <button class="secondary" id="next-btn" ${page >= pages ? "disabled" : ""}>Siguiente →</button>`;
  el.querySelector("#prev-btn")?.addEventListener("click", () => loadPage(page - 1));
  el.querySelector("#next-btn")?.addEventListener("click", () => loadPage(page + 1));
}

async function loadPage(page) {
  currentPage = page;
  try {
    const { items, total } = await apiListMyVideos(page, PAGE_SIZE, currentStatus || null);
    renderList(items);
    renderPagination(total, page);
  } catch (err) { noticeVisible(err.message, "error"); }
}

// --- Modal publicar ---
function openPublishModal(videoId, videoTitle) {
  pendingVideoId = videoId;
  byId("modal-video-name").textContent = videoTitle;
  byId("publish-title").value = videoTitle;
  byId("publish-desc").value = "";

  const sel = byId("publish-group");
  sel.innerHTML = myGroups.length
    ? myGroups.map((g) => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("")
    : `<option disabled>No tienes grupos creados</option>`;

  byId("publish-modal").style.display = "";
}

byId("modal-cancel").addEventListener("click", () => { byId("publish-modal").style.display = "none"; });
byId("publish-modal").addEventListener("click", (e) => { if (e.target === byId("publish-modal")) byId("publish-modal").style.display = "none"; });

byId("publish-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("modal-submit"), async () => {
    try {
      const groupId = Number(byId("publish-group").value);
      await apiPublishVideoAsTopic(groupId, pendingVideoId, byId("publish-title").value.trim(), byId("publish-desc").value.trim());
      byId("publish-modal").style.display = "none";
      noticeVisible("Video publicado como tema en el grupo.", "success");
      await loadPage(currentPage); // refrescar badges
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});

// Cargar grupos del usuario para el modal (solo los que administra)
apiListGroups().then((groups) => { myGroups = groups; }).catch(() => {});
loadPage(1);
