import { apiAddMember, apiCreateTopic, apiDeleteTopic, apiGetGroup, apiListTopics, apiRemoveMember, auth } from "/ui/api.js";
import { escapeHtml, getPositiveIntParam, renderUserBar, requireAuth, runWithButtonDisabled, urlFor } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
const groupId = getPositiveIntParam("group");
if (!groupId) { window.location.assign("/ui/groups/"); }

const currentUser = auth.user();
let isAdmin = false;

function noticeVisible(msg, type) {
  const el = byId("notice");
  el.textContent = msg;
  el.className = `notice ${type}`.trim();
  el.style.display = "";
}

function renderTopics(topics) {
  const list = byId("topics-list");
  if (!topics.length) { list.className = "empty-state"; list.textContent = "No hay temas aún. Agrega el primero arriba."; return; }
  list.className = "topics-list";
  list.innerHTML = topics.map((t) => {
    const videoLinks = t.video_id
      ? `<div class="topic-links">
           <a href="${urlFor("/ui/resumen/", { video: t.video_id })}" class="topic-link">Ver resumen</a>
           <a href="${urlFor("/ui/quiz/", { video: t.video_id })}" class="topic-link">Cuestionario</a>
         </div>`
      : `<p class="topic-no-video">Sin video asignado</p>`;
    const deleteBtn = isAdmin
      ? `<button class="topic-delete secondary" data-id="${t.id}" type="button" title="Eliminar tema">✕</button>`
      : "";
    return `<article class="topic-card">
      <div class="topic-head">
        <strong>${escapeHtml(t.title)}</strong>${deleteBtn}
      </div>
      ${t.description ? `<p class="topic-desc">${escapeHtml(t.description)}</p>` : ""}
      ${videoLinks}
    </article>`;
  }).join("");

  list.querySelectorAll(".topic-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este tema?")) return;
      try {
        await apiDeleteTopic(groupId, Number(btn.dataset.id));
        await loadTopics();
      } catch (err) { noticeVisible(err.message, "error"); }
    });
  });
}

async function loadTopics() {
  try { renderTopics(await apiListTopics(groupId)); }
  catch (err) { noticeVisible(err.message, "error"); }
}

async function init() {
  try {
    const group = await apiGetGroup(groupId);
    byId("group-title").textContent = group.name;
    isAdmin = currentUser && currentUser.id === group.admin_id;

    if (isAdmin) {
      byId("members-section").style.display = "";
      byId("topic-form").style.display = "";
    } else {
      byId("topic-form").style.display = "none";
    }

    await loadTopics();
  } catch (err) { noticeVisible(err.message, "error"); }
}

// --- Crear tema ---
byId("topic-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("topic-btn"), async () => {
    try {
      const videoId = Number(byId("topic-video").value) || null;
      await apiCreateTopic(groupId, byId("topic-title").value.trim(), byId("topic-desc").value.trim(), videoId);
      byId("topic-title").value = "";
      byId("topic-desc").value = "";
      byId("topic-video").value = "";
      await loadTopics();
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});

// --- Agregar miembro ---
byId("member-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("member-btn"), async () => {
    try {
      await apiAddMember(groupId, Number(byId("member-uid").value));
      byId("member-uid").value = "";
      noticeVisible("Miembro agregado.", "success");
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});

init();
