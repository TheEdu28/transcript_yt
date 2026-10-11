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

function renderQuiz(quiz) {
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
            ⏱ Evidencia: ${escapeHtml(question.evidence_timestamp)}
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
            ⏱ Evidencia: ${escapeHtml(question.evidence_timestamp)}
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

  byId("feedback-button").disabled = false;
  if (activeMaterialId) updateExportVisibility(activeMaterialId);
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
    byId("summary-link").href = urlFor("/ui/resumen/", { video: material.video_id });
    byId("material-link").href = urlFor("/ui/material/", { video: material.video_id, material: material.id });
    replaceUrl("/ui/quiz/", { video: material.video_id, material: material.id });
    loadVideoPlayer(material.video_id);
  }
  showNotice(`Cuestionario ${id} cargado.`, "success");
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

function setupExportHandlers() {
  const triggerExport = async (format) => {
    if (!activeMaterialId) {
      showNotice("Primero debes generar o cargar un cuestionario.", "error");
      return;
    }
    showNotice(`Generando archivo ${format.toUpperCase()}…`, "info");
    try {
      const token = auth.token();
      const headers = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`/api/v1/materials/${activeMaterialId}/export?format=${format}`, { headers });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail?.message || `Error al exportar (${res.status})`);
      }

      const blob = await res.blob();
      const extMap = { markdown: "md", pdf: "pdf", docx: "docx" };
      const filename = `cuestionario_${activeMaterialId}.${extMap[format] || format}`;

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      showNotice(`✓ Archivo ${filename} descargado con éxito.`, "success");
    } catch (err) {
      showNotice(`Error al exportar: ${err.message}`, "error");
    }
  };

  byId("quiz-export-md")?.addEventListener("click", () => triggerExport("markdown"));
  byId("quiz-export-pdf")?.addEventListener("click", () => triggerExport("pdf"));
  byId("quiz-export-docx")?.addEventListener("click", () => triggerExport("docx"));
}

async function init() {
  setupExportHandlers();

  // Si venimos desde un tema de grupo, cargar el material compartido del tema
  if (groupId && topicId) {
    try {
      const topicMats = await apiGetTopicMaterials(groupId, topicId);
      if (topicMats?.video_id && !videoId) videoId = topicMats.video_id;

      // Actualizar enlace para volver al grupo
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

      if (topicMats?.quiz) {
        activeMaterialId = topicMats.quiz.id;
        materialId = topicMats.quiz.id;
        renderQuiz(topicMats.quiz.content);
        updateExportVisibility(topicMats.quiz.id);

        const banner = document.createElement("div");
        banner.className = "notice";
        banner.style.borderLeft = "4px solid var(--violet)";
        banner.style.marginBottom = "14px";
        banner.innerHTML = `<strong>Evaluación del tema:</strong> ${escapeHtml(topicMats.title)} · <em>Las respuestas se calificarán y registrarán en el libro de calificaciones del grupo.</em>`;
        byId("quiz-output")?.parentNode.insertBefore(banner, byId("quiz-output"));

        if (topicMats.video_id) {
          videoId = topicMats.video_id;
          byId("video-label").textContent = `Video ID: ${videoId}`;
          byId("summary-link").href = urlFor("/ui/resumen/", { video: videoId, group: groupId, topic: topicId });
          byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: materialId });
          loadVideoPlayer(videoId);
        }
        showNotice(`Evaluación del tema «${topicMats.title}» lista para responder.`, "info");
        return;
      }
    } catch (err) {
      console.warn("No se pudo obtener el material del tema del grupo:", err);
      showNotice(err.message, "error");
    }
  }

  // Si no hay video en la URL, pero sí material
  if (!videoId && materialId) {
    try {
      const mat = await request(`/materials/${materialId}`);
      if (mat?.video_id) videoId = mat.video_id;
    } catch (e) {
      console.warn("No se pudo obtener el video del material:", e);
    }
  }

  // Si aún no hay videoId, buscar el historial de videos del usuario
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
    loadStoredQuiz(materialId).catch((error) => showNotice(error.message, "error"));
  } else {
    showNotice("Configura y genera el cuestionario.");
  }
}

byId("generate-button").addEventListener("click", async () => {
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
      renderQuiz(quiz);
      updateExportVisibility(quiz.material_id);
      
      const pageParams = { video: videoId, material: quiz.material_id };
      if (groupId) pageParams.group = groupId;
      if (topicId) pageParams.topic = topicId;
      replaceUrl("/ui/quiz/", pageParams);
      byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: quiz.material_id });

      if (groupId && topicId) {
        try {
          await request(`/groups/${groupId}/topics/${topicId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ material_id: quiz.material_id, video_id: videoId }),
          });
          showNotice(`¡Cuestionario #${quiz.material_id} creado y vinculado exitosamente al tema del grupo!`, "success");
        } catch (linkErr) {
          console.warn("No se pudo vincular automáticamente el cuestionario al tema:", linkErr);
          showNotice(`Cuestionario creado como material ${quiz.material_id}.`, "success");
        }
      } else {
        showNotice(`Cuestionario creado como material ${quiz.material_id}.`, "success");
      }
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});

byId("feedback-button").addEventListener("click", async () => {
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

      // Si estamos en un tema de grupo, registrar el intento oficial en el grupo
      let attemptResult = null;
      if (groupId && topicId) {
        try {
          const attemptPayload = {
            material_id: currentMaterialId,
            multiple_choice_answers: multiple_choice_answers,
            answers: multiple_choice_answers,
            open_answers: open_answers,
          };
          attemptResult = await apiSubmitAttempt(groupId, topicId, attemptPayload);
        } catch (attemptErr) {
          console.warn("No se pudo registrar intento en grupo, evaluando solo retroalimentación:", attemptErr);
        }
      }

      // Obtener la retroalimentación detallada
      const feedback = await request(`/materials/${currentMaterialId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ multiple_choice_answers, open_answers }),
      });

      const closed = feedback.multiple_choice
        .map(
          (item) => `
          <div class="feedback-item ${item.is_correct ? "good" : "bad"}">
            <strong>Pregunta ${item.question_index + 1}: ${item.is_correct ? "Correcta ✓" : "Por revisar ✗"}</strong><br>
            ${escapeHtml(item.explanation)}
          </div>`
        )
        .join("");

      const open = feedback.open_questions
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
      }

      byId("feedback-output").innerHTML = scoreBanner + (closed + open || "No hubo respuestas para revisar.");
      showNotice("Evaluación completada con éxito.", "success");
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});

init();
