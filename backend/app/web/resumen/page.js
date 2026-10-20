import { apiGetTopicMaterials, apiGetVideo, apiListMyMaterials, apiListMyVideos, auth, fetchModels, request } from "/ui/api.js";
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

const modelSelector = initModelSelector("model-selector-container", fetchModels);

let ytPlayer = null;
let isPlayerReady = false;
let autoPauseTargetSecond = null;
let autoPauseCheckInterval = null;
let activeMaterialId = null;

/** Convierte una cadena de formato HH:MM:SS (o MM:SS) a segundos enteros. */
export function parseTimestampToSeconds(hhmmss) {
  if (!hhmmss) return 0;
  const parts = hhmmss.trim().split(":").map(Number);
  if (parts.length === 3) {
    const [h, m, s] = parts;
    return h * 3600 + m * 60 + s;
  }
  if (parts.length === 2) {
    const [m, s] = parts;
    return m * 60 + s;
  }
  return Number(parts[0]) || 0;
}

/** Limpia el intervalo de pausa automática. */
function clearAutoPauseWatcher() {
  if (autoPauseCheckInterval) {
    clearInterval(autoPauseCheckInterval);
    autoPauseCheckInterval = null;
  }
  autoPauseTargetSecond = null;
}

/** Inicia el sondeo para pausar el video exactamente al llegar a endSecond. */
function setAutoPauseWatcher(endSecond) {
  clearAutoPauseWatcher();
  if (typeof endSecond !== "number" || isNaN(endSecond)) return;

  autoPauseTargetSecond = endSecond;
  autoPauseCheckInterval = setInterval(() => {
    if (!ytPlayer || !isPlayerReady) return;
    try {
      const current = ytPlayer.getCurrentTime ? ytPlayer.getCurrentTime() : 0;
      if (current >= autoPauseTargetSecond) {
        ytPlayer.pauseVideo();
        clearAutoPauseWatcher();
        showNotice("Reproducción pausada al finalizar el bloque didáctico.", "success");
      }
    } catch {
      clearAutoPauseWatcher();
    }
  }, 250);
}

/**
 * Salta al segundo correspondiente en el reproductor de YouTube.
 * Opcionalmente recibe endHhmmss para pausar automáticamente al finalizar el bloque.
 */
export function seekToTimestamp(startHhmmss, endHhmmss = null) {
  const startSeconds = parseTimestampToSeconds(startHhmmss);
  if (ytPlayer && isPlayerReady && ytPlayer.seekTo) {
    ytPlayer.seekTo(startSeconds, true);
    ytPlayer.playVideo();

    if (endHhmmss) {
      const endSeconds = parseTimestampToSeconds(endHhmmss);
      if (endSeconds > startSeconds) {
        setAutoPauseWatcher(endSeconds);
      } else {
        clearAutoPauseWatcher();
      }
    } else {
      clearAutoPauseWatcher();
    }

    byId("player-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } else {
    showNotice(`Cargando reproductor (segundo ${startSeconds}). Intenta de nuevo en unos segundos.`, "info");
  }
}

/** Inicializa el IFrame Player API de YouTube de forma nativa sin librerías externas. */
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
        playerVars: {
          playsinline: 1,
          rel: 0,
          modestbranding: 1,
        },
        events: {
          onReady: () => {
            isPlayerReady = true;
          },
          onStateChange: (event) => {
            if (
              window.YT &&
              (event.data === window.YT.PlayerState.PAUSED || event.data === window.YT.PlayerState.ENDED)
            ) {
              if (autoPauseTargetSecond !== null) {
                const current = ytPlayer.getCurrentTime ? ytPlayer.getCurrentTime() : 0;
                if (current < autoPauseTargetSecond && event.data === window.YT.PlayerState.PAUSED) {
                  clearAutoPauseWatcher();
                }
              }
            }
          },
        },
      });
    } catch (e) {
      console.warn("Error creando YT.Player:", e);
    }
  };

  if (window.YT && window.YT.Player) {
    createPlayer();
  } else {
    window.onYouTubeIframeAPIReady = () => {
      createPlayer();
    };

    if (!document.getElementById("yt-iframe-api")) {
      const tag = document.createElement("script");
      tag.id = "yt-iframe-api";
      tag.src = "https://www.youtube.com/iframe_api";
      const firstScriptTag = document.getElementsByTagName("script")[0];
      firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    }
  }
}

/** Renderiza el timestamp como un botón interactivo clickeable. */
function renderTimestampButton(timestampStr, endStr = null) {
  const dataEnd = endStr ? ` data-end="${escapeHtml(endStr)}"` : "";
  const title = endStr
    ? `Reproducir bloque (${escapeHtml(timestampStr)} hasta ${escapeHtml(endStr)})`
    : `Saltar a ${escapeHtml(timestampStr)}`;
  return `<button type="button" class="timestamp" data-timestamp="${escapeHtml(timestampStr)}"${dataEnd} title="${title}"><svg class="ui-icon" style="width:0.95em;height:0.95em" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${escapeHtml(timestampStr)}</button>`;
}

function updateExportVisibility(matId) {
  activeMaterialId = matId;
  const bar = byId("summary-export-actions");
  if (bar) {
    bar.style.display = matId ? "flex" : "none";
  }
}

function renderSummary(summary) {
  const glossary = (summary.glossary || [])
    .map(
      (item) => `<li>
        <strong>${escapeHtml(item.term)}</strong> ${renderTimestampButton(item.timestamp)}<br>
        ${escapeHtml(item.definition)}
      </li>`
    )
    .join("");

  const didacticBlocks = summary.didactic_blocks || [];
  const blocks = didacticBlocks
    .map((block, idx) => {
      let blockEnd = null;
      if (block.timestamps && block.timestamps.length > 1) {
        blockEnd = block.timestamps[block.timestamps.length - 1];
      } else if (idx + 1 < didacticBlocks.length) {
        const nextBlock = didacticBlocks[idx + 1];
        if (nextBlock.timestamps && nextBlock.timestamps.length > 0) {
          blockEnd = nextBlock.timestamps[0];
        }
      }

      const buttons = (block.timestamps || [])
        .map((t) => {
          const endForThis = t !== blockEnd ? blockEnd : null;
          return renderTimestampButton(t, endForThis);
        })
        .join(" ");

      return `<article class="question" style="margin-bottom:14px">
        <div class="question-head">
          <strong>${escapeHtml(block.title)}</strong>
        </div>
        <p>${escapeHtml(block.explanation)}</p>
        <div style="margin-top:6px">${buttons}</div>
      </article>`;
    })
    .join("");

  const output = byId("summary-output");
  output.className = "";
  output.innerHTML = `
    <article class="question" style="margin-bottom:16px">
      <div class="question-head">
        <strong>Sinopsis</strong>
      </div>
      <p>${escapeHtml(summary.synopsis)}</p>
    </article>
    <h3>Glosario de conceptos</h3>
    <ul class="editor-list" style="margin-bottom:20px">${glossary || "<li>Sin glosario disponible.</li>"}</ul>
    <h3>Bloques temáticos</h3>
    <div>${blocks || "<p>Sin bloques didácticos.</p>"}</div>
  `;

  output.querySelectorAll(".timestamp").forEach((btn) => {
    btn.addEventListener("click", () => {
      const start = btn.dataset.timestamp;
      const end = btn.dataset.end || null;
      if (start) seekToTimestamp(start, end);
    });
  });

  if (summary.material_id) {
    updateExportVisibility(summary.material_id);
  }
}

async function loadExistingMaterial(id) {
  const material = await request(`/materials/${id}`);
  if (material.material_type !== "summary") return;
  renderSummary(material.content);
  updateExportVisibility(id);
  showNotice(`Resumen cargado (Material ID: ${id}).`, "success");
}

function setupExportHandlers() {
  const triggerExport = async (format) => {
    if (!activeMaterialId) {
      showNotice("Primero debes generar o cargar un resumen.", "error");
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
      const filename = `resumen_${activeMaterialId}.${extMap[format] || format}`;

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

  byId("resumen-export-md")?.addEventListener("click", () => triggerExport("markdown"));
  byId("resumen-export-pdf")?.addEventListener("click", () => triggerExport("pdf"));
  byId("resumen-export-docx")?.addEventListener("click", () => triggerExport("docx"));
}

async function init() {
  setupExportHandlers();

  // Si venimos desde un tema de grupo, cargar el resumen compartido del tema
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

      if (topicMats?.summary) {
        activeMaterialId = topicMats.summary.id;
        materialId = topicMats.summary.id;
        renderSummary(topicMats.summary.content);
        updateExportVisibility(topicMats.summary.id);

        const banner = document.createElement("div");
        banner.className = "notice";
        banner.style.borderLeft = "4px solid var(--blue)";
        banner.style.marginBottom = "14px";
        banner.innerHTML = `<strong>Resumen didáctico oficial del tema:</strong> ${escapeHtml(topicMats.title)} · <em>Material publicado por el docente para el grupo.</em>`;
        byId("summary-output")?.parentNode.insertBefore(banner, byId("summary-output"));

        if (topicMats.video_id) {
          videoId = topicMats.video_id;
          byId("video-label").textContent = `Video ID: ${videoId}`;
          byId("quiz-link").href = urlFor("/ui/quiz/", { video: videoId, group: groupId, topic: topicId });
          byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: materialId });
          loadVideoPlayer(videoId);
        }
        showNotice(`Resumen del tema «${topicMats.title}» cargado.`, "info");
        return;
      }
    } catch (err) {
      console.warn("No se pudo obtener el material del tema del grupo:", err);
    }
  }

  // Si no hay video en la URL, pero sí material, obtenemos el video del material
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
          window.location.assign(urlFor("/ui/resumen/", { video: chosen }));
        });
      }

      if (!videoId) {
        videoId = videos[0].id;
        replaceUrl("/ui/resumen/", { video: videoId });
      }
    }
  } catch (err) {
    console.warn("Error cargando historial de videos:", err);
  }

  if (!videoId) {
    showNotice("No tienes videos procesados aún. Inicia con la ingesta de un video en la sección 1.", "info");
    byId("generate-button").disabled = true;
    return;
  }

  byId("video-label").textContent = `Video ID: ${videoId}`;
  byId("quiz-link").href = urlFor("/ui/quiz/", { video: videoId });
  byId("material-link").href = urlFor("/ui/material/", { video: videoId });

  try {
    const video = await apiGetVideo(videoId);
    if (video?.title) {
      byId("video-label").textContent = `${video.title} (ID: ${videoId})`;
    }
    if (video?.youtube_id) {
      initYouTubePlayer(video.youtube_id, video.title || "");
    }
  } catch (err) {
    console.warn("No se pudo cargar la información del video:", err);
  }

  if (materialId) {
    try {
      await loadExistingMaterial(materialId);
    } catch (err) {
      showNotice(err.message, "error");
    }
  } else {
    // Si no se pasó material en la URL, auto-detectar si ya hay un resumen para este video
    try {
      const mats = await apiListMyMaterials();
      const existing = (mats || []).find((m) => m.video_id === videoId && m.material_type === "summary");
      if (existing) {
        materialId = existing.id;
        replaceUrl("/ui/resumen/", { video: videoId, material: materialId });
        byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: materialId });
        await loadExistingMaterial(materialId);
        return;
      }
    } catch {
      // Continuar normalmente
    }
    showNotice("Video listo para generar o consultar su resumen.");
  }
}

byId("generate-button").addEventListener("click", async () => {
  await runWithButtonDisabled(byId("generate-button"), async (signal) => {
    try {
      showNotice("Generando resumen fundamentado con evidencia RAG…");
      const payload = { video_id: videoId };
      const modelId = modelSelector.getSelectedModelId();
      if (modelId) payload.model_id = modelId;

      const summary = await request("/materials/summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
      });

      renderSummary(summary);
      activeMaterialId = summary.material_id;
      updateExportVisibility(summary.material_id);
      replaceUrl("/ui/resumen/", { video: videoId, material: summary.material_id });
      byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: summary.material_id });
      showNotice(`Resumen creado como material ${summary.material_id}.`, "success");
    } catch (error) {
      if (error.name === "AbortError") {
        showNotice("Generación cancelada por el usuario.");
      } else {
        showNotice(error.message, "error");
      }
    }
  }, { cancellable: true });
});

init();
