import { request } from "/ui/api.js";
import { confirmModal, goTo, renderUserBar, requireAuth, runWithButtonDisabled, showNotice } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
let progressTimer = null;
let polling = false;
let currentJobVideoId = null;

async function pollProgress(videoId) {
  if (polling) return true;
  polling = true;
  try {
    const progress = await request(`/videos/${videoId}/progress`);
    const stageText = (progress.progress_stage || "procesando").replaceAll("_", " ");
    const percent = Math.min(100, Math.max(0, Number(progress.progress_percent) || 0));

    byId("progress-stage").textContent = stageText;
    byId("progress-value").textContent = `${percent}%`;
    byId("progress-bar").style.width = `${percent}%`;

    const track = byId("progress-track-el");
    if (track) track.setAttribute("aria-valuenow", String(percent));

    byId("progress-detail").textContent =
      progress.status === "indexed"
        ? "Video indexado con éxito. Redirigiendo al resumen…"
        : `Estado actual: ${progress.status} · Etapa: ${stageText}`;

    if (progress.status === "indexed") {
      showNotice("Ingesta y vectorización terminadas con éxito. Abriendo el resumen…", "success");
      setTimeout(() => {
        goTo("/ui/resumen/", { video: videoId });
      }, 700);
      return false;
    }
    if (progress.progress_stage === "cancelled") {
      byId("cancel-ingest-button").style.display = "none";
      byId("progress-detail").textContent = "La ingesta fue cancelada por el usuario.";
      showNotice("Ingesta cancelada.", "info");
      return false;
    }
    if (progress.status === "failed") {
      byId("cancel-ingest-button").style.display = "none";
      showNotice("La ingesta falló. Verifica que el video sea público y esté disponible.", "error");
      return false;
    }
    return true;
  } catch (error) {
    showNotice(error.message, "error");
    return false;
  } finally {
    polling = false;
  }
}

byId("cancel-ingest-button")?.addEventListener("click", async () => {
  if (!currentJobVideoId) return;

  const confirmed = await confirmModal({
    title: "Cancelar procesamiento",
    message: "¿Deseas cancelar el procesamiento de este video? Se liberarán los recursos temporales y se detendrá la transcripción.",
    confirmText: "Sí, cancelar ingesta",
    cancelText: "Continuar esperando",
    danger: true,
  });

  if (!confirmed) return;

  try {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    await request(`/videos/${currentJobVideoId}/cancel`, { method: "POST" });
    byId("progress-stage").textContent = "Cancelado";
    byId("progress-detail").textContent = "La ingesta fue cancelada por el usuario.";
    byId("cancel-ingest-button").style.display = "none";
    showNotice("Ingesta cancelada correctamente.", "info");
  } catch (err) {
    showNotice(err.message, "error");
  }
});

byId("ingest-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = byId("video-url").value.trim();
  if (!url) {
    showNotice("Ingresa una URL válida de YouTube.", "error");
    return;
  }

  await runWithButtonDisabled(byId("ingest-button"), async () => {
    try {
      showNotice("Validando el video e iniciando la descarga del audio…", "info");
      const job = await request("/videos/ingest/async", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      currentJobVideoId = job.video_id;
      byId("progress-card").classList.remove("hidden");
      byId("cancel-ingest-button").style.display = "";

      if (await pollProgress(job.video_id)) {
        progressTimer = setInterval(async () => {
          if (!await pollProgress(job.video_id)) {
            clearInterval(progressTimer);
            progressTimer = null;
          }
        }, 2200);
      }
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});
