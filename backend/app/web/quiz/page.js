import { apiGetTopicMaterials, apiGetVideo, apiListMyVideos, apiSubmitAttempt, auth, fetchModels, request } from "/ui/api.js";
import {
  escapeHtml,
  getPositiveIntParam,
  initModelSelector,
  renderUserBar,
  requireAuth,
  replaceUrl,
  runWithButtonDisabled,
  showNotice,
  urlFor,
} from "/ui/shared.js";

const byId = (id) => document.getElementById(id);
requireAuth();
renderUserBar();

let videoId = getPositiveIntParam("video");
let materialId = getPositiveIntParam("material");
let groupId = getPositiveIntParam("group");
let topicId = getPositiveIntParam("topic");
let activeMaterialId = materialId;

// Estado del tema y roles
let topicData = null;
let isAdmin = false;
let currentMode = "shared"; // "shared" (profesor) | "personal" (propios) | "standalone"
let personalQuizzes = [];
let sharedQuiz = null;

const selectedBloomLevels = () =>
  [...document.querySelectorAll(".bloom-options input:checked")].map((input) => input.value);

const modelSelector = initModelSelector("model-selector-container", fetchModels);

let ytPlayer = null;
let isPlayerReady = false;

function parseTimestampToSeconds(hhmmss) {
  if (!hhmmss) return 0;
  const parts = hhmmss.trim().split(":").map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return Number(parts[0]) || 0;
}

function seekToTimestamp(timestampStr) {
  const secs = parseTimestampToSeconds(timestampStr);
  if (ytPlayer && isPlayerReady && ytPlayer.seekTo) {
    ytPlayer.seekTo(secs, true);
    ytPlayer.playVideo();
    byId("player-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } else {
    showNotice(`Cargando reproductor (segundo ${secs})...`, "info");
  }
}

function initYouTubePlayer(youtubeId, videoTitle = "") {
  const panel = byId("player-panel");
  if (!panel || !youtubeId) return;
  panel.style.display = "";

  if (videoTitle && byId("player-video-title")) {
    byId("player-video-title").textContent = `Video: ${videoTitle}`;
  }

  const createPlayer = () => {
    if (ytPlayer && ytPlayer.loadVideoById) {
      ytPlayer.loadVideoById(youtubeId);
      return;
    }
    try {
      ytPlayer = new window.YT.Player("yt-player", {
        videoId: youtubeId,
        playerVars: { playsinline: 1, rel: 0, modestbranding: 1 },
        events: {
          onReady: () => {
            isPlayerReady = true;
          },
        },
      });
    } catch (e) {
      console.warn("Error creando reproductor en quiz:", e);
    }
  };

  if (window.YT && window.YT.Player) {
    createPlayer();
  } else {
    window.onYouTubeIframeAPIReady = () => createPlayer();
    if (!document.getElementById("yt-iframe-api")) {
      const tag = document.createElement("script");
      tag.id = "yt-iframe-api";
      tag.src = "https://www.youtube.com/iframe_api";
      const first = document.getElementsByTagName("script")[0];
      first.parentNode.insertBefore(tag, first);
    }
  }
}

function updateExportVisibility(matId) {
  activeMaterialId = matId;
  const bar = byId("quiz-export-actions");
  if (bar) {
    bar.style.display = matId ? "flex" : "none";
  }
}

// =============================================================================
// Renderizado de Cuestionario para ESTUDIANTE (Solo responder)
// =============================================================================
function renderQuizForStudent(quiz, isPersonal = false) {
  const multiple = (quiz.multiple_choice || [])
    .map(
      (question, index) => `
      <article class="question">
        <div class="question-head">
          <strong>${index + 1}. ${escapeHtml(question.question)}</strong>
          <span class="badge">${question.bloom_level}</span>
        </div>
        <div class="options">
          ${(question.options || [])
            .map(
              (option, optionIndex) =>
                `<label><input type="radio" name="multiple-${index}" value="${optionIndex}">${escapeHtml(option)}</label>`
            )
            .join("")}
        </div>
        <div style="margin-top:8px">
          <button type="button" class="timestamp quiz-ts-btn" data-ts="${escapeHtml(question.evidence_timestamp)}">
            <svg class="ui-icon" style="width:0.95em;height:0.95em" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> Evidencia: ${escapeHtml(question.evidence_timestamp)}
          </button>
        </div>
      </article>`
    )
    .join("");

  const open = (quiz.open_questions || [])
    .map(
      (question, index) => `
      <article class="question">
        <div class="question-head">
          <strong>Abierta ${index + 1}. ${escapeHtml(question.question)}</strong>
          <span class="badge">${question.bloom_level}</span>
        </div>
        <label class="open-answer">Tu respuesta
          <textarea id="open-${index}" rows="3" placeholder="Explica con tus palabras..."></textarea>
        </label>
        <div style="margin-top:8px">
          <button type="button" class="timestamp quiz-ts-btn" data-ts="${escapeHtml(question.evidence_timestamp)}">
            <svg class="ui-icon" style="width:0.95em;height:0.95em" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> Evidencia: ${escapeHtml(question.evidence_timestamp)}
          </button>
        </div>
      </article>`
    )
    .join("");

  const out = byId("quiz-output");
  out.className = "";
  out.innerHTML = `${multiple}<h3>Preguntas abiertas</h3>${open || "<p>Este cuestionario no contiene preguntas abiertas.</p>"}`;

  out.querySelectorAll(".quiz-ts-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      seekToTimestamp(btn.dataset.ts);
    });
  });

  const fbBtn = byId("feedback-button");
  fbBtn.style.display = "";
  fbBtn.disabled = false;
  fbBtn.textContent = isPersonal ? "Revisar respuestas (Práctica)" : "Revisar respuestas";

  byId("feedback-output").innerHTML = "";

  if (activeMaterialId) updateExportVisibility(activeMaterialId);
}

// =============================================================================
// Renderizado de Cuestionario para ADMINISTRADOR / PROFESOR
// (Solo lectura con respuestas correctas y explicaciones)
// =============================================================================
function renderQuizForAdmin(quiz) {
  const checkIcon = `<svg class="ui-icon" style="color:#059669;width:1.1em;height:1.1em" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>`;

  const multiple = (quiz.multiple_choice || [])
    .map((question, index) => {
      const correctIdx = question.correct_option;
      const optionsHtml = (question.options || [])
        .map((option, optIdx) => {
          const isCorrect = optIdx === correctIdx;
          const letter = String.fromCharCode(65 + optIdx);
          if (isCorrect) {
            return `
              <div style="padding:10px 14px;border:2px solid #10b981;border-radius:9px;background:#ecfdf5;display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                <span style="font-weight:700;color:#065f46">${letter}) ${escapeHtml(option)}</span>
                <span style="display:inline-flex;align-items:center;gap:4px;background:#10b981;color:#fff;font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px">
                  ${checkIcon} Respuesta correcta
                </span>
              </div>
            `;
          }
          return `
            <div style="padding:8px 14px;border:1px solid #e2e8f0;border-radius:9px;background:#f8fafc;color:#475569;margin-bottom:6px;font-size:13px">
              ${letter}) ${escapeHtml(option)}
            </div>
          `;
        })
        .join("");

      return `
        <article class="question" style="border:1px solid #c9d5fa;background:#fff;border-radius:12px;padding:18px;margin-bottom:16px">
          <div class="question-head">
            <strong style="font-size:15px;color:var(--ink)">${index + 1}. ${escapeHtml(question.question)}</strong>
            <span class="badge">${question.bloom_level}</span>
          </div>
          <div style="margin:12px 0 8px">
            ${optionsHtml}
          </div>
          ${
            question.explanation
              ? `<div style="background:#f0f7ff;border-left:3px solid var(--blue);padding:8px 12px;border-radius:6px;font-size:12px;color:#1e3a8a;margin-top:8px">
                  <strong>Explicación docente:</strong> ${escapeHtml(question.explanation)}
                </div>`
              : ""
          }
          <div style="margin-top:10px">
            <button type="button" class="timestamp quiz-ts-btn" data-ts="${escapeHtml(question.evidence_timestamp)}">
              <svg class="ui-icon" style="width:0.95em;height:0.95em" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> Evidencia RAG: ${escapeHtml(question.evidence_timestamp)}
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  const open = (quiz.open_questions || [])
    .map((question, index) => {
      const expectedList = (question.expected_points || [])
        .map((p) => `<li>${escapeHtml(p)}</li>`)
        .join("");

      return `
        <article class="question" style="border:1px solid #d8c9fa;background:#fff;border-radius:12px;padding:18px;margin-bottom:16px">
          <div class="question-head">
            <strong style="font-size:15px;color:var(--ink)">Abierta ${index + 1}. ${escapeHtml(question.question)}</strong>
            <span class="badge">${question.bloom_level}</span>
          </div>
          <div style="background:#faf5ff;border-left:3px solid var(--violet);padding:10px 14px;border-radius:8px;margin-top:12px;font-size:13px;color:#4c1d95">
            <strong>Puntos clave / Criterios de evaluación esperados:</strong>
            <ul style="margin:6px 0 0;padding-left:20px;line-height:1.5">
              ${expectedList || "<li>Criterio libre según el video.</li>"}
            </ul>
          </div>
          <div style="margin-top:10px">
            <button type="button" class="timestamp quiz-ts-btn" data-ts="${escapeHtml(question.evidence_timestamp)}">
              <svg class="ui-icon" style="width:0.95em;height:0.95em" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> Evidencia RAG: ${escapeHtml(question.evidence_timestamp)}
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  const out = byId("quiz-output");
  out.className = "";
  out.innerHTML = `
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:#1e40af;display:flex;align-items:center;gap:10px">
      <svg class="ui-icon" style="width:20px;height:20px;color:var(--blue);flex-shrink:0" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      <div>
        <strong>Modo Docente / Administrador:</strong> Esta pauta incluye las respuestas correctas, explicaciones y puntos esperados. Como administrador no rindes ni calificas este cuestionario.
      </div>
    </div>
    ${multiple}
    <h3 style="margin:20px 0 12px;font-size:18px">Preguntas abiertas</h3>
    ${open || "<p>Este cuestionario no contiene preguntas abiertas.</p>"}
  `;

  out.querySelectorAll(".quiz-ts-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      seekToTimestamp(btn.dataset.ts);
    });
  });

  // El administrador NO rinde ni califica el cuestionario
  byId("feedback-button").style.display = "none";
  byId("feedback-output").innerHTML = "";

  if (activeMaterialId) updateExportVisibility(activeMaterialId);
}

// Despachador de renderizado
function renderQuiz(quiz) {
  if (isAdmin) {
    renderQuizForAdmin(quiz);
  } else {
    renderQuizForStudent(quiz, currentMode === "personal");
  }
}

async function loadStoredQuiz(id) {
  const material = await request(`/materials/${id}`);
  if (material.material_type !== "quiz") throw new Error("El material indicado no es un cuestionario.");
  activeMaterialId = id;
  renderQuiz(material.content);
  updateExportVisibility(id);

  if (material.video_id) {
    videoId = material.video_id;
    byId("video-label").textContent = `Video ID: ${material.video_id}`;
    const pageParams = { video: material.video_id, material: material.id };
    if (groupId) pageParams.group = groupId;
    if (topicId) pageParams.topic = topicId;
    byId("summary-link").href = urlFor("/ui/resumen/", pageParams);
    byId("material-link").href = urlFor("/ui/material/", { video: material.video_id, material: material.id });
    replaceUrl("/ui/quiz/", pageParams);
    loadVideoPlayer(material.video_id);
  }
}

async function loadVideoPlayer(vidId) {
  try {
    const video = await apiGetVideo(vidId);
    if (video?.title) byId("video-label").textContent = `${video.title} (ID: ${vidId})`;
    if (video?.youtube_id) initYouTubePlayer(video.youtube_id, video.title || "");
  } catch (err) {
    console.warn("No se pudo cargar video para reproductor:", err);
  }
}

// =============================================================================
// Exportación con opción: Solo preguntas vs Preguntas y respuestas
// =============================================================================
function setupExportHandlers() {
  const triggerExport = async (format) => {
    if (!activeMaterialId) {
      showNotice("Primero debes generar o cargar un cuestionario.", "error");
      return;
    }
    const includeAnswers = byId("export-mode-select")?.value === "true";
    const modeLabel = includeAnswers ? "con respuestas" : "solo preguntas";
    showNotice(`Generando archivo ${format.toUpperCase()} (${modeLabel})…`, "info");
    try {
      const token = auth.token();
      const headers = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(
        `/api/v1/materials/${activeMaterialId}/export?format=${format}&include_answers=${includeAnswers}`,
        { headers }
      );
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail?.message || `Error al exportar (${res.status})`);
      }

      const blob = await res.blob();
      const extMap = { markdown: "md", pdf: "pdf", docx: "docx" };
      const suffix = includeAnswers ? "_con_respuestas" : "_preguntas";
      const filename = `cuestionario_${activeMaterialId}${suffix}.${extMap[format] || format}`;

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      showNotice(`Archivo ${filename} descargado con éxito.`, "success");
    } catch (err) {
      showNotice(`Error al exportar: ${err.message}`, "error");
    }
  };

  byId("quiz-export-md")?.addEventListener("click", () => triggerExport("markdown"));
  byId("quiz-export-pdf")?.addEventListener("click", () => triggerExport("pdf"));
  byId("quiz-export-docx")?.addEventListener("click", () => triggerExport("docx"));
}

// =============================================================================
// Gestión de Cuestionarios Personales vs Cuestionario del Profesor
// =============================================================================
function switchQuizMode(mode) {
  currentMode = mode;
  const sharedBtn = byId("tab-btn-shared");
  const personalBtn = byId("tab-btn-personal");

  if (mode === "shared") {
    if (sharedBtn) {
      sharedBtn.classList.add("active");
      sharedBtn.style.color = "var(--ink)";
      sharedBtn.style.borderBottom = "3px solid var(--blue)";
    }
    if (personalBtn) {
      personalBtn.classList.remove("active");
      personalBtn.style.color = "var(--muted)";
      personalBtn.style.borderBottom = "3px solid transparent";
    }

    // En el cuestionario del profesor, el panel de configuración NUNCA se muestra
    byId("config-panel").style.display = "none";
    byId("personal-quiz-bar").style.display = "none";
    byId("output-panel-title").textContent = "Cuestionario del profesor";

    if (sharedQuiz) {
      activeMaterialId = sharedQuiz.id;
      renderQuiz(sharedQuiz.content);
      updateExportVisibility(sharedQuiz.id);
    } else {
      byId("quiz-output").className = "empty-state";
      byId("quiz-output").textContent = "El profesor no ha publicado aún un cuestionario para este tema.";
      byId("feedback-button").style.display = "none";
    }
  } else if (mode === "personal") {
    if (personalBtn) {
      personalBtn.classList.add("active");
      personalBtn.style.color = "var(--ink)";
      personalBtn.style.borderBottom = "3px solid var(--blue)";
    }
    if (sharedBtn) {
      sharedBtn.classList.remove("active");
      sharedBtn.style.color = "var(--muted)";
      sharedBtn.style.borderBottom = "3px solid transparent";
    }

    byId("personal-quiz-bar").style.display = "flex";
    byId("output-panel-title").textContent = "Mi cuestionario propio";
    renderPersonalQuizzesList();

    if (personalQuizzes && personalQuizzes.length > 0) {
      byId("config-panel").style.display = "none";
      const selId = Number(byId("personal-quiz-select")?.value) || personalQuizzes[0].id;
      const chosen = personalQuizzes.find((q) => q.id === selId) || personalQuizzes[0];
      activeMaterialId = chosen.id;
      renderQuizForStudent(chosen.content, true);
      updateExportVisibility(chosen.id);
    } else {
      // Si no tiene cuestionarios propios aún, invitar a crearlo
      byId("quiz-output").className = "empty-state";
      byId("quiz-output").textContent = "No has creado ningún cuestionario propio todavía. Haz clic en «+ Crear cuestionario propio» para generar uno para practicar.";
      byId("feedback-button").style.display = "none";
    }
  }
}

function renderPersonalQuizzesList() {
  const select = byId("personal-quiz-select");
  if (!select) return;

  if (!personalQuizzes || personalQuizzes.length === 0) {
    select.innerHTML = `<option value="">Sin cuestionarios propios</option>`;
    select.disabled = true;
    return;
  }

  select.disabled = false;
  select.innerHTML = personalQuizzes
    .map(
      (q, idx) =>
        `<option value="${q.id}">Cuestionario personal #${q.id} (Material ${q.id})</option>`
    )
    .join("");

  select.onchange = () => {
    const chosenId = Number(select.value);
    const chosen = personalQuizzes.find((q) => q.id === chosenId);
    if (chosen) {
      activeMaterialId = chosen.id;
      byId("config-panel").style.display = "none";
      renderQuizForStudent(chosen.content, true);
      updateExportVisibility(chosen.id);
    }
  };
}

// Botón "+ Crear cuestionario propio"
byId("toggle-configure-quiz-btn")?.addEventListener("click", () => {
  const panel = byId("config-panel");
  const isHidden = panel.style.display === "none";
  if (isHidden) {
    panel.style.display = "";
    byId("close-config-panel-btn").style.display = "";
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    panel.style.display = "none";
  }
});

byId("close-config-panel-btn")?.addEventListener("click", () => {
  byId("config-panel").style.display = "none";
});

// Pestañas compartidas vs personales
byId("tab-btn-shared")?.addEventListener("click", () => switchQuizMode("shared"));
byId("tab-btn-personal")?.addEventListener("click", () => switchQuizMode("personal"));

// =============================================================================
// Generación de Cuestionario Propio
// =============================================================================
byId("generate-button")?.addEventListener("click", async () => {
  const bloomLevels = selectedBloomLevels();
  if (!bloomLevels.length) return showNotice("Selecciona al menos un nivel de Bloom.", "error");

  await runWithButtonDisabled(byId("generate-button"), async () => {
    try {
      showNotice("Generando cuestionario con evidencia RAG…");
      const payload = {
        video_id: videoId,
        multiple_choice_count: Number(byId("multiple-count").value),
        open_question_count: Number(byId("open-count").value),
        bloom_levels: bloomLevels,
      };
      const modelId = modelSelector.getSelectedModelId();
      if (modelId) payload.model_id = modelId;

      const quiz = await request("/materials/quiz", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      activeMaterialId = quiz.material_id;

      // Cuestionario propio: lo agregamos a la lista personal del usuario
      const newPersonalQuiz = {
        id: quiz.material_id,
        video_id: videoId,
        material_type: "quiz",
        content: quiz,
      };

      personalQuizzes.unshift(newPersonalQuiz);
      renderPersonalQuizzesList();
      byId("personal-quiz-select").value = quiz.material_id;

      // Ocultamos el panel de configuración tras generar
      byId("config-panel").style.display = "none";

      if (groupId && topicId && !isAdmin) {
        // En un tema de grupo, renderizar como cuestionario de práctica personal
        renderQuizForStudent(quiz, true);
        showNotice(`¡Cuestionario propio #${quiz.material_id} generado! Solo tú puedes verlo para practicar.`, "success");
      } else {
        renderQuiz(quiz);
        showNotice(`Cuestionario propio #${quiz.material_id} creado con éxito.`, "success");
      }

      updateExportVisibility(quiz.material_id);
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});

// =============================================================================
// Evaluación / Calificación
// =============================================================================
byId("feedback-button")?.addEventListener("click", async () => {
  const currentMaterialId = activeMaterialId || getPositiveIntParam("material");
  if (!currentMaterialId) return showNotice("Primero genera o abre un cuestionario.", "error");

  await runWithButtonDisabled(byId("feedback-button"), async () => {
    try {
      const multiple_choice_answers = [
        ...new Set([...document.querySelectorAll('#quiz-output input[type="radio"][name^="multiple-"]')].map((i) => i.name)),
      ].flatMap((name) => {
        const selected = document.querySelector(`input[name="${name}"]:checked`);
        return selected
          ? [{ question_index: Number(name.replace("multiple-", "")), selected_option: Number(selected.value) }]
          : [];
      });

      const open_answers = [...document.querySelectorAll('#quiz-output textarea[id^="open-"]')].flatMap((input) => {
        const answer = input.value.trim();
        return answer ? [{ question_index: Number(input.id.replace("open-", "")), answer }] : [];
      });

      if (!multiple_choice_answers.length && !open_answers.length) {
        return showNotice("Responde al menos una pregunta antes de solicitar revisión.", "error");
      }

      showNotice("Evaluando tus respuestas con evidencia RAG…");

      let attemptResult = null;
      let attemptErrorMsg = null;

      // Solo registrar intento oficial en el grupo si estamos en el "Cuestionario del profesor"
      if (groupId && topicId && currentMode === "shared" && !isAdmin) {
        try {
          const attemptPayload = {
            material_id: currentMaterialId,
            multiple_choice_answers: multiple_choice_answers,
            answers: multiple_choice_answers,
            open_answers: open_answers,
          };
          attemptResult = await apiSubmitAttempt(groupId, topicId, attemptPayload);
        } catch (attemptErr) {
          console.warn("No se pudo registrar intento en grupo:", attemptErr);
          attemptErrorMsg = attemptErr.message || "Error al registrar el intento en el grupo.";
        }
      }

      // Obtener retroalimentación detallada
      const feedback = await request(`/materials/${currentMaterialId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ multiple_choice_answers, open_answers }),
      });

      const closed = (feedback.multiple_choice || [])
        .map(
          (item) => `
          <div class="feedback-item ${item.is_correct ? "good" : "bad"}">
            <strong style="display:inline-flex;align-items:center;gap:4px">Pregunta ${item.question_index + 1}: ${item.is_correct ? 'Correcta <svg class="ui-icon" style="color:var(--mint)" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : 'Por revisar <svg class="ui-icon" style="color:var(--red)" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'}</strong><br>
            ${escapeHtml(item.explanation)}
          </div>`
        )
        .join("");

      const open = (feedback.open_questions || [])
        .map(
          (item) => `
          <div class="feedback-item">
            <strong>Pregunta abierta ${item.question_index + 1}</strong><br>
            ${escapeHtml(item.feedback)}<br>
            <small>Logrado: ${escapeHtml(item.achieved_points.join(", ") || "—")} · Falta: ${escapeHtml(item.missing_points.join(", ") || "—")}</small>
          </div>`
        )
        .join("");

      let scoreBanner = "";
      if (attemptResult) {
        const score = attemptResult.final_score !== null ? attemptResult.final_score : attemptResult.raw_score;
        scoreBanner = `
          <div style="background:#eff6ff;border:2px solid var(--blue);border-radius:10px;padding:14px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
            <div>
              <strong style="font-size:16px;color:var(--blue)">Calificación registrada: ${score !== null ? score.toFixed(1) : '—'} / 100</strong>
              <p style="margin:2px 0 0;font-size:12px;color:var(--muted)">Intento #${attemptResult.id} guardado en el grupo. Tu profesor podrá revisarlo.</p>
            </div>
            <a href="/ui/groups/detail/?group=${groupId}" class="secondary" style="text-decoration:none;font-size:12px;padding:6px 12px">Ver mis calificaciones →</a>
          </div>
        `;
      } else if (currentMode === "personal") {
        scoreBanner = `
          <div style="background:#f0fdf4;border:2px solid #10b981;border-radius:10px;padding:14px;margin-bottom:14px">
            <strong style="font-size:15px;color:#047857">Autoevaluación de práctica completada</strong>
            <p style="margin:2px 0 0;font-size:12px;color:#065f46">Este cuestionario es personal para tu estudio. No afecta tus calificaciones oficiales en el grupo.</p>
          </div>
        `;
      } else if (attemptErrorMsg) {
        scoreBanner = `
          <div style="background:#fef2f2;border:2px solid #ef4444;border-radius:10px;padding:14px;margin-bottom:14px">
            <strong style="font-size:15px;color:#b91c1c;display:flex;align-items:center;gap:6px"><svg class="ui-icon" style="color:#b91c1c" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Aviso al registrar la calificación en el grupo</strong>
            <p style="margin:4px 0 0;font-size:13px;color:#7f1d1d">${escapeHtml(attemptErrorMsg)}</p>
          </div>
        `;
      }

      byId("feedback-output").innerHTML = scoreBanner + (closed + open || "No hubo respuestas para revisar.");
      showNotice("Evaluación completada con éxito.", "success");
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});

// =============================================================================
// Inicialización
// =============================================================================
async function init() {
  setupExportHandlers();

  // Si venimos desde un tema de grupo
  if (groupId && topicId) {
    try {
      topicData = await apiGetTopicMaterials(groupId, topicId);
      isAdmin = Boolean(topicData?.is_admin);

      if (topicData?.video_id && !videoId) videoId = topicData.video_id;

      // Enlace para volver al grupo
      const navSteps = document.querySelector(".steps");
      if (navSteps && !document.getElementById("back-to-group-link")) {
        const backLink = document.createElement("a");
        backLink.id = "back-to-group-link";
        backLink.href = `/ui/groups/detail/?group=${groupId}`;
        backLink.style.color = "var(--blue)";
        backLink.style.fontWeight = "700";
        backLink.innerHTML = "← Volver al Grupo";
        navSteps.prepend(backLink);
        const sep = document.createElement("i");
        navSteps.insertBefore(sep, navSteps.children[1]);
      }

      if (topicData.video_id) {
        videoId = topicData.video_id;
        byId("video-label").textContent = `Video ID: ${videoId}`;
        byId("summary-link").href = urlFor("/ui/resumen/", { video: videoId, group: groupId, topic: topicId });
        byId("material-link").href = urlFor("/ui/material/", { video: videoId });
        loadVideoPlayer(videoId);
      }

      sharedQuiz = topicData.shared_quiz;
      personalQuizzes = topicData.personal_quizzes || (topicData.personal_quiz ? [topicData.personal_quiz] : []);

      if (isAdmin) {
        // VISTA ADMINISTRADOR / PROFESOR:
        // Solo ve el cuestionario oficial con respuestas correctas
        // No ve pestañas de miembro, no puede autocalificarse, no ve configurar cuestionario
        byId("quiz-mode-nav").style.display = "none";
        byId("personal-quiz-bar").style.display = "none";
        byId("config-panel").style.display = "none";
        byId("output-panel-title").textContent = "Pauta de Evaluación (Profesor)";

        if (sharedQuiz) {
          activeMaterialId = sharedQuiz.id;
          renderQuizForAdmin(sharedQuiz.content);
          updateExportVisibility(sharedQuiz.id);
          showNotice(`Pauta de evaluación del tema cargada.`, "info");
        } else {
          byId("quiz-output").className = "empty-state";
          byId("quiz-output").textContent = "No hay un cuestionario asignado a este tema aún.";
        }
        return;
      } else {
        // VISTA ESTUDIANTE / MIEMBRO:
        // Separación: Cuestionario del profesor vs Mis cuestionarios propios
        byId("quiz-mode-nav").style.display = "flex";
        byId("config-panel").style.display = "none"; // Configurar solo sale al crear uno propio

        switchQuizMode("shared");
        showNotice(`Evaluación del profesor lista para responder.`, "info");
        return;
      }
    } catch (err) {
      console.warn("No se pudo obtener el material del tema del grupo:", err);
      showNotice(err.message, "error");
    }
  }

  // Si no estamos en un tema de grupo (Modo Standalone / Autoevaluación independiente)
  byId("quiz-mode-nav").style.display = "none";
  byId("personal-quiz-bar").style.display = "none";

  // Si no hay video en la URL, pero sí material
  if (!videoId && materialId) {
    try {
      const mat = await request(`/materials/${materialId}`);
      if (mat?.video_id) videoId = mat.video_id;
    } catch (e) {
      console.warn("No se pudo obtener el video del material:", e);
    }
  }

  // Buscar historial de videos del usuario
  try {
    const res = await apiListMyVideos(1, 25);
    const videos = res.items || [];
    if (videos.length > 0) {
      const switcher = byId("video-switcher");
      const switchBox = byId("video-select-box");

      if (switcher && switchBox) {
        switcher.innerHTML = videos
          .map((v) => `<option value="${v.id}" ${videoId === v.id ? "selected" : ""}>${escapeHtml(v.title)}</option>`)
          .join("");
        switchBox.style.display = "";

        switcher.addEventListener("change", () => {
          const chosen = Number(switcher.value);
          window.location.assign(urlFor("/ui/quiz/", { video: chosen }));
        });
      }

      if (!videoId) {
        videoId = videos[0].id;
        replaceUrl("/ui/quiz/", { video: videoId });
      }
    }
  } catch (err) {
    console.warn("Error cargando historial de videos:", err);
  }

  if (!videoId && !materialId) {
    showNotice("No tienes videos procesados aún. Inicia con la ingesta de un video en la sección 1.", "info");
    byId("config-panel").style.display = "";
    byId("generate-button").disabled = true;
    return;
  }

  if (videoId) {
    byId("video-label").textContent = `Video ID: ${videoId}`;
    byId("summary-link").href = urlFor("/ui/resumen/", { video: videoId });
    byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: materialId });
    loadVideoPlayer(videoId);
  }

  if (materialId) {
    loadStoredQuiz(materialId)
      .then(() => {
        // En modo standalone con cuestionario cargado, ocultar config-panel por defecto
        byId("config-panel").style.display = "none";
      })
      .catch((error) => {
        showNotice(error.message, "error");
        byId("config-panel").style.display = "";
      });
  } else {
    // Si no hay cuestionario cargado en standalone, mostrar panel de configuración
    byId("config-panel").style.display = "";
    showNotice("Configura y genera tu cuestionario.");
  }
}

init();
