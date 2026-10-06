import { apiCreateGroup, apiListGroups } from "/ui/api.js";
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

async function loadGroups() {
  try {
    const groups = await apiListGroups();
    const list = byId("groups-list");
    if (!groups.length) { list.className = "empty-state"; list.textContent = "Aún no perteneces a ningún grupo. Crea uno arriba."; return; }
    list.className = "groups-grid";
    list.innerHTML = groups.map((g) => `
      <a class="group-card" href="${urlFor("/ui/groups/detail/", { group: g.id })}">
        <strong>${escapeHtml(g.name)}</strong>
        <span class="group-card-meta">ID ${g.id} · creado ${new Date(g.created_at).toLocaleDateString("es")}</span>
      </a>`).join("");
  } catch (err) { noticeVisible(err.message, "error"); }
}

byId("create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("create-btn"), async () => {
    try {
      await apiCreateGroup(byId("group-name").value.trim());
      byId("group-name").value = "";
      await loadGroups();
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});

loadGroups();
