import { auth, apiLogin, apiMe, apiRegister } from "/ui/api.js";
import { runWithButtonDisabled, showNotice } from "/ui/shared.js";

// Si ya hay sesión válida, saltar directo a grupos
if (auth.isLoggedIn()) {
  window.location.assign("/ui/groups/");
}

const byId = (id) => document.getElementById(id);

function switchTab(tabName) {
  const isLogin = tabName === "login";
  byId("tab-login")?.classList.toggle("auth-tab-btn--active", isLogin);
  byId("tab-login")?.setAttribute("aria-selected", String(isLogin));

  byId("tab-register")?.classList.toggle("auth-tab-btn--active", !isLogin);
  byId("tab-register")?.setAttribute("aria-selected", String(!isLogin));

  byId("login-form").style.display = isLogin ? "" : "none";
  byId("register-form").style.display = isLogin ? "none" : "";

  // Ocultar avisos previos al cambiar de pestaña
  showNotice("");

  if (isLogin) {
    byId("login-email")?.focus();
  } else {
    byId("reg-name")?.focus();
  }
}

// Botones de pestañas superiores
byId("tab-login")?.addEventListener("click", () => switchTab("login"));
byId("tab-register")?.addEventListener("click", () => switchTab("register"));

// Enlaces de texto alternativo al pie
byId("goto-register-link")?.addEventListener("click", () => switchTab("register"));
byId("goto-login-link")?.addEventListener("click", () => switchTab("login"));

// --- Login ---
byId("login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("login-btn"), async () => {
    try {
      const email = byId("login-email").value.trim().toLowerCase();
      const password = byId("login-password").value;
      const res = await apiLogin(email, password);
      if (!res?.access_token) {
        throw new Error("No se recibió el token de autenticación del servidor.");
      }
      auth.save(res.access_token, {});
      const user = await apiMe();
      auth.save(res.access_token, user);
      showNotice("Sesión iniciada correctamente. Redirigiendo…", "success");
      window.location.assign("/ui/groups/");
    } catch (err) {
      showNotice(err.message, "error");
    }
  });
});

// --- Registro con auto-login fluido ---
byId("register-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  await runWithButtonDisabled(byId("register-btn"), async () => {
    try {
      const name = byId("reg-name").value.trim();
      const email = byId("reg-email").value.trim().toLowerCase();
      const password = byId("reg-password").value;

      if (password.length < 8) {
        throw new Error("La contraseña debe tener al menos 8 caracteres.");
      }

      await apiRegister(name, email, password);

      // Iniciar sesión automáticamente con las credenciales registradas
      try {
        const { access_token } = await apiLogin(email, password);
        auth.save(access_token, {});
        const user = await apiMe();
        auth.save(access_token, user);
        showNotice("¡Cuenta creada exitosamente! Redirigiendo a tu aula…", "success");
        window.location.assign("/ui/groups/");
        return;
      } catch {
        // Fallback si por alguna razón falla el login automático
        switchTab("login");
        byId("login-email").value = email;
        byId("login-password").value = "";
        byId("login-password").focus();
        showNotice("Cuenta creada exitosamente. Ingresa tu contraseña para acceder.", "success");
      }
    } catch (err) {
      showNotice(err.message, "error");
    }
  });
});
