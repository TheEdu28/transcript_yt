const TOKEN_KEY = "aulavideo_token";
const USER_KEY  = "aulavideo_user";

export const auth = {
  save(token, user) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); },
  token()  { return localStorage.getItem(TOKEN_KEY); },
  user()   { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } },
  clear()  { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
  isLoggedIn() { return Boolean(this.token()); },
};

export async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = auth.token();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(`/api/v1${path}`, { ...options, headers });
  if (response.status === 401) { auth.clear(); window.location.assign("/ui/auth/"); return; }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail?.message || `Error ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** Obtiene la lista de modelos LLM disponibles en el servidor. */
export async function fetchModels() { return request("/models"); }

// --- Auth ---
export async function apiRegister(nombre, email, password) {
  return request("/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nombre, email, password }) });
}
export async function apiLogin(email, password) {
  return request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
}
export async function apiMe() { return request("/auth/me"); }

// --- Groups ---
export async function apiCreateGroup(name) {
  return request("/groups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
}
export async function apiListGroups() { return request("/groups"); }
export async function apiGetGroup(id) { return request(`/groups/${id}`); }
export async function apiUpdateGroup(id, name) {
  return request(`/groups/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
}
export async function apiAddMember(groupId, userId) {
  return request(`/groups/${groupId}/members`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
}
export async function apiRemoveMember(groupId, userId) {
  return request(`/groups/${groupId}/members/${userId}`, { method: "DELETE" });
}

// --- Topics ---
export async function apiCreateTopic(groupId, title, description, videoId) {
  return request(`/groups/${groupId}/topics`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, description: description || "", is_published: true, video_id: videoId || null }) });
}
export async function apiListTopics(groupId) { return request(`/groups/${groupId}/topics`); }
export async function apiUpdateTopic(groupId, topicId, fields) {
  return request(`/groups/${groupId}/topics/${topicId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) });
}
export async function apiDeleteTopic(groupId, topicId) {
  return request(`/groups/${groupId}/topics/${topicId}`, { method: "DELETE" });
}

// --- Videos ---
export async function apiListMyVideos(page = 1, pageSize = 20, status = null) {
  const params = `page=${page}&page_size=${pageSize}${status ? `&status=${status}` : ""}`;
  return request(`/videos?${params}`);
}
export async function apiDeleteVideo(videoId) {
  return request(`/videos/${videoId}`, { method: "DELETE" });
}
export async function apiPublishVideoAsTopic(groupId, videoId, title, description) {
  return request(`/groups/${groupId}/topics`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, description: description || "", is_published: true, video_id: videoId }) });
}
