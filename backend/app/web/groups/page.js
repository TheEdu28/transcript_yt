import { apiCreateGroup, apiGetMyGroups, apiJoinGroup } from "/ui/api.js";
import { escapeHtml, renderUserBar, requireAuth, runWithButtonDisabled, showNotice, showToast, urlFor } from "/ui/shared.js";

requireAuth();
renderUserBar();

const byId = (id) => document.getElementById(id);

function renderGroupCard(g, roleLabel, isAdmin) {
  const badgeStyle = isAdmin
    ? "background:#e8eeff;color:var(--blue);border:1px solid #c9d5fa"
    : "background:#f1f5f9;color:#475569;border:1px solid #e2e8f0";

  return `
    <article class="group-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <a href="${urlFor("/ui/groups/detail/", { group: g.id })}" style="color:var(--ink);text-decoration:none;font-weight:700;font-size:15px;line-height:1.3;flex:1" class="group-title-link">
          ${escapeHtml(g.name)}
        </a>
        <span class="badge" style="font-size:11px;padding:2px 8px;border-radius:99px;${badgeStyle}">${roleLabel}</span>
      </div>
      <div class="group-card-meta" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
        <span style="display:inline-flex;align-items:center;gap:6px">
          Código:
          <strong class="group-code-tag" style="font-size:13px;background:#eef4ff;padding:2px 7px;border-radius:6px;border:1px solid #c9d5fa;color:var(--blue);font-family:monospace">
            ${escapeHtml(g.code)}
          </strong>
        </span>
        <button type="button" class="secondary copy-card-code-btn" data-code="${escapeHtml(g.code)}" style="padding:2px 8px;font-size:11px;min-height:auto" title="Copiar código del grupo">
          Copiar
        </button>
      </div>
      <div style="margin-top:10px;padding-top:10px;border-top:1px solid #f1f5f9;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:11px;color:var(--muted)">Creado: ${g.created_at ? new Date(g.created_at).toLocaleDateString("es") : "—"}</span>
        <a href="${urlFor("/ui/groups/detail/", { group: g.id })}" style="font-size:12px;font-weight:700;color:var(--blue);text-decoration:none">
          Entrar al aula →
        </a>
      </div>
    </article>`;
}

async function loadGroups() {
  const list = byId("groups-list");
  if (!list) return;

  try {
    const res = await apiGetMyGroups();
    const adminGroups = res.admin_groups || [];
    const memberGroups = res.member_groups || [];

    if (!adminGroups.length && !memberGroups.length) {
      list.className = "empty-state";
      list.innerHTML = `
        <div style="max-width:440px;margin:12px auto;text-align:center">
          <svg class="ui-icon" style="width:36px;height:36px;color:var(--muted);margin-bottom:8px" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <p style="margin:0 0 6px;font-weight:700;color:var(--ink)">Aún no perteneces a ningún grupo</p>
          <p style="margin:0;font-size:13px;color:var(--muted)">
            Como docente, puedes <strong>crear un grupo</strong> arriba para invitar a tus alumnos. Como estudiante, pide el código de 6 caracteres a tu profesor e ingrésalo en <strong>Unirse con código</strong>.
          </p>
        </div>
      `;
      return;
    }

    list.className = "groups-grid";
    let html = "";
    if (adminGroups.length) {
      html += adminGroups.map((g) => renderGroupCard(g, "Administrador", true)).join("");
    }
    if (memberGroups.length) {
      html += memberGroups.map((g) => renderGroupCard(g, "Miembro", false)).join("");
    }
    list.innerHTML = html;

    list.querySelectorAll(".copy-card-code-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const code = btn.dataset.code;
        if (!code) return;
        navigator.clipboard?.writeText(code).then(
          () => showToast(`¡Código ${code} copiado al portapapeles!`, "success"),
          () => showToast(`Código de grupo: ${code}`, "info")
        );
      });
    });
  } catch (err) {
    showNotice(err.message, "error");
  }
}

byId("create-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = byId("group-name");
  const name = input.value.trim();
  if (!name) return;

  await runWithButtonDisabled(byId("create-btn"), async () => {
    try {
      const created = await apiCreateGroup(name);
      input.value = "";
      showNotice(`¡Grupo «${created.name}» creado con éxito! Código de acceso: ${created.code}`, "success");
      await loadGroups();
    } catch (err) {
      showNotice(err.message, "error");
    }
  });
});

byId("join-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = byId("join-code");
  const code = input.value.trim().toUpperCase();
  if (!code) return;

  await runWithButtonDisabled(byId("join-btn"), async () => {
    try {
      await apiJoinGroup(code);
      input.value = "";
      showNotice("¡Te has unido al grupo con éxito!", "success");
      await loadGroups();
    } catch (err) {
      showNotice(err.message, "error");
    }
  });
});

loadGroups();
