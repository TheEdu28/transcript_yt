import { fetchModels, request } from "/ui/api.js";
import { escapeHtml, getPositiveIntParam, initModelSelector, renderUserBar, requireAuth, replaceUrl, runWithButtonDisabled, showNotice, urlFor } from "/ui/shared.js";
const byId = (id) => document.getElementById(id);
requireAuth();
renderUserBar();
const videoId = getPositiveIntParam("video");
const materialId = getPositiveIntParam("material");
const selectedBloomLevels = () => [...document.querySelectorAll(".bloom-options input:checked")].map((input) => input.value);

const modelSelector = initModelSelector("model-selector-container", fetchModels);

function renderQuiz(quiz) {
  const multiple = quiz.multiple_choice.map((question, index) => `<article class="question"><div class="question-head"><strong>${index + 1}. ${escapeHtml(question.question)}</strong><span class="badge">${question.bloom_level}</span></div><div class="options">${question.options.map((option, optionIndex) => `<label><input type="radio" name="multiple-${index}" value="${optionIndex}">${escapeHtml(option)}</label>`).join("")}</div><span class="timestamp">Evidencia: ${question.evidence_timestamp}</span></article>`).join("");
  const open = quiz.open_questions.map((question, index) => `<article class="question"><div class="question-head"><strong>Abierta ${index + 1}. ${escapeHtml(question.question)}</strong><span class="badge">${question.bloom_level}</span></div><label class="open-answer">Tu respuesta<textarea id="open-${index}" rows="3" placeholder="Explica con tus palabras..."></textarea></label><span class="timestamp">Evidencia: ${question.evidence_timestamp}</span></article>`).join("");
  byId("quiz-output").className = "";
  byId("quiz-output").innerHTML = `${multiple}<h3>Preguntas abiertas</h3>${open || "<p>Este cuestionario no contiene preguntas abiertas.</p>"}`;
  byId("feedback-button").disabled = false;
}

async function loadStoredQuiz(id) {
  const material = await request(`/materials/${id}`);
  if (material.material_type !== "quiz") throw new Error("El material indicado no es un cuestionario.");
  renderQuiz(material.content);
  byId("video-label").textContent = `Video ID: ${material.video_id}`;
  byId("summary-link").href = urlFor("/ui/resumen/", { video: material.video_id });
  byId("material-link").href = urlFor("/ui/material/", { video: material.video_id, material: material.id });
  replaceUrl("/ui/quiz/", { video: material.video_id, material: material.id });
  showNotice(`Cuestionario ${id} cargado.`, "success");
}

if (!videoId && !materialId) { showNotice("Usa ?video=42 para generar un cuestionario o ?material=17 para abrir uno.", "error"); byId("generate-button").disabled = true; }
else {
  if (videoId) {
    byId("video-label").textContent = `Video ID: ${videoId}`;
    byId("summary-link").href = urlFor("/ui/resumen/", { video: videoId });
    byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: materialId });
  }
  if (materialId) loadStoredQuiz(materialId).catch((error) => showNotice(error.message, "error"));
  else showNotice("Configura y genera el cuestionario.");
}

byId("generate-button").addEventListener("click", async () => {
  const bloomLevels = selectedBloomLevels();
  if (!bloomLevels.length) return showNotice("Selecciona al menos un nivel de Bloom.", "error");
  await runWithButtonDisabled(byId("generate-button"), async () => {
    try {
    showNotice("Generando cuestionario con evidencia RAG…");
    const payload = { video_id: videoId, multiple_choice_count: Number(byId("multiple-count").value), open_question_count: Number(byId("open-count").value), bloom_levels: bloomLevels };
    const modelId = modelSelector.getSelectedModelId();
    if (modelId) payload.model_id = modelId;
    const quiz = await request("/materials/quiz", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    renderQuiz(quiz);
    replaceUrl("/ui/quiz/", { video: videoId, material: quiz.material_id });
    byId("material-link").href = urlFor("/ui/material/", { video: videoId, material: quiz.material_id });
    showNotice(`Cuestionario creado como material ${quiz.material_id}.`, "success");
    } catch (error) { showNotice(error.message, "error"); }
  });
});

byId("feedback-button").addEventListener("click", async () => {
  const currentMaterialId = getPositiveIntParam("material");
  if (!currentMaterialId) return showNotice("Primero genera o abre un cuestionario.", "error");
  await runWithButtonDisabled(byId("feedback-button"), async () => {
    try {
    const multiple_choice_answers = [...new Set([...document.querySelectorAll('#quiz-output input[type="radio"][name^="multiple-"]')].map((input) => input.name))].flatMap((name) => {
      const selected = document.querySelector(`input[name="${name}"]:checked`);
      return selected ? [{ question_index: Number(name.replace("multiple-", "")), selected_option: Number(selected.value) }] : [];
    });
    const open_answers = [...document.querySelectorAll('#quiz-output textarea[id^="open-"]')].flatMap((input) => {
      const answer = input.value.trim();
      return answer ? [{ question_index: Number(input.id.replace("open-", "")), answer }] : [];
    });
    if (!multiple_choice_answers.length && !open_answers.length) return showNotice("Responde al menos una pregunta antes de solicitar retroalimentación.", "error");
    showNotice("Revisando tus respuestas…");
    const feedback = await request(`/materials/${currentMaterialId}/feedback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ multiple_choice_answers, open_answers }) });
    const closed = feedback.multiple_choice.map((item) => `<div class="feedback-item ${item.is_correct ? "good" : "bad"}"><strong>Pregunta ${item.question_index + 1}: ${item.is_correct ? "Correcta" : "Por revisar"}</strong><br>${escapeHtml(item.explanation)}</div>`).join("");
    const open = feedback.open_questions.map((item) => `<div class="feedback-item"><strong>Pregunta abierta ${item.question_index + 1}</strong><br>${escapeHtml(item.feedback)}<br><small>Logrado: ${escapeHtml(item.achieved_points.join(", ") || "—")} · Falta: ${escapeHtml(item.missing_points.join(", ") || "—")}</small></div>`).join("");
    byId("feedback-output").innerHTML = closed + open || "No hubo respuestas para revisar.";
    showNotice("Retroalimentación lista.", "success");
    } catch (error) { showNotice(error.message, "error"); }
  });
});
