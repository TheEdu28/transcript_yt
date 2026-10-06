import { fetchModels, request } from "/ui/api.js";
import { escapeHtml, getPositiveIntParam, initModelSelector, renderUserBar, requireAuth, replaceUrl, runWithButtonDisabled, showNotice, urlFor } from "/ui/shared.js";
const byId = (id) => document.getElementById(id);
requireAuth();
renderUserBar();
const videoId = getPositiveIntParam("video");

const modelSelector = initModelSelector("model-selector-container", fetchModels);

function renderSummary(summary) {
  const glossary = summary.glossary.map((item) => `<li><strong>${escapeHtml(item.term)}</strong> <span class="timestamp">${item.timestamp}</span><br>${escapeHtml(item.definition)}</li>`).join("");
  const blocks = summary.didactic_blocks.map((item) => `<article class="question"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.explanation)}</p><span class="timestamp">${item.timestamps.join(", ")}</span></article>`).join("");
  byId("summary-output").className = "summary-copy";
  byId("summary-output").innerHTML = `<p>${escapeHtml(summary.synopsis)}</p><h3>Glosario</h3><ul class="glossary">${glossary || "<li>Sin términos adicionales.</li>"}</ul><h3>Bloques didácticos</h3>${blocks || "<p>Sin bloques adicionales.</p>"}`;
}

if (!videoId) { showNotice("Falta un video válido. Inicia una ingesta o usa ?video=42.", "error"); byId("generate-button").disabled = true; }
else {
  byId("video-label").textContent = `Video ID: ${videoId}`;
  byId("quiz-link").href = urlFor("/ui/quiz/", { video: videoId });
  byId("material-link").href = urlFor("/ui/material/", { video: videoId });
  showNotice("Video listo para generar un resumen.");
}

byId("generate-button").addEventListener("click", async () => {
  await runWithButtonDisabled(byId("generate-button"), async () => {
    try {
    showNotice("Generando resumen fundamentado con evidencia RAG…");
    const payload = { video_id: videoId };
    const modelId = modelSelector.getSelectedModelId();
    if (modelId) payload.model_id = modelId;
    const summary = await request("/materials/summary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    renderSummary(summary);
    replaceUrl("/ui/resumen/", { video: videoId, material: summary.material_id });
    byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: summary.material_id });
    showNotice(`Resumen creado como material ${summary.material_id}.`, "success");
    } catch (error) { showNotice(error.message, "error"); }
  });
});
