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

  const badges = document.createElement("div");
  badges.className = "profile-badges";

  if (profile.is_default) {
    const badge = document.createElement("span");
    badge.className = "profile-badge";
    badge.textContent = "Predeterminado";
    badges.append(badge);
  }

  const providerLabel = profile.provider_id
    ? `${profile.provider_id.toUpperCase()}${profile.model_override ? ` (${profile.model_override})` : ""}`
    : "IA Global";
  const provBadge = document.createElement("span");
  provBadge.className = "profile-badge provider-badge";
  provBadge.textContent = providerLabel;
  badges.append(provBadge);

  content.append(badges);
  const button = document.createElement("button"); button.type = "button"; button.textContent = "Editar"; button.addEventListener("click", () => openProfile(profile));
  article.append(content, button); return article;
}

async function loadProfiles() {
  const data = await requestJson("/api/ai-profiles");
  list.replaceChildren(...data.items.map(profileCard));
}

const PROVIDER_MODELS = {
  gemini: ["gemini-3.6-flash", "gemini-3.1-pro-preview", "gemini-1.5-flash", "gemini-1.5-pro"],
  openrouter: ["google/gemini-2.5-flash", "google/gemini-2.5-pro", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"],
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "o3-mini"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  openclaw: ["openclaw"],
};

const profileProviderSelect = document.querySelector("#profile-provider");
const profileModelSelect = document.querySelector("#profile-model-select");
const profileModelInput = document.querySelector("#profile-model");

function updateProfileModelSelect(providerId, currentModel = "") {
  if (!profileModelSelect) return;
  profileModelSelect.innerHTML = "";
  
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "-- Seleccionar de la lista de sugeridos --";
  profileModelSelect.appendChild(defaultOpt);

  const modelsList = PROVIDER_MODELS[providerId] || [];
  modelsList.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    profileModelSelect.appendChild(opt);
  });

  const customOpt = document.createElement("option");
  customOpt.value = "custom";
  customOpt.textContent = "✍️ Escribir modelo personalizado...";
  profileModelSelect.appendChild(customOpt);

  if (currentModel && modelsList.includes(currentModel)) {
    profileModelSelect.value = currentModel;
  } else if (currentModel) {
    profileModelSelect.value = "custom";
  } else {
    profileModelSelect.value = "";
  }
}

if (profileProviderSelect && profileModelSelect) {
  profileProviderSelect.addEventListener("change", (e) => {
    updateProfileModelSelect(e.target.value, profileModelInput.value);
  });
}

if (profileModelSelect && profileModelInput) {
  profileModelSelect.addEventListener("change", (e) => {
    if (e.target.value && e.target.value !== "custom") {
      profileModelInput.value = e.target.value;
    }
  });

  profileModelInput.addEventListener("input", () => {
    const val = profileModelInput.value.trim();
    const providerId = profileProviderSelect.value;
    const modelsList = PROVIDER_MODELS[providerId] || [];
    if (modelsList.includes(val)) {
      profileModelSelect.value = val;
    } else if (val) {
      profileModelSelect.value = "custom";
    } else {
      profileModelSelect.value = "";
    }
  });
}

function openProfile(profile = null) {
  form.hidden = false;
  document.querySelector("#profile-id").value = profile?.id || "";
  document.querySelector("#profile-name").value = profile?.name || "";
  document.querySelector("#profile-description").value = profile?.description || "";
  const providerVal = profile?.provider_id || "";
  const modelVal = profile?.model_override || "";
  document.querySelector("#profile-provider").value = providerVal;
  document.querySelector("#profile-model").value = modelVal;
  updateProfileModelSelect(providerVal, modelVal);
  document.querySelector("#profile-prompt").value = profile?.prompt || "";
  document.querySelector("#profile-default").checked = Boolean(profile?.is_default);
  document.querySelector("#profile-form-title").textContent = profile ? "Editar perfil" : "Nuevo perfil";
  document.querySelector("#archive-profile").hidden = !profile;
  document.querySelector("#profile-feedback").textContent = "";
  document.querySelector("#profile-name").focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); const id = document.querySelector("#profile-id").value;
  const payload = {
    name: document.querySelector("#profile-name").value,
    description: document.querySelector("#profile-description").value,
    provider_id: document.querySelector("#profile-provider").value || null,
    model_override: document.querySelector("#profile-model").value || null,
    prompt: document.querySelector("#profile-prompt").value,
    is_default: document.querySelector("#profile-default").checked,
  };
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
