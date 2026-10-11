import { apiCreateGroup, apiGetMyGroups, apiJoinGroup } from "/ui/api.js";
import { escapeHtml, renderUserBar, requireAuth, runWithButtonDisabled, urlFor } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);

function noticeVisible(msg, type) {
  const el = byId("notice");
  el.textContent = msg;
  el.className = `notice ${type}`.trim();
  el.style.display = "";
}

function renderGroupCard(g, roleLabel) {
  return `
    <a class="group-card" href="${urlFor("/ui/groups/detail/", { group: g.id })}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <strong>${escapeHtml(g.name)}</strong>
        <span class="badge" style="font-size:0.75rem;padding:2px 8px;border-radius:12px;background:#f0f0f0">${roleLabel}</span>
      </div>
      <div class="group-card-meta" style="font-size:0.85rem;color:#666;display:flex;justify-content:space-between;align-items:center;margin-top:4px">
        <span>Código: <strong class="group-code-tag" style="font-size:14px;background:#eef4ff;padding:2px 8px;border-radius:6px;border:1px solid #c9d5fa">${escapeHtml(g.code)}</strong></span>
        <span>${new Date(g.created_at).toLocaleDateString("es")}</span>
      </div>
    </a>`;
}

async function loadGroups() {
  try {
    const res = await apiGetMyGroups();
    const list = byId("groups-list");
    const adminGroups = res.admin_groups || [];
    const memberGroups = res.member_groups || [];

    if (!adminGroups.length && !memberGroups.length) {
      list.className = "empty-state";
      list.textContent = "Aún no perteneces a ningún grupo. Crea uno o únete con un código arriba.";
      return;
    }

    list.className = "groups-grid";
    let html = "";
    if (adminGroups.length) {
      html += adminGroups.map((g) => renderGroupCard(g, "Administrador")).join("");
    }
    if (memberGroups.length) {
      html += memberGroups.map((g) => renderGroupCard(g, "Miembro")).join("");
    }
    list.innerHTML = html;
  } catch (err) {
    noticeVisible(err.message, "error");
  }
}

byId("create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("create-btn"), async () => {
    try {
      const created = await apiCreateGroup(byId("group-name").value.trim());
      byId("group-name").value = "";
      noticeVisible(`¡Grupo "${created.name}" creado con éxito! Código de acceso: ${created.code}`, "success");
      await loadGroups();
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

byId("join-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("join-btn"), async () => {
    try {
      const code = byId("join-code").value.trim().toUpperCase();
      await apiJoinGroup(code);
      byId("join-code").value = "";
      noticeVisible("Te has unido al grupo con éxito.", "success");
      await loadGroups();
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

loadGroups();

