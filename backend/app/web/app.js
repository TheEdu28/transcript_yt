const byId = (id) => document.getElementById(id);
let activeMaterialId = null;
let activeQuiz = null;
let progressTimer = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function showNotice(message, type = "") {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = `notice ${type}`.trim();
}

async function request(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail?.message || `Error ${response.status}`);
  }
  return response.json();
}

function selectedBloomLevels() {
  return [...document.querySelectorAll(".bloom-options input:checked")].map((input) => input.value);
}

function setActiveMaterial(materialId) {
  activeMaterialId = materialId;
  byId("material-id").value = materialId || "";
}

function renderSummary(summary) {
  const glossary = summary.glossary.map((item) => `<li><strong>${escapeHtml(item.term)}</strong> <span class="timestamp">${item.timestamp}</span><br>${escapeHtml(item.definition)}</li>`).join("");
  const blocks = summary.didactic_blocks.map((item) => `<div class="question"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.explanation)}</p><span class="timestamp">${item.timestamps.join(", ")}</span></div>`).join("");
  byId("summary-output").className = "summary-copy";
  byId("summary-output").innerHTML = `<p>${escapeHtml(summary.synopsis)}</p><h3>Glosario</h3><ul class="glossary">${glossary || "<li>Sin términos adicionales.</li>"}</ul><h3>Bloques didácticos</h3>${blocks || "<p>Sin bloques adicionales.</p>"}`;
}

function renderQuiz(quiz) {
  activeQuiz = quiz;
  const multiple = quiz.multiple_choice.map((question, index) => {
    const options = question.options.map((option, optionIndex) => `<label><input type="radio" name="multiple-${index}" value="${optionIndex}">${escapeHtml(option)}</label>`).join("");
    return `<article class="question"><div class="question-head"><strong>${index + 1}. ${escapeHtml(question.question)}</strong><span class="badge">${question.bloom_level}</span></div><div class="options">${options}</div><span class="timestamp">Evidencia: ${question.evidence_timestamp}</span></article>`;
  }).join("");
  const open = quiz.open_questions.map((question, index) => `<article class="question"><div class="question-head"><strong>Abierta ${index + 1}. ${escapeHtml(question.question)}</strong><span class="badge">${question.bloom_level}</span></div><label class="open-answer">Tu respuesta<textarea id="open-${index}" rows="3" placeholder="Explica con tus palabras..."></textarea></label><span class="timestamp">Evidencia: ${question.evidence_timestamp}</span></article>`).join("");
  byId("quiz-output").className = "";
  byId("quiz-output").innerHTML = `${multiple}<h3>Preguntas abiertas</h3>${open || "<p>Este cuestionario no contiene preguntas abiertas.</p>"}`;
  byId("feedback-button").disabled = false;
}

async function pollProgress(videoId) {
  try {
    const progress = await request(`/videos/${videoId}/progress`);
    byId("progress-stage").textContent = progress.progress_stage.replaceAll("_", " ");
    byId("progress-value").textContent = `${progress.progress_percent}%`;
    byId("progress-bar").style.width = `${progress.progress_percent}%`;
    byId("progress-detail").textContent = progress.status === "indexed" ? "Video listo para generar material." : `Estado: ${progress.status}`;
    if (progress.status === "indexed" || progress.status === "failed") {
      clearInterval(progressTimer);
      progressTimer = null;
      if (progress.status === "indexed") showNotice("Ingesta terminada. Ya puedes generar el resumen o cuestionario.", "success");
      if (progress.status === "failed") showNotice("La ingesta falló. Revisa las cookies de YouTube o el registro del servidor.", "error");
    }
  } catch (error) { showNotice(error.message, "error"); clearInterval(progressTimer); }
}

byId("ingest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    showNotice("Validando el video y creando el trabajo de ingesta...");
    const job = await request("/videos/ingest/async", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: byId("video-url").value }) });
    byId("video-id").value = job.video_id;
    byId("progress-card").classList.remove("hidden");
    if (progressTimer) clearInterval(progressTimer);
    await pollProgress(job.video_id);
    progressTimer = setInterval(() => pollProgress(job.video_id), 2500);
  } catch (error) { showNotice(error.message, "error"); }
});

byId("summary-button").addEventListener("click", async () => {
  const videoId = Number(byId("video-id").value);
  if (!videoId) return showNotice("Ingresa un Video ID válido.", "error");
  try {
    showNotice("Generando resumen fundamentado...");
    const summary = await request("/materials/summary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_id: videoId }) });
    setActiveMaterial(summary.material_id); renderSummary(summary); showNotice(`Resumen creado como material ${summary.material_id}.`, "success");
  } catch (error) { showNotice(error.message, "error"); }
});

byId("quiz-button").addEventListener("click", async () => {
  const videoId = Number(byId("video-id").value); const bloomLevels = selectedBloomLevels();
  if (!videoId) return showNotice("Ingresa un Video ID válido.", "error");
  if (!bloomLevels.length) return showNotice("Selecciona al menos un nivel de Bloom.", "error");
  try {
    showNotice("Generando cuestionario con evidencia RAG...");
    const quiz = await request("/materials/quiz", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_id: videoId, multiple_choice_count: Number(byId("multiple-count").value), open_question_count: Number(byId("open-count").value), bloom_levels: bloomLevels }) });
    setActiveMaterial(quiz.material_id); renderQuiz(quiz); showNotice(`Cuestionario creado como material ${quiz.material_id}.`, "success");
  } catch (error) { showNotice(error.message, "error"); }
});

byId("feedback-button").addEventListener("click", async () => {
  if (!activeMaterialId || !activeQuiz) return showNotice("Primero genera un cuestionario.", "error");
  const multipleChoiceAnswers = activeQuiz.multiple_choice.flatMap((_, index) => { const selected = document.querySelector(`input[name="multiple-${index}"]:checked`); return selected ? [{ question_index: index, selected_option: Number(selected.value) }] : []; });
  const openAnswers = activeQuiz.open_questions.flatMap((_, index) => { const answer = byId(`open-${index}`).value.trim(); return answer ? [{ question_index: index, answer }] : []; });
  if (!multipleChoiceAnswers.length && !openAnswers.length) return showNotice("Responde al menos una pregunta antes de solicitar retroalimentación.", "error");
  try {
    showNotice("Revisando tus respuestas...");
    const feedback = await request(`/materials/${activeMaterialId}/feedback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ multiple_choice_answers: multipleChoiceAnswers, open_answers: openAnswers }) });
    const closed = feedback.multiple_choice.map((item) => `<div class="feedback-item ${item.is_correct ? "good" : "bad"}"><strong>Pregunta ${item.question_index + 1}: ${item.is_correct ? "Correcta" : "Por revisar"}</strong><br>${escapeHtml(item.explanation)}</div>`).join("");
    const open = feedback.open_questions.map((item) => `<div class="feedback-item"><strong>Pregunta abierta ${item.question_index + 1}</strong><br>${escapeHtml(item.feedback)}<br><small>Logrado: ${escapeHtml(item.achieved_points.join(", ") || "—")} · Falta: ${escapeHtml(item.missing_points.join(", ") || "—")}</small></div>`).join("");
    byId("feedback-output").innerHTML = closed + open || "No hubo respuestas para revisar.";
    showNotice("Retroalimentación lista.", "success");
  } catch (error) { showNotice(error.message, "error"); }
});

byId("load-material").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Ingresa un Material ID válido.", "error");
  try { const material = await request(`/materials/${materialId}`); setActiveMaterial(material.id); byId("material-editor").value = JSON.stringify(material.content, null, 2); showNotice(`Material ${material.id} cargado para edición.`, "success"); } catch (error) { showNotice(error.message, "error"); }
});

byId("save-material").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  try { const content = JSON.parse(byId("material-editor").value); await request(`/materials/${materialId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) }); showNotice("Edición guardada.", "success"); } catch (error) { showNotice(`No se pudo guardar: ${error.message}`, "error"); }
});

byId("export-material").addEventListener("click", () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Ingresa un Material ID válido.", "error");
  window.open(`/api/v1/materials/${materialId}/export?format=markdown`, "_blank", "noopener");
});
