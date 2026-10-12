import { apiListMyMaterials, auth, request } from "/ui/api.js";
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

// --- Helpers para construir filas del formulario de resumen ---

function glossaryRowHtml(item = {}, index) {
  return `<div class="editor-row" data-index="${index}">
    <div class="editor-row-fields">
      <label>Término<input class="g-term" type="text" value="${escapeHtml(item.term || "")}" placeholder="Término"></label>
      <label>Definición<input class="g-def" type="text" value="${escapeHtml(item.definition || "")}" placeholder="Definición"></label>
      <label>Timestamp<input class="g-ts" type="text" value="${escapeHtml(item.timestamp || "")}" placeholder="00:00:00" pattern="\\d{2}:\\d{2}:\\d{2}"></label>
    </div>
    <button type="button" class="row-delete" title="Eliminar"><svg class="ui-icon" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
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
    <button type="button" class="row-delete" title="Eliminar"><svg class="ui-icon" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
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

function renderQuizViewer(content) {
  const container = byId("quiz-viewer-content");
  if (!container) return;

  const multipleChoice = content.multiple_choice || [];
  const openQuestions = content.open_questions || [];

  let html = "";

  if (multipleChoice.length) {
    html += `<div style="margin-bottom:12px"><h3 style="font-size:16px;margin:0 0 10px;color:var(--text)">Preguntas de Opción Múltiple (${multipleChoice.length})</h3><div class="stack" style="gap:12px">`;
    html += multipleChoice.map((q, idx) => {
      const optionsHtml = (q.options || []).map((opt, optIdx) => {
        const isCorrect = optIdx === q.correct_option;
        return `
          <div style="padding:6px 10px;margin-top:4px;border-radius:6px;border:1px solid ${isCorrect ? '#86efac' : '#e2e8f0'};background:${isCorrect ? '#f0fdf4' : '#fff'};font-size:13px;display:flex;align-items:center;justify-content:space-between">
            <span><strong>${String.fromCharCode(65 + optIdx)})</strong> ${escapeHtml(opt)}</span>
            ${isCorrect ? `<span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;font-weight:700;color:#16a34a;background:#dcfce7;padding:1px 6px;border-radius:4px"><svg class="ui-icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Correcta</span>` : ""}
          </div>
        `;
      }).join("");

      return `
        <div class="panel" style="background:#f8fafc;padding:14px;border-radius:10px;border:1px solid #e2e8f0">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <strong style="font-size:14px">${idx + 1}. ${escapeHtml(q.question)}</strong>
            <span style="font-size:11px;background:#e0e7ff;color:#3730a3;padding:2px 6px;border-radius:4px;white-space:nowrap">${escapeHtml(q.bloom_level || "")}</span>
          </div>
          <div style="margin-top:8px">${optionsHtml}</div>
          <div style="margin-top:8px;font-size:12px;color:var(--muted)">
            <em>Explicación:</em> ${escapeHtml(q.explanation || "N/A")} · 
            <strong>Timestamp:</strong> <code>${escapeHtml(q.evidence_timestamp || "")}</code>
          </div>
        </div>
      `;
    }).join("");
    html += `</div></div>`;
  }

  if (openQuestions.length) {
    html += `<div style="margin-top:16px"><h3 style="font-size:16px;margin:0 0 10px;color:var(--text)">Preguntas Abiertas (${openQuestions.length})</h3><div class="stack" style="gap:12px">`;
    html += openQuestions.map((q, idx) => {
      const pointsHtml = (q.expected_points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
      return `
        <div class="panel" style="background:#f8fafc;padding:14px;border-radius:10px;border:1px solid #e2e8f0">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <strong style="font-size:14px">${idx + 1}. ${escapeHtml(q.question)}</strong>
            <span style="font-size:11px;background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;white-space:nowrap">${escapeHtml(q.bloom_level || "")}</span>
          </div>
          <div style="margin-top:8px;font-size:13px">
            <span style="font-weight:600;color:var(--muted)">Puntos esperados:</span>
            <ul style="margin:4px 0 0 20px;padding:0">${pointsHtml}</ul>
          </div>
          <div style="margin-top:8px;font-size:12px;color:var(--muted)">
            <strong>Timestamp:</strong> <code>${escapeHtml(q.evidence_timestamp || "")}</code>
          </div>
        </div>
      `;
    }).join("");
    html += `</div></div>`;
  }

  container.innerHTML = html;
  byId("quiz-viewer").style.display = "";
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

  const select = byId("material-select");
  if (select && select.value !== String(material.id)) {
    select.value = String(material.id);
  }

  if (material.material_type === "summary") {
    byId("quiz-viewer").style.display = "none";
    renderSummaryForm(material.content);
    showNotice(`Resumen #${id} cargado con éxito.`, "success");
  } else if (material.material_type === "quiz") {
    byId("summary-editor").style.display = "none";
    renderQuizViewer(material.content);
    showNotice(`Cuestionario #${id} cargado con éxito.`, "success");
  } else {
    byId("summary-editor").style.display = "none";
    byId("quiz-viewer").style.display = "none";
    showNotice(`Material #${id} (${material.material_type}) cargado.`, "info");
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

// --- Exportar mediante Blob ---
async function downloadExport(format) {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Carga un material primero antes de exportar.", "error");

  const btnId = `export-${format === "markdown" ? "md" : format}-btn`;
  const btn = byId(btnId);

  await runWithButtonDisabled(btn || byId("load-button"), async () => {
    try {
      showNotice(`Generando archivo ${format.toUpperCase()}…`, "info");
      const token = auth.token();
      const headers = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`/api/v1/materials/${materialId}/export?format=${format}`, { headers });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail?.message || `Error al exportar (${res.status})`);
      }

      const blob = await res.blob();
      const extMap = { markdown: "md", pdf: "pdf", docx: "docx", json: "json" };
      const filename = `material_${materialId}.${extMap[format] || format}`;

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
      showNotice(`Error en la exportación: ${err.message}`, "error");
    }
  });
}

byId("export-md-btn")?.addEventListener("click", () => downloadExport("markdown"));
byId("export-pdf-btn")?.addEventListener("click", () => downloadExport("pdf"));
byId("export-docx-btn")?.addEventListener("click", () => downloadExport("docx"));

// --- Desplegable de materiales disponibles ---
async function populateMaterialsDropdown() {
  const select = byId("material-select");
  if (!select) return;

  try {
    const list = await apiListMyMaterials();
    if (!list || !list.length) {
      select.innerHTML = '<option value="">No hay materiales generados aún</option>';
      return;
    }

    let options = '<option value="">-- Elige un material generado (' + list.length + ') --</option>';
    options += list.map((m) => {
      const typeLabel = m.material_type === "summary" ? "Resumen" : "Cuestionario";
      return `<option value="${m.id}">Material #${m.id} · ${typeLabel} (Video #${m.video_id})</option>`;
    }).join("");

    select.innerHTML = options;

    if (initialMaterialId) {
      select.value = String(initialMaterialId);
    }
  } catch (err) {
    select.innerHTML = '<option value="">Error al cargar lista</option>';
    console.warn("No se pudo cargar lista de materiales:", err);
  }
}

byId("material-select")?.addEventListener("change", (e) => {
  const val = Number(e.target.value);
  if (val) {
    byId("material-id").value = val;
    loadMaterial(val).catch((err) => showNotice(err.message, "error"));
  }
});

// --- Cargar al inicio ---
byId("load-button").addEventListener("click", async () => {
  const materialId = Number(byId("material-id").value);
  if (!materialId) return showNotice("Ingresa un Material ID válido.", "error");
  try { await loadMaterial(materialId); } catch (err) { showNotice(err.message, "error"); }
});

setNavigation(videoId, initialMaterialId);
populateMaterialsDropdown();

if (initialMaterialId) {
  loadMaterial(initialMaterialId).catch((err) => showNotice(err.message, "error"));
} else {
  showNotice("Selecciona un material arriba o escribe su ID para editarlo o exportarlo.");
}
