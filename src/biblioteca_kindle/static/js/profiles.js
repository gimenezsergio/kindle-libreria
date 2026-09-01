const list = document.querySelector("#profile-list");
const form = document.querySelector("#profile-form");

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "No se pudo guardar el perfil");
  return data;
}

function profileCard(profile) {
  const article = document.createElement("article");
  article.className = "profile-card";
  const content = document.createElement("div");
  const title = document.createElement("h2"); title.textContent = profile.name;
  const description = document.createElement("p"); description.textContent = profile.description || "Sin descripción";
  content.append(title, description);
  if (profile.is_default) { const badge = document.createElement("span"); badge.className = "profile-badge"; badge.textContent = "Predeterminado"; content.append(badge); }
  const button = document.createElement("button"); button.type = "button"; button.textContent = "Editar"; button.addEventListener("click", () => openProfile(profile));
  article.append(content, button); return article;
}

async function loadProfiles() {
  const data = await requestJson("/api/ai-profiles");
  list.replaceChildren(...data.items.map(profileCard));
}

function openProfile(profile = null) {
  form.hidden = false;
  document.querySelector("#profile-id").value = profile?.id || "";
  document.querySelector("#profile-name").value = profile?.name || "";
  document.querySelector("#profile-description").value = profile?.description || "";
  document.querySelector("#profile-prompt").value = profile?.prompt || "";
  document.querySelector("#profile-default").checked = Boolean(profile?.is_default);
  document.querySelector("#profile-form-title").textContent = profile ? "Editar perfil" : "Nuevo perfil";
  document.querySelector("#archive-profile").hidden = !profile;
  document.querySelector("#profile-feedback").textContent = "";
  document.querySelector("#profile-name").focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); const id = document.querySelector("#profile-id").value;
  const payload = {name: document.querySelector("#profile-name").value, description: document.querySelector("#profile-description").value, prompt: document.querySelector("#profile-prompt").value, is_default: document.querySelector("#profile-default").checked};
  try { await requestJson(id ? `/api/ai-profiles/${encodeURIComponent(id)}` : "/api/ai-profiles", {method: id ? "PATCH" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}); form.hidden = true; await loadProfiles(); }
  catch (error) { document.querySelector("#profile-feedback").textContent = error.message; }
});

document.querySelector("#archive-profile").addEventListener("click", async () => {
  const id = document.querySelector("#profile-id").value;
  try { await requestJson(`/api/ai-profiles/${encodeURIComponent(id)}`, {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({is_archived: true, is_default: false})}); form.hidden = true; await loadProfiles(); }
  catch (error) { document.querySelector("#profile-feedback").textContent = error.message; }
});
document.querySelector("#new-profile").addEventListener("click", () => openProfile());
document.querySelector("#close-profile").addEventListener("click", () => { form.hidden = true; });
loadProfiles();
