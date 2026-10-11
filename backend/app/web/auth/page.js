import { auth, apiLogin, apiMe, apiRegister } from "/ui/api.js";
import { runWithButtonDisabled, showNotice } from "/ui/shared.js";

// Si ya hay sesión válida, saltar directo a grupos
if (auth.isLoggedIn()) window.location.assign("/ui/groups/");

const byId = (id) => document.getElementById(id);

function noticeVisible(msg, type) {
  const el = byId("notice");
  el.textContent = msg;
  el.className = `notice ${type}`.trim();
  el.style.display = "";
}

function switchTab(tabName) {
  document.querySelectorAll(".auth-choice").forEach((t) => {
    const active = t.dataset.tab === tabName;
    t.classList.toggle("auth-choice--active", active);
    t.classList.toggle("secondary", !active);
    t.setAttribute("aria-selected", String(active));
  });
  byId("login-form").style.display    = tabName === "login"    ? "" : "none";
  byId("register-form").style.display = tabName === "register" ? "" : "none";
  byId("notice").style.display = "none";
}

// --- Tabs (solo escuchar clicks en botones secundarios de cambio de pestaña) ---
document.querySelectorAll(".auth-choice[type='button']").forEach((tab) => {
  tab.addEventListener("click", () => {
    switchTab(tab.dataset.tab);
  });
});

// --- Login ---
byId("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("login-btn"), async () => {
    try {
      const email = byId("login-email").value.trim().toLowerCase();
      const password = byId("login-password").value;
      const res = await apiLogin(email, password);
      if (!res?.access_token) {
        throw new Error("No se recibió el token de autenticación.");
      }
      auth.save(res.access_token, {});
      const user = await apiMe();
      auth.save(res.access_token, user);
      window.location.assign("/ui/groups/");
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});

// --- Registro con auto-login fluido ---
byId("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("register-btn"), async () => {
    try {
      const name = byId("reg-name").value.trim();
      const email = byId("reg-email").value.trim().toLowerCase();
      const password = byId("reg-password").value;

      await apiRegister(name, email, password);

      // Iniciar sesión automáticamente con las credenciales registradas
      try {
        const { access_token } = await apiLogin(email, password);
        auth.save(access_token, {});
        const user = await apiMe();
        auth.save(access_token, user);
        window.location.assign("/ui/groups/");
        return;
      } catch (loginErr) {
        // Fallback si por alguna razón falla el login automático
        switchTab("login");
        byId("login-email").value = email;
        byId("login-password").value = "";
        byId("login-password").focus();
        noticeVisible("Cuenta creada exitosamente. Ingresa tu contraseña para acceder.", "success");
      }
    } catch (err) {
      noticeVisible(err.message, "error");
    }
  });
});
