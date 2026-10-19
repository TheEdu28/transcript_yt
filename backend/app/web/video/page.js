import { request } from "/ui/api.js";
import { goTo, renderUserBar, requireAuth, runWithButtonDisabled, showNotice } from "/ui/shared.js";

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
    byId("progress-stage").textContent = progress.progress_stage.replaceAll("_", " ");
    byId("progress-value").textContent = `${progress.progress_percent}%`;
    byId("progress-bar").style.width = `${progress.progress_percent}%`;
    byId("progress-detail").textContent = progress.status === "indexed" ? "Video listo para generar material." : `Estado: ${progress.status}`;
    if (progress.status === "indexed") {
      showNotice("Ingesta terminada. Abriendo el resumen…", "success");
      goTo("/ui/resumen/", { video: videoId });
      return false;
    }
    if (progress.progress_stage === "cancelled") {
      byId("cancel-ingest-button").style.display = "none";
      byId("progress-detail").textContent = "La ingesta fue cancelada por el usuario.";
      showNotice("Ingesta cancelada.", "notice");
      return false;
    }
    if (progress.status === "failed") {
      byId("cancel-ingest-button").style.display = "none";
      showNotice("La ingesta falló. Revisa el registro del servidor.", "error");
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
  if (!confirm("¿Deseas cancelar el procesamiento de este video?")) return;
  try {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    await request(`/videos/${currentJobVideoId}/cancel`, { method: "POST" });
    byId("progress-stage").textContent = "Cancelado";
    byId("progress-detail").textContent = "La ingesta fue cancelada por el usuario.";
    byId("cancel-ingest-button").style.display = "none";
    showNotice("Ingesta cancelada.", "notice");
  } catch (err) {
    showNotice(err.message, "error");
  }
});

byId("ingest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runWithButtonDisabled(byId("ingest-button"), async () => {
    try {
      showNotice("Validando el video y creando el trabajo de ingesta…");
      const job = await request("/videos/ingest/async", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: byId("video-url").value }),
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
        }, 2500);
      }
    } catch (error) {
      showNotice(error.message, "error");
    }
  });
});
