import {
  apiAddMember,
  apiCreateTopic,
  apiDeleteTopic,
  apiGetAllTopicAttempts,
  apiGetGroup,
  apiGetGroupGrades,
  apiGetMyTopicAttempts,
  apiListGroupMembers,
  apiListMyVideos,
  apiListTopics,
  apiMe,
  apiRegenerateGroupCode,
  apiRemoveMember,
  apiUpdateAttemptGrade,
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
let currentTab = "topics";
let cachedTopics = [];

function noticeVisible(msg, type = "info") {
  showNotice(msg, type);
}

function formatDuration(seconds) {
  if (!seconds) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

// ==========================================
// --- Gestión de Pestañas (Tabs) ---
// ==========================================
function switchGroupTab(tabName) {
  currentTab = tabName;
  const tabs = ["topics", "members", "grades"];
  tabs.forEach((t) => {
    const section = byId(`tab-${t}`);
    const btn = document.querySelector(`.group-tab-btn[data-tab='${t}']`);
    if (section) section.style.display = t === tabName ? "" : "none";
    if (btn) {
      if (t === tabName) {
        btn.classList.add("active");
        btn.style.color = "var(--ink)";
        btn.style.borderBottom = "3px solid var(--blue)";
      } else {
        btn.classList.remove("active");
        btn.style.color = "var(--muted)";
        btn.style.borderBottom = "3px solid transparent";
      }
    }
  });

  if (tabName === "topics") loadTopics();
  else if (tabName === "members") loadMembers();
  else if (tabName === "grades") loadGrades();
}

document.querySelectorAll(".group-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    switchGroupTab(btn.dataset.tab);
  });
});

// ==========================================
// --- Código de Acceso ---
// ==========================================
function renderGroupCode(code) {
  const codeTag = byId("group-code-tag");
  if (codeTag) codeTag.textContent = code;
}

// ==========================================
// --- Selector Visual de Videos (Admin) ---
// ==========================================
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

  const titleInput = byId("topic-title");
  if (!titleInput.value.trim()) {
    titleInput.value = video.title;
  }

  byId("video-picker-container").style.display = "none";
  renderVideoPicker(myVideos);
}

// ==========================================
// --- PESTAÑA: TEMAS ---
// ==========================================
function renderTopics(topics) {
  cachedTopics = topics;
  const list = byId("topics-list");
  if (!topics.length) {
    list.className = "empty-state";
    list.textContent = "No hay temas aún. " + (isAdmin ? "Haz clic en «+ Nuevo tema» para publicar el primero." : "El docente aún no ha publicado actividades en este grupo.");
    return;
  }

  list.className = "topics-list";
  list.innerHTML = topics
    .map((t) => {
      // Pasamos group_id y topic_id además de video_id y material_id
      const resumenParams = { group: groupId, topic: t.id };
      const quizParams = { group: groupId, topic: t.id };
      if (t.video_id) {
        resumenParams.video = t.video_id;
        quizParams.video = t.video_id;
      }
      if (t.summary_id) resumenParams.material = t.summary_id;
      const quizId = t.quiz_id || t.material_id;
      if (quizId) quizParams.material = quizId;

      const videoLinks = t.video_id
        ? `<div class="topic-links" style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
             <a href="${urlFor("/ui/resumen/", resumenParams)}" class="topic-link" style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:#f0f5ff;border:1px solid #c9d5fa;border-radius:8px;font-size:13px;font-weight:700;color:var(--blue);text-decoration:none">
               📖 Resumen didáctico ${t.summary_id ? '✓' : ''}
             </a>
             <a href="${urlFor("/ui/quiz/", quizParams)}" class="topic-link" style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:#f5f0ff;border:1px solid #d8c9fa;border-radius:8px;font-size:13px;font-weight:700;color:var(--violet);text-decoration:none">
               ✍ Realizar evaluación ${quizId ? '✓' : ''}
             </a>
           </div>`
        : `<p class="topic-no-video" style="margin:10px 0 0;font-size:12px;color:var(--muted)">Sin video asignado</p>`;

      const deleteBtn = isAdmin
        ? `<button class="topic-delete secondary" data-id="${t.id}" type="button" title="Eliminar tema" style="color:var(--red);border-color:#fca5a5;padding:4px 8px;font-size:12px">🗑 Eliminar</button>`
        : "";

      return `
        <article class="topic-card" style="padding:18px;border:1px solid var(--line);border-radius:12px;margin-bottom:12px;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,0.02)">
          <div class="topic-head" style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
            <div style="flex:1">
              <strong style="font-size:16px;color:var(--ink)">${escapeHtml(t.title)}</strong>
              ${t.created_at ? `<span style="display:block;font-size:12px;color:var(--muted);margin-top:3px">Publicado: ${new Date(t.created_at).toLocaleDateString("es")}</span>` : ""}
            </div>
            ${deleteBtn}
          </div>
          ${t.description ? `<p class="topic-desc" style="margin:10px 0 6px;color:#475569;font-size:13px;line-height:1.5">${escapeHtml(t.description)}</p>` : ""}
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

// Toggle formulario "Nuevo tema"
function openTopicForm() {
  byId("topic-form").style.display = "";
  byId("toggle-new-topic-btn").style.display = "none";
  byId("topic-title").focus();
}

function closeTopicForm() {
  byId("topic-form").style.display = "none";
  if (isAdmin) byId("toggle-new-topic-btn").style.display = "";
  byId("topic-title").value = "";
  byId("topic-desc").value = "";
  byId("topic-video").value = "";
  selectedVideo = null;
  byId("selected-video-preview").style.display = "none";
  byId("selected-video-preview").innerHTML = "";
  byId("video-picker-container").style.display = "none";
}

byId("toggle-new-topic-btn")?.addEventListener("click", openTopicForm);
byId("cancel-topic-btn")?.addEventListener("click", closeTopicForm);
byId("cancel-topic-btn-2")?.addEventListener("click", closeTopicForm);

// ==========================================
// --- PESTAÑA: MIEMBROS ---
// ==========================================
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
        ? `<button class="topic-delete secondary member-remove-btn" data-uid="${m.user_id}" type="button" title="Expulsar del grupo" style="color:var(--red);border-color:#fca5a5;padding:3px 8px;font-size:12px">Expulsar</button>`
        : "—";

      return `
        <tr>
          <td>
            <strong>${escapeHtml(m.nombre)}</strong>
            <span style="display:block;font-size:11px;color:var(--muted)">ID: ${m.user_id}</span>
          </td>
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

// ==========================================
// --- PESTAÑA: CALIFICACIONES (Gradebook) ---
// ==========================================
async function loadGrades() {
  const container = byId("grades-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state">Consultando calificaciones…</div>`;

  try {
    const data = await apiGetGroupGrades(groupId);
    renderGrades(data);
  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="color:var(--red)">Error al cargar calificaciones: ${escapeHtml(err.message)}</div>`;
  }
}

function renderGrades(data) {
  const container = byId("grades-container");
  if (!container) return;

  const topics = data.topics || [];
  const members = data.members || [];

  if (!topics.length) {
    container.innerHTML = `<div class="empty-state">Aún no hay temas creados en este grupo para evaluar.</div>`;
    return;
  }

  if (isAdmin) {
    // Vista Administrador: Tabla de calificaciones general
    if (!members.length) {
      container.innerHTML = `<div class="empty-state">No hay miembros en el grupo para mostrar calificaciones.</div>`;
      return;
    }

    const headerThs = topics
      .map((t) => `<th style="text-align:center" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</th>`)
      .join("");

    const rows = members
      .map((m) => {
        const topicTds = topics
          .map((t) => {
            const gradeInfo = m.topic_grades[t.id];
            if (!gradeInfo || !gradeInfo.submitted) {
              return `<td style="text-align:center;color:var(--muted)"><em>Pendiente</em></td>`;
            }

            const scoreDisplay = gradeInfo.final_score !== null ? gradeInfo.final_score.toFixed(1) : (gradeInfo.raw_score !== null ? gradeInfo.raw_score.toFixed(1) : "—");
            const isReviewed = gradeInfo.review_notes || (gradeInfo.final_score !== null && gradeInfo.final_score !== gradeInfo.raw_score);
            const badgeClass = isReviewed ? "background:#eff6ff;color:var(--blue)" : "background:#f0fdf4;color:#16a34a";

            return `
              <td style="text-align:center">
                <button type="button" class="secondary review-grade-btn" 
                        data-topic-id="${t.id}" 
                        data-topic-title="${escapeHtml(t.title)}"
                        data-member-id="${m.user_id}"
                        data-member-name="${escapeHtml(m.nombre)}"
                        data-attempt-id="${gradeInfo.attempt_id}"
                        data-raw-score="${gradeInfo.raw_score ?? ''}"
                        data-final-score="${gradeInfo.final_score ?? ''}"
                        data-notes="${escapeHtml(gradeInfo.review_notes || '')}"
                        style="padding:4px 8px;font-size:12px;border-radius:6px;${badgeClass}">
                  ${scoreDisplay} / 100 ${isReviewed ? '✎' : ''}
                </button>
              </td>
            `;
          })
          .join("");

        const avg = m.average_score !== null ? `${m.average_score.toFixed(1)} / 100` : "—";

        return `
          <tr>
            <td>
              <strong>${escapeHtml(m.nombre)}</strong>
              <span style="display:block;font-size:11px;color:var(--muted)">${escapeHtml(m.email)}</span>
            </td>
            ${topicTds}
            <td style="text-align:center"><strong>${m.completed_topics}/${topics.length}</strong></td>
            <td style="text-align:center;font-weight:700;color:var(--blue)">${avg}</td>
          </tr>
        `;
      })
      .join("");

    container.innerHTML = `
      <div style="overflow-x:auto">
        <table class="members-table" style="min-width:600px">
          <thead>
            <tr>
              <th>Estudiante / Miembro</th>
              ${headerThs}
              <th style="text-align:center">Progreso</th>
              <th style="text-align:center">Promedio</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
      <p style="font-size:12px;color:var(--muted);margin-top:12px">
        💡 <em>Haz clic en la calificación de un estudiante para abrir el modal de revisión y ajustar su nota final o dejar retroalimentación docente.</em>
      </p>
    `;

    container.querySelectorAll(".review-grade-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        openGradeReviewModal({
          topicId: Number(btn.dataset.topicId),
          topicTitle: btn.dataset.topicTitle,
          memberId: Number(btn.dataset.memberId),
          memberName: btn.dataset.memberName,
          attemptId: Number(btn.dataset.attemptId),
          rawScore: btn.dataset.rawScore !== "" ? Number(btn.dataset.rawScore) : null,
          finalScore: btn.dataset.finalScore !== "" ? Number(btn.dataset.finalScore) : null,
          reviewNotes: btn.dataset.notes,
        });
      });
    });

  } else {
    // Vista Estudiante: Tarjetas de sus propios temas e intentos
    const mySummary = members[0];
    if (!mySummary) {
      container.innerHTML = `<div class="empty-state">No se encontró información académica para tu usuario.</div>`;
      return;
    }

    const cards = topics
      .map((t) => {
        const gradeInfo = mySummary.topic_grades[t.id];
        const submitted = gradeInfo && gradeInfo.submitted;
        const score = submitted ? (gradeInfo.final_score !== null ? gradeInfo.final_score.toFixed(1) : gradeInfo.raw_score.toFixed(1)) : null;

        const actionBtn = submitted
          ? `<span style="font-size:12px;font-weight:700;color:#16a34a;background:#ecfaf5;padding:4px 10px;border-radius:99px">✓ Realizado (${gradeInfo.attempts_count} intento${gradeInfo.attempts_count > 1 ? 's' : ''})</span>`
          : `<a href="${urlFor('/ui/quiz/', { group: groupId, topic: t.id, video: t.video_id, material: t.quiz_id || t.material_id })}" class="primary-action" style="margin:0;padding:6px 14px;font-size:12px">Tomar cuestionario →</a>`;

        return `
          <div style="border:1px solid var(--line);border-radius:12px;padding:16px;background:#fff;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:10px">
            <div style="flex:1;min-width:220px">
              <strong style="font-size:15px;color:var(--ink)">${escapeHtml(t.title)}</strong>
              ${t.description ? `<p style="margin:4px 0 0;font-size:12px;color:var(--muted)">${escapeHtml(t.description)}</p>` : ''}
              ${gradeInfo?.review_notes ? `<p style="margin:6px 0 0;font-size:12px;color:var(--blue);background:#eff6ff;padding:6px 10px;border-radius:6px"><strong>Comentario del docente:</strong> ${escapeHtml(gradeInfo.review_notes)}</p>` : ''}
            </div>
            <div style="display:flex;align-items:center;gap:16px">
              <div style="text-align:right">
                <span style="font-size:11px;color:var(--muted);display:block">Calificación</span>
                <strong style="font-size:18px;color:${submitted ? 'var(--blue)' : 'var(--muted)'}">
                  ${submitted ? `${score} / 100` : 'Sin rendir'}
                </strong>
              </div>
              <div>${actionBtn}</div>
            </div>
          </div>
        `;
      })
      .join("");

    const avg = mySummary.average_score !== null ? `${mySummary.average_score.toFixed(1)} / 100` : "Sin calificaciones aún";

    container.innerHTML = `
      <div style="background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <span style="font-size:12px;color:var(--muted);display:block">Progreso del grupo</span>
          <strong style="font-size:16px">${mySummary.completed_topics} de ${topics.length} temas completados</strong>
        </div>
        <div>
          <span style="font-size:12px;color:var(--muted);display:block">Promedio acumulado</span>
          <strong style="font-size:20px;color:var(--blue)">${avg}</strong>
        </div>
      </div>
      <div>
        ${cards}
      </div>
    `;
  }
}

// Modal de revisión manual (Admin)
let activeReviewData = null;

function openGradeReviewModal(data) {
  activeReviewData = data;
  const modal = byId("grade-review-modal");
  byId("grade-modal-subtitle").textContent = `Estudiante: ${data.memberName} · Tema: ${data.topicTitle}`;
  byId("grade-modal-attempt-info").innerHTML = `
    <strong>Intento #${data.attemptId}</strong><br>
    Nota evaluada automáticamente por RAG: <strong>${data.rawScore !== null ? data.rawScore.toFixed(1) : '—'} / 100</strong><br>
    Nota actual: <strong>${data.finalScore !== null ? data.finalScore.toFixed(1) : (data.rawScore !== null ? data.rawScore.toFixed(1) : '—')} / 100</strong>
  `;
  byId("grade-modal-score").value = data.finalScore !== null ? data.finalScore : (data.rawScore ?? 100);
  byId("grade-modal-notes").value = data.reviewNotes || "";
  modal.style.display = "grid";
}

byId("grade-modal-cancel")?.addEventListener("click", () => {
  byId("grade-review-modal").style.display = "none";
  activeReviewData = null;
});

byId("grade-modal-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!activeReviewData) return;
  const submitBtn = byId("grade-modal-submit");
  await runWithButtonDisabled(submitBtn, async () => {
    try {
      const score = Number(byId("grade-modal-score").value);
      const notes = byId("grade-modal-notes").value.trim() || null;
      await apiUpdateAttemptGrade(groupId, activeReviewData.topicId, activeReviewData.attemptId, score, notes);
      noticeVisible("Calificación actualizada con éxito.", "success");
      byId("grade-review-modal").style.display = "none";
      await loadGrades();
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

byId("refresh-grades-btn")?.addEventListener("click", loadGrades);

// ==========================================
// --- Inicialización de página ---
// ==========================================
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
      // Usar currentUser ya presente
    }

    isAdmin = Boolean(me && currentGroup && Number(me.id) === Number(currentGroup.admin_id));

    if (isAdmin) {
      byId("toggle-new-topic-btn").style.display = "";
      byId("admin-member-box").style.display = "";
      byId("regen-code-btn").style.display = "";

      try {
        const res = await apiListMyVideos(1, 50);
        myVideos = res.items || [];
        renderVideoPicker(myVideos);
      } catch (err) {
        console.warn("No se pudo cargar el historial de videos:", err);
      }
    } else {
      byId("toggle-new-topic-btn").style.display = "none";
      byId("admin-member-box").style.display = "none";
      byId("regen-code-btn").style.display = "none";
    }

    // Inicializar pestaña activa
    switchGroupTab("topics");
  } catch (err) {
    noticeVisible(err.message, "error");
    const main = document.querySelector("main") || document.body;
    if (main) {
      main.innerHTML = `
        <div style="max-width:550px;margin:40px auto;padding:28px;background:#fff;border:1px solid var(--line);border-radius:14px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,0.04)">
          <div style="font-size:42px;margin-bottom:12px">🔒</div>
          <h2 style="font-size:20px;margin:0 0 10px;color:var(--ink)">Acceso restringido a este grupo</h2>
          <p style="color:var(--muted);font-size:14px;line-height:1.5;margin-bottom:24px">
            ${escapeHtml(err.message || "Debes pertenecer al grupo para consultar sus actividades y materiales.")}
          </p>
          <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
            <a href="/ui/groups/" class="primary-action" style="margin:0;padding:8px 20px">Ir a Mis Grupos / Unirme con Código</a>
          </div>
        </div>
      `;
    }
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

      closeTopicForm();
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
