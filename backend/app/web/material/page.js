import { request } from "/ui/api.js";
import { escapeHtml, getPositiveIntParam, renderUserBar, requireAuth, replaceUrl, runWithButtonDisabled, showNotice, urlFor } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);
const videoId = getPositiveIntParam("video");
const initialMaterialId = getPositiveIntParam("material");
let currentType = null;

function renderLastEditor(material) {
  const editor = material.last_edited_by_name || (material.last_edited_by ? `usuario ${material.last_edited_by}` : null);
  byId("last-editor").textContent = editor
    ? `Última edición: ${editor}${material.last_edited_at ? ` · ${new Date(material.last_edited_at).toLocaleString("es")}` : ""}`
    : "Última edición: todavía no se ha editado.";
}

function setNavigation(video, material) {
  if (!video) return;
  byId("video-label").textContent = `Video ID: ${video}`;
  byId("summary-link").href = urlFor("/ui/resumen/", { video });
  byId("quiz-link").href = urlFor("/ui/quiz/", { video, material });
}

// --- Helpers para construir filas del formulario ---

function glossaryRowHtml(item = {}, index) {
  return `<div class="editor-row" data-index="${index}">
    <div class="editor-row-fields">
      <label>Término<input class="g-term" type="text" value="${escapeHtml(item.term || "")}" placeholder="Término"></label>
      <label>Definición<input class="g-def" type="text" value="${escapeHtml(item.definition || "")}" placeholder="Definición"></label>
      <label>Timestamp<input class="g-ts" type="text" value="${escapeHtml(item.timestamp || "")}" placeholder="00:00:00" pattern="\\d{2}:\\d{2}:\\d{2}"></label>
    </div>
    <button type="button" class="row-delete" title="Eliminar">✕</button>
  </div>`;
}

function blockRowHtml(item = {}, index) {
  const timestamps = (item.timestamps || []).join(", ");
  return `<div class="editor-row" data-index="${index}">
    <div class="editor-row-fields">
      <label>Título<input class="b-title" type="text" value="${escapeHtml(item.title || "")}" placeholder="Título del bloque"></label>
      <label style="grid-column:1/3">Explicación<textarea class="b-exp" rows="2">${escapeHtml(item.explanation || "")}</textarea></label>
      <label>Timestamps (separados por coma)<input class="b-ts" type="text" value="${escapeHtml(timestamps)}" placeholder="00:01:00, 00:02:30"></label>
    </div>
    <button type="button" class="row-delete" title="Eliminar">✕</button>
  </div>`;
}

function attachDeleteListeners(container) {
  container.querySelectorAll(".row-delete").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest(".editor-row").remove());
  });
}

function renderSummaryForm(content) {
  byId("field-synopsis").value = content.synopsis || "";

  const glossaryEl = byId("glossary-items");
  glossaryEl.innerHTML = (content.glossary || []).map((item, i) => glossaryRowHtml(item, i)).join("");
  attachDeleteListeners(glossaryEl);

  const blockEl = byId("block-items");
  blockEl.innerHTML = (content.didactic_blocks || []).map((item, i) => blockRowHtml(item, i)).join("");
  attachDeleteListeners(blockEl);

  byId("summary-editor").style.display = "";
}

function collectSummaryContent() {
  const glossary = [...byId("glossary-items").querySelectorAll(".editor-row")].map((row) => ({
    term: row.querySelector(".g-term").value.trim(),
    definition: row.querySelector(".g-def").value.trim(),
    timestamp: row.querySelector(".g-ts").value.trim(),
  })).filter((g) => g.term);

  const didactic_blocks = [...byId("block-items").querySelectorAll(".editor-row")].map((row) => ({
    title: row.querySelector(".b-title").value.trim(),
    explanation: row.querySelector(".b-exp").value.trim(),
    timestamps: row.querySelector(".b-ts").value.split(",").map((t) => t.trim()).filter(Boolean),
  })).filter((b) => b.title);

  return {
    synopsis: byId("field-synopsis").value.trim(),
    glossary,
    didactic_blocks,
    evidence_sufficient: true,
    insufficiency_note: null,
  };
}

// --- Cargar material ---
async function loadMaterial(id) {
  const material = await request(`/materials/${id}`);
  currentType = material.material_type;
  renderLastEditor(material);
  setNavigation(material.video_id, material.id);
  replaceUrl("/ui/material/", { video: material.video_id, material: material.id });
  byId("material-id").value = material.id;

  if (material.material_type === "summary") {
    renderSummaryForm(material.content);
    showNotice(`Resumen ${id} cargado para edición.`, "success");
  } else {
    byId("summary-editor").style.display = "none";
    showNotice("Los cuestionarios no tienen edición estructurada aún. Usa la API directamente.", "");
  }
}

// --- Agregar filas ---
byId("add-glossary").addEventListener("click", () => {
  const el = byId("glossary-items");
  const div = document.createElement("div");
  div.innerHTML = glossaryRowHtml({}, el.children.length);
  const row = div.firstElementChild;
  attachDeleteListeners(row);
  el.appendChild(row);
});

byId("add-block").addEventListener("click", () => {
  const el = byId("block-items");
  const div = document.createElement("div");
  div.innerHTML = blockRowHtml({}, el.children.length);
  const row = div.firstElementChild;
  attachDeleteListeners(row);
  el.appendChild(row);
});

// --- Guardar ---
byId("save-button").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Carga un material primero.", "error");
  await runWithButtonDisabled(byId("save-button"), async () => {
    try {
      const content = collectSummaryContent();
      const updated = await request(`/materials/${materialId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      renderLastEditor(updated);
      showNotice("Edición guardada y versión anterior archivada.", "success");
    } catch (err) { showNotice(err.message, "error"); }
  });
});

// --- Historial de versiones ---
byId("versions-button").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return;
  const panel = byId("versions-panel");
  panel.style.display = panel.style.display === "none" ? "" : "none";
  if (panel.style.display === "none") return;
  try {
    const { versions } = await request(`/materials/${materialId}/versions`);
    const list = byId("versions-list");
    if (!versions.length) { list.className = "empty-state"; list.textContent = "Sin versiones anteriores."; return; }
    list.className = "";
    list.innerHTML = versions.map((v) => `
      <div class="version-row">
        <span class="version-date">${new Date(v.edited_at).toLocaleString("es")}</span>
        <span class="version-user">por ${escapeHtml(v.edited_by_name || `usuario ${v.edited_by ?? "—"}`)}</span>
        <button type="button" class="secondary restore-version" data-version-id="${v.id}">Restaurar</button>
      </div>`).join("");
    list.querySelectorAll(".restore-version").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!window.confirm("¿Restaurar esta versión? El contenido actual se conservará en el historial.")) return;
        await runWithButtonDisabled(button, async () => {
          try {
            const restored = await request(`/materials/${materialId}/versions/${button.dataset.versionId}/restore`, { method: "POST" });
            renderLastEditor(restored);
            renderSummaryForm(restored.content);
            showNotice("Versión restaurada. El estado anterior también fue archivado.", "success");
            byId("versions-button").click();
          } catch (err) { showNotice(err.message, "error"); }
        });
      });
    });
  } catch (err) { showNotice(err.message, "error"); }
});

// --- Exportar ---
byId("export-button").addEventListener("click", () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Carga un material primero.", "error");
  window.open(`/api/v1/materials/${materialId}/export?format=markdown`, "_blank", "noopener");
});

// --- Cargar al inicio ---
byId("load-button").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Ingresa un Material ID válido.", "error");
  try { await loadMaterial(materialId); } catch (err) { showNotice(err.message, "error"); }
});

setNavigation(videoId, initialMaterialId);
if (initialMaterialId) loadMaterial(initialMaterialId).catch((err) => showNotice(err.message, "error"));
else showNotice("Usa ?material=17 o escribe el identificador del recurso.");
