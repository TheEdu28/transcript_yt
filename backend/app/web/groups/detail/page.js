import {
  apiAddMember,
  apiCreateTopic,
  apiDeleteTopic,
  apiGetGroup,
  apiListGroupMembers,
  apiListMyVideos,
  apiListTopics,
  apiMe,
  apiRegenerateGroupCode,
  apiRemoveMember,
  auth,
} from "/ui/api.js";
import {
  escapeHtml,
  getPositiveIntParam,
  renderUserBar,
  requireAuth,
  runWithButtonDisabled,
  showNotice,
  urlFor,
} from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
const groupId = getPositiveIntParam("group");
if (!groupId) {
  window.location.assign("/ui/groups/");
}

const currentUser = auth.user();
let isAdmin = false;
let currentGroup = null;
let myVideos = [];
let selectedVideo = null;

function noticeVisible(msg, type = "info") {
  showNotice(msg, type);
}

function formatDuration(seconds) {
  if (!seconds) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

// --- Renderizar código del grupo ---
function renderGroupCode(code) {
  const codeTag = byId("group-code-tag");
  if (codeTag) codeTag.textContent = code;
}

// --- Renderizar selector de videos ---
function renderVideoPicker(videos) {
  const grid = byId("video-picker-grid");
  if (!grid) return;

  if (!videos || !videos.length) {
    grid.className = "empty-state";
    grid.innerHTML = "No tienes videos procesados aún. <a href='/ui/video/'>Procesar uno ahora</a>.";
    return;
  }

  grid.className = "video-picker-grid";
  grid.innerHTML = videos
    .map((v) => {
      const isSel = selectedVideo && selectedVideo.id === v.id;
      const thumbUrl = `https://img.youtube.com/vi/${v.youtube_id}/mqdefault.jpg`;
      const quizBadge = v.has_quiz
        ? `<span class="vid-badge vid-badge--quiz" style="font-size:9px">Quiz listo</span>`
        : `<span class="vid-badge" style="font-size:9px;background:#f1f5f9;color:#64748b">Sin quiz</span>`;

      return `
        <div class="video-picker-item ${isSel ? "selected" : ""}" data-video-id="${v.id}">
          <img class="video-picker-thumb" src="${thumbUrl}" alt="Miniatura" loading="lazy">
          <div class="video-picker-info">
            <div class="video-picker-title" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</div>
            <div class="video-picker-meta">ID: ${v.id} · ${formatDuration(v.duration_seconds)}</div>
            <div style="margin-top:4px">${quizBadge}</div>
          </div>
        </div>
      `;
    })
    .join("");

  grid.querySelectorAll(".video-picker-item").forEach((card) => {
    card.addEventListener("click", () => {
      const vidId = Number(card.dataset.videoId);
      const chosen = myVideos.find((v) => v.id === vidId);
      if (chosen) {
        selectVideoForTopic(chosen);
      }
    });
  });
}

function selectVideoForTopic(video) {
  selectedVideo = video;
  byId("topic-video").value = video.id;

  const preview = byId("selected-video-preview");
  const thumbUrl = `https://img.youtube.com/vi/${video.youtube_id}/mqdefault.jpg`;

  preview.style.display = "";
  preview.innerHTML = `
    <div class="selected-video-card">
      <img class="selected-video-thumb" src="${thumbUrl}" alt="Miniatura">
      <div style="flex:1;min-width:0">
        <strong style="font-size:13px;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(video.title)}</strong>
        <span style="font-size:12px;color:var(--muted)">Video #${video.id} · Duración: ${formatDuration(video.duration_seconds)}</span>
      </div>
      <button type="button" id="clear-selected-video-btn" class="secondary" style="font-size:12px;padding:4px 8px" title="Quitar video">✕</button>
    </div>
  `;

  byId("clear-selected-video-btn")?.addEventListener("click", () => {
    selectedVideo = null;
    byId("topic-video").value = "";
    preview.style.display = "none";
    preview.innerHTML = "";
    renderVideoPicker(myVideos);
  });

  // Auto-completar título si está vacío
  const titleInput = byId("topic-title");
  if (!titleInput.value.trim()) {
    titleInput.value = video.title;
  }

  // Ocultar desplegable
  byId("video-picker-container").style.display = "none";
  renderVideoPicker(myVideos);
}

// --- Renderizar temas ---
function renderTopics(topics) {
  const list = byId("topics-list");
  if (!topics.length) {
    list.className = "empty-state";
    list.textContent = "No hay temas aún. " + (isAdmin ? "Publica el primero arriba." : "El docente aún no ha publicado actividades.");
    return;
  }

  list.className = "topics-list";
  list.innerHTML = topics
    .map((t) => {
      const videoLinks = t.video_id
        ? `<div class="topic-links">
             <a href="${urlFor("/ui/resumen/", { video: t.video_id })}" class="topic-link">📖 Ver resumen didáctico</a>
             <a href="${urlFor("/ui/quiz/", { video: t.video_id })}" class="topic-link">✍ Realizar cuestionario</a>
           </div>`
        : `<p class="topic-no-video">Sin video asignado</p>`;

      const deleteBtn = isAdmin
        ? `<button class="topic-delete secondary" data-id="${t.id}" type="button" title="Eliminar tema">✕</button>`
        : "";

      return `
        <article class="topic-card" style="padding:16px;border:1px solid var(--line);border-radius:12px;margin-bottom:12px;background:#fff">
          <div class="topic-head" style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <strong style="font-size:16px">${escapeHtml(t.title)}</strong>
              ${t.created_at ? `<span style="display:block;font-size:11px;color:var(--muted);margin-top:2px">Publicado: ${new Date(t.created_at).toLocaleDateString("es")}</span>` : ""}
            </div>
            ${deleteBtn}
          </div>
          ${t.description ? `<p class="topic-desc" style="margin:8px 0">${escapeHtml(t.description)}</p>` : ""}
          ${videoLinks}
        </article>
      `;
    })
    .join("");

  list.querySelectorAll(".topic-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este tema del grupo?")) return;
      try {
        await apiDeleteTopic(groupId, Number(btn.dataset.id));
        noticeVisible("Tema eliminado.", "success");
        await loadTopics();
      } catch (err) {
        noticeVisible(err.message, "error");
      }
    });
  });
}

async function loadTopics() {
  try {
    const topics = await apiListTopics(groupId);
    renderTopics(topics);
  } catch (err) {
    noticeVisible(err.message, "error");
  }
}

// --- Renderizar miembros ---
function renderMembers(members) {
  const container = byId("members-table-container");
  if (!members || !members.length) {
    container.innerHTML = `<div class="empty-state">No hay miembros registrados en este grupo.</div>`;
    return;
  }

  const rows = members
    .map((m) => {
      const isAdm = m.is_admin;
      const roleBadge = isAdm
        ? `<span class="member-role-badge member-role-badge--admin">Admin</span>`
        : `<span class="member-role-badge member-role-badge--member">Miembro</span>`;

      const removeBtn = isAdmin && !isAdm
        ? `<button class="topic-delete secondary member-remove-btn" data-uid="${m.user_id}" type="button" title="Expulsar del grupo">✕</button>`
        : "";

      return `
        <tr>
          <td><strong>${escapeHtml(m.nombre)}</strong></td>
          <td>${escapeHtml(m.email)}</td>
          <td>${roleBadge}</td>
          <td>${m.joined_at ? new Date(m.joined_at).toLocaleDateString("es") : "—"}</td>
          <td style="text-align:right">${removeBtn}</td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = `
    <table class="members-table">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Correo</th>
          <th>Rol</th>
          <th>Fecha unión</th>
          <th style="text-align:right">Acción</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;

  container.querySelectorAll(".member-remove-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const uid = Number(btn.dataset.uid);
      if (!confirm("¿Deseas expulsar a este usuario del grupo?")) return;
      try {
        await apiRemoveMember(groupId, uid);
        noticeVisible("Miembro removido.", "success");
        await loadMembers();
      } catch (err) {
        noticeVisible(err.message, "error");
      }
    });
  });
}

async function loadMembers() {
  try {
    const members = await apiListGroupMembers(groupId);
    renderMembers(members);
  } catch (err) {
    console.warn("No se pudieron cargar miembros:", err);
  }
}

// --- Inicialización de página ---
async function init() {
  try {
    currentGroup = await apiGetGroup(groupId);
    byId("group-title").textContent = currentGroup.name;
    renderGroupCode(currentGroup.code);

    let me = currentUser;
    try {
      const freshMe = await apiMe();
      if (freshMe && freshMe.id) {
        me = freshMe;
        auth.save(auth.token(), freshMe);
      }
    } catch {
      // Usar currentUser ya presente en memoria
    }

    isAdmin = Boolean(me && currentGroup && Number(me.id) === Number(currentGroup.admin_id));

    if (isAdmin) {
      byId("topic-form").style.display = "";
      byId("admin-member-box").style.display = "";
      byId("regen-code-btn").style.display = "";

      // Cargar videos del admin para el selector
      try {
        const res = await apiListMyVideos(1, 50);
        myVideos = res.items || [];
        renderVideoPicker(myVideos);
      } catch (err) {
        console.warn("No se pudo cargar el historial de videos:", err);
      }
    } else {
      byId("topic-form").style.display = "none";
      byId("admin-member-box").style.display = "none";
      byId("regen-code-btn").style.display = "none";
    }

    await loadTopics();
    await loadMembers();
  } catch (err) {
    noticeVisible(err.message, "error");
  }
}

// --- Toggle selector de videos ---
byId("toggle-video-picker-btn")?.addEventListener("click", async () => {
  const container = byId("video-picker-container");
  const isHidden = container.style.display === "none";
  if (isHidden) {
    container.style.display = "";
    if (!myVideos || !myVideos.length) {
      try {
        const res = await apiListMyVideos(1, 50);
        myVideos = res.items || [];
        renderVideoPicker(myVideos);
      } catch (err) {
        console.warn("Error cargando videos al desplegar:", err);
      }
    }
  } else {
    container.style.display = "none";
  }
});

// --- Copiar código de grupo ---
byId("copy-code-btn")?.addEventListener("click", () => {
  if (!currentGroup?.code) return;
  const text = currentGroup.code;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(
      () => noticeVisible(`¡Código ${text} copiado al portapapeles!`, "success"),
      () => noticeVisible(`Código de acceso: ${text}`, "info")
    );
  } else {
    try {
      const tempInput = document.createElement("input");
      tempInput.value = text;
      document.body.appendChild(tempInput);
      tempInput.select();
      document.execCommand("copy");
      tempInput.remove();
      noticeVisible(`¡Código ${text} copiado!`, "success");
    } catch {
      noticeVisible(`Código de acceso: ${text}`, "info");
    }
  }
});

// --- Regenerar código de grupo ---
byId("regen-code-btn")?.addEventListener("click", async () => {
  if (!confirm("¿Regenerar el código de este grupo? El código anterior dejará de ser válido.")) return;
  await runWithButtonDisabled(byId("regen-code-btn"), async () => {
    try {
      const updated = await apiRegenerateGroupCode(groupId);
      currentGroup = updated;
      renderGroupCode(updated.code);
      noticeVisible(`Nuevo código generado: ${updated.code}`, "success");
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

// --- Crear tema ---
byId("topic-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("topic-btn"), async () => {
    try {
      const title = byId("topic-title").value.trim();
      const desc = byId("topic-desc").value.trim();
      const videoId = Number(byId("topic-video").value) || null;

      await apiCreateTopic(groupId, title, desc, videoId);

      // Limpiar formulario
      byId("topic-title").value = "";
      byId("topic-desc").value = "";
      byId("topic-video").value = "";
      selectedVideo = null;
      byId("selected-video-preview").style.display = "none";
      byId("selected-video-preview").innerHTML = "";

      noticeVisible("Tema publicado exitosamente en el grupo.", "success");
      await loadTopics();
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

// --- Agregar miembro manual (admin) ---
byId("member-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("member-btn"), async () => {
    try {
      const uid = Number(byId("member-uid").value);
      if (!uid) return;
      await apiAddMember(groupId, uid);
      byId("member-uid").value = "";
      noticeVisible("Miembro incorporado al grupo.", "success");
      await loadMembers();
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

init();
