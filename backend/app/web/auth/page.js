import { auth, apiLogin, apiMe, apiRegister } from "/ui/api.js";
import { runWithButtonDisabled, showNotice } from "/ui/shared.js";

// Si ya hay sesión válida, saltar directo a grupos
if (auth.isLoggedIn()) window.location.assign("/ui/groups/");

const byId = (id) => document.getElementById(id);

// --- Tabs ---
document.querySelectorAll(".auth-choice[data-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-choice").forEach((t) => {
      const active = t.dataset.tab === tab.dataset.tab;
      t.classList.toggle("auth-choice--active", active);
      t.classList.toggle("secondary", !active);
      t.setAttribute("aria-selected", String(active));
    });
    byId("login-form").style.display    = tab.dataset.tab === "login"    ? "" : "none";
    byId("register-form").style.display = tab.dataset.tab === "register" ? "" : "none";
    byId("notice").style.display = "none";
  });
});

function noticeVisible(msg, type) {
  const el = byId("notice");
  el.textContent = msg;
  el.className = `notice ${type}`.trim();
  el.style.display = "";
}

// --- Login ---
byId("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("login-btn"), async () => {
    try {
      const { access_token } = await apiLogin(byId("login-email").value, byId("login-password").value);
      // Guardar token primero, luego obtener perfil
      auth.save(access_token, {});
      const user = await apiMe();
      auth.save(access_token, user);
      window.location.assign("/ui/groups/");
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});

// --- Registro ---
byId("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("register-btn"), async () => {
    try {
      await apiRegister(byId("reg-name").value, byId("reg-email").value, byId("reg-password").value);
      noticeVisible("Cuenta creada. Ahora inicia sesión.", "success");
      // Cambiar a tab login
      document.querySelector("#login-form [data-tab='login']").click();
      byId("login-email").value = byId("reg-email").value;
    } catch (err) { noticeVisible(err.message, "error"); }
  });
});
