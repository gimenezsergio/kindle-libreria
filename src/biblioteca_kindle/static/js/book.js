const formatNumber = new Intl.NumberFormat("es-AR");
const setText = (id, value) => { document.querySelector(`#${id}`).textContent = value; };
const languageNames = {de: "Alemán", en: "Inglés", es: "Español", fr: "Francés", it: "Italiano", pt: "Portugués"};
let annotationPage = 1;
let annotationPages = 1;
let activeConversationId = null;

function languageName(code) {
  const normalized = String(code || "").trim().toLowerCase();
  return languageNames[normalized] || normalized.toUpperCase();
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "No se pudo guardar");
  return data;
}

async function loadBook() {
  const response = await fetch(`/api/works/${encodeURIComponent(window.WORK_ID)}`);
  if (!response.ok) { setText("book-title", "No encontramos esta obra"); return; }
  const book = await response.json();
  document.title = `${book.title} · Biblioteca personal`;
  setText("book-title", book.title);
  setText("original-title", book.original_title);
  document.querySelector("#display-title-input").value = book.display_title || book.title;
  setText("book-author", book.authors || "Autor no disponible");
  setText("identity-state", book.merge_status === "review" ? "Identidad por revisar" : "Ficha de lectura");
  setText("book-annotation-total", formatNumber.format(book.annotations.total));
  const present = book.editions.some((edition) => edition.presence === "present");
  setText("book-presence", present ? "Presente" : "Ausente");
  const languages = [...new Set(book.editions.map((edition) => edition.language).filter(Boolean).map(languageName))];
  const editionTotal = book.editions.length;
  setText("edition-count", languages.join(" · ") || (editionTotal ? `${formatNumber.format(editionTotal)} documento${editionTotal === 1 ? "" : "s"}` : "Sin datos"));
  setText("edition-detail", editionTotal ? `${formatNumber.format(editionTotal)} ${editionTotal === 1 ? "edición registrada" : "ediciones registradas"}` : "El Kindle no expuso datos del documento");
  if (book.progress) {
    setText("progress-position", "Actividad registrada");
    const bits = [];
    if (book.progress.progress_fraction !== null) bits.push(`${Math.round(book.progress.progress_fraction * 100)} % estimado`);
    if (book.progress.words_read !== null) bits.push(`${formatNumber.format(book.progress.words_read)} palabras registradas`);
    setText("progress-detail", bits.join(" · ") || "El Kindle conserva una posición de lectura");
  } else {
    setText("progress-position", "Sin datos");
    setText("progress-detail", "El Kindle no expuso seguimiento para este libro");
  }
  const personalTotal = book.personal.collections + book.personal.notes + book.personal.relations;
  setText("personal-count", personalTotal ? `${formatNumber.format(personalTotal)} ${personalTotal === 1 ? "elemento" : "elementos"}` : "Sin organizar");
  setText("personal-detail", personalTotal ? `${book.personal.collections} colecciones · ${book.personal.notes} notas · ${book.personal.relations} relaciones` : "Podés agregar categorías, notas o relaciones");
}

function annotationCard(annotation) {
  const article = document.createElement("article");
  article.className = `annotation-card ${annotation.kind}`;
  const meta = document.createElement("div");
  meta.className = "annotation-meta";
  const kind = {highlight: "Subrayado", note: "Nota", bookmark: "Marcador"}[annotation.kind] || "Anotación";
  meta.textContent = `${kind} · ${(annotation.sources || "fuente desconocida").toUpperCase()}`;
  if (annotation.reference) {
    const separator = document.createTextNode(" · ");
    const reference = document.createElement("span");
    reference.className = "annotation-reference";
    reference.textContent = annotation.reference.label;
    const copy = document.createElement("button");
    copy.className = "copy-reference";
    copy.type = "button";
    copy.textContent = "Copiar referencia";
    copy.setAttribute("aria-label", `Copiar ${annotation.reference.label}`);
    copy.addEventListener("click", async () => {
      await navigator.clipboard.writeText(annotation.reference.label);
      copy.textContent = "Copiado";
      window.setTimeout(() => { copy.textContent = "Copiar referencia"; }, 1500);
    });
    meta.append(separator, reference, document.createTextNode(" "), copy);
  }
  const quote = document.createElement("blockquote");
  quote.textContent = annotation.text || (annotation.kind === "bookmark" ? "Marcador sin texto" : "Anotación sin texto recuperable");
  article.append(meta, quote);
  if (annotation.note_text) {
    const note = document.createElement("p");
    note.className = "kindle-note";
    note.textContent = annotation.note_text;
    article.append(note);
  }
  return article;
}

async function loadAnnotations() {
  const params = new URLSearchParams({kind: document.querySelector("#kind").value, source: document.querySelector("#source").value, page: annotationPage});
  const response = await fetch(`/api/works/${encodeURIComponent(window.WORK_ID)}/annotations?${params}`);
  if (!response.ok) return;
  const data = await response.json();
  annotationPages = data.pages;
  document.querySelector("#annotation-list").replaceChildren(...data.items.map(annotationCard));
  document.querySelector("#annotation-empty").hidden = data.items.length > 0;
  setText("annotation-result-count", `${formatNumber.format(data.total)} resultados`);
  setText("annotation-page", `${data.page} / ${data.pages}`);
  document.querySelector("#annotation-previous").disabled = data.page <= 1;
  document.querySelector("#annotation-next").disabled = data.page >= data.pages;
}

function personalItem(title, detail = "") {
  const item = document.createElement("div");
  item.className = "personal-item";
  const strong = document.createElement("strong");
  strong.textContent = title;
  item.append(strong);
  if (detail) {
    const paragraph = document.createElement("p");
    paragraph.textContent = detail;
    item.append(paragraph);
  }
  return item;
}

async function loadPersonal() {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/personal`);
  const collections = data.collections.map((item) => personalItem(item.name, item.note || ""));
  const notes = data.notes.map((item) => personalItem("Nota personal", item.body));
  const relations = data.relations.map((item) => personalItem(item.label || item.relation_type, `${item.other_title}${item.explanation ? ` · ${item.explanation}` : ""}`));
  document.querySelector("#collection-items").replaceChildren(...collections);
  document.querySelector("#personal-note-items").replaceChildren(...notes);
  document.querySelector("#relation-items").replaceChildren(...relations);
  for (const [selector, count, label] of [["#collection-items", collections.length, "colecciones"], ["#personal-note-items", notes.length, "notas propias"], ["#relation-items", relations.length, "relaciones"]]) {
    const container = document.querySelector(selector);
    if (!count) container.append(personalItem(`Sin ${label}`));
  }
}

async function loadOptions() {
  const [collections, works, profiles] = await Promise.all([
    jsonRequest("/api/collections"), jsonRequest("/api/work-options"), jsonRequest("/api/ai-profiles"),
  ]);
  const collectionSelect = document.querySelector("#collection-select");
  collectionSelect.replaceChildren(...collections.items.map((item) => new Option(item.name, item.id)));
  collectionSelect.disabled = collections.items.length === 0;
  const relationSelect = document.querySelector("#relation-target");
  const alternatives = works.items.filter((item) => item.id !== window.WORK_ID);
  relationSelect.replaceChildren(...alternatives.map((item) => new Option(item.title, item.id)));
  const profileSelect = document.querySelector("#conversation-profile");
  profileSelect.replaceChildren(...profiles.items.map((item) => new Option(item.name, item.id, item.is_default, item.is_default)));
  document.querySelector("#new-conversation").disabled = profiles.items.length === 0;
}

function messageCard(message) {
  const article = document.createElement("article");
  article.className = `conversation-message ${message.role}`;
  const label = document.createElement("strong");
  label.textContent = message.role === "assistant" ? "Acompañante" : "Vos";
  const content = document.createElement("p");
  content.textContent = message.content;
  article.append(label, content);
  return article;
}

function contextChoice(item, type, selected) {
  const label = document.createElement("label");
  const input = document.createElement("input");
  input.type = "checkbox"; input.name = type; input.value = item.id; input.checked = selected.includes(item.id);
  const text = document.createElement("span");
  text.textContent = item.content;
  label.append(input, text);
  return label;
}

async function loadContext(identifier) {
  const data = await jsonRequest(`/api/conversations/${encodeURIComponent(identifier)}/context`);
  const selectedNotes = data.selected.personal_note || [];
  const selectedAnnotations = data.selected.annotation || [];
  document.querySelector("#context-notes").replaceChildren(...data.notes.map((item) => contextChoice(item, "personal_note", selectedNotes)));
  document.querySelector("#context-annotations").replaceChildren(...data.annotations.map((item) => contextChoice(item, "annotation", selectedAnnotations)));
  for (const [selector, emptyText] of [["#context-notes", "No hay notas propias"], ["#context-annotations", "No hay anotaciones recuperadas"]]) {
    const container = document.querySelector(selector);
    if (!container.children.length) { const empty = document.createElement("p"); empty.textContent = emptyText; container.append(empty); }
  }
  setText("context-count", `· ${selectedNotes.length + selectedAnnotations.length} seleccionadas`);
}

async function loadPromptPreview() {
  if (!activeConversationId) return;
  const packet = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/prompt-preview`);
  document.querySelector("#prompt-preview-content").textContent = `INSTRUCCIONES DEL PERFIL\n${packet.instructions}\n\nMENSAJES Y CONTEXTO\n${JSON.stringify(packet.input, null, 2)}`;
}

async function loadProviderStatus() {
  const status = await jsonRequest("/api/ai/status");
  document.querySelector("#provider-notice").textContent = status.ready
    ? `Proveedor activo: ${status.provider}. El mensaje y el contexto seleccionado se enviarán al proveedor.`
    : "Modo borrador: el mensaje se guarda, pero nada se envía fuera de esta computadora.";
}

async function openConversation(identifier) {
  const conversation = await jsonRequest(`/api/conversations/${encodeURIComponent(identifier)}`);
  activeConversationId = identifier;
  document.querySelector("#conversation-empty").hidden = true;
  document.querySelector("#conversation-active").hidden = false;
  setText("active-conversation-profile", conversation.profile_name_snapshot);
  setText("active-conversation-title", conversation.title || "Conversación sobre la lectura");
  const messages = conversation.messages.map(messageCard);
  const container = document.querySelector("#conversation-messages");
  container.replaceChildren(...messages);
  if (!messages.length) {
    const empty = document.createElement("p");
    empty.className = "conversation-message-empty";
    empty.textContent = "La conversación está lista. Escribí el primer mensaje.";
    container.append(empty);
  }
  document.querySelectorAll(".conversation-list button").forEach((button) => {
    button.setAttribute("aria-current", button.dataset.id === identifier ? "true" : "false");
  });
  await loadContext(identifier);
  await loadPromptPreview();
}

async function loadConversations(preferredId = activeConversationId) {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`);
  const list = document.querySelector("#conversation-list");
  const buttons = data.items.map((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.id = conversation.id;
    const title = document.createElement("strong");
    title.textContent = conversation.title || "Conversación sobre la lectura";
    const detail = document.createElement("span");
    detail.textContent = `${conversation.profile_name_snapshot} · ${conversation.message_count} mensajes`;
    button.append(title, detail);
    button.addEventListener("click", () => openConversation(conversation.id));
    return button;
  });
  list.replaceChildren(...buttons);
  if (!buttons.length) {
    const empty = document.createElement("p");
    empty.textContent = "Sin conversaciones";
    list.append(empty);
    return;
  }
  const next = data.items.some((item) => item.id === preferredId) ? preferredId : data.items[0].id;
  await openConversation(next);
}

function feedback(message, error = false) {
  const element = document.querySelector("#personal-feedback");
  element.textContent = message;
  element.classList.toggle("is-error", error);
}

async function saveDisplayTitle(title) {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/display-title`, {
    method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({title}),
  });
  setText("book-title", data.title);
  document.title = `${data.title} · Biblioteca personal`;
  document.querySelector("#display-title-input").value = data.display_title || data.title;
  feedback(data.display_title ? "Título mostrado actualizado." : "Se restauró la corrección automática.");
}

async function submitPersonal(event, action) {
  event.preventDefault();
  try {
    await action();
    event.currentTarget.reset();
    feedback("Cambios guardados en la biblioteca local.");
    await Promise.all([loadPersonal(), loadOptions(), loadBook()]);
  } catch (error) {
    feedback(error.message, true);
  }
}

document.querySelector("#create-collection-form").addEventListener("submit", (event) => submitPersonal(event, () => jsonRequest("/api/collections", {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({name: document.querySelector("#collection-name").value}),
})));
document.querySelector("#assign-collection-form").addEventListener("submit", (event) => submitPersonal(event, () => jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/collections`, {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({collection_id: document.querySelector("#collection-select").value, note: document.querySelector("#collection-note").value}),
})));
document.querySelector("#personal-note-form").addEventListener("submit", (event) => submitPersonal(event, () => jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/notes`, {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({body: document.querySelector("#personal-note-body").value}),
})));
document.querySelector("#relation-form").addEventListener("submit", (event) => submitPersonal(event, () => jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/relations`, {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({target_work_id: document.querySelector("#relation-target").value, relation_type: document.querySelector("#relation-type").value, explanation: document.querySelector("#relation-explanation").value, symmetric: document.querySelector("#relation-symmetric").checked}),
})));
document.querySelector("#title-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await saveDisplayTitle(document.querySelector("#display-title-input").value); }
  catch (error) { feedback(error.message, true); }
});
document.querySelector("#reset-title").addEventListener("click", async () => {
  try { await saveDisplayTitle(null); }
  catch (error) { feedback(error.message, true); }
});
document.querySelector("#new-conversation").addEventListener("click", async () => {
  const button = document.querySelector("#new-conversation");
  button.disabled = true;
  try {
    const created = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({profile_id: document.querySelector("#conversation-profile").value}),
    });
    await loadConversations(created.id);
    document.querySelector("#conversation-message").focus();
  } catch (error) {
    document.querySelector("#conversation-feedback").textContent = error.message;
  } finally { button.disabled = false; }
});
document.querySelector("#conversation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversationId) return;
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    const result = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/respond`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({content: document.querySelector("#conversation-message").value}),
    });
    event.currentTarget.reset();
    document.querySelector("#conversation-feedback").textContent = result.mode === "draft" ? "Mensaje guardado. No se envió a una IA porque está activo el modo borrador." : "El acompañante respondió.";
    await loadConversations(activeConversationId);
  } catch (error) {
    document.querySelector("#conversation-feedback").textContent = error.message;
  } finally { button.disabled = false; }
});
document.querySelector("#context-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversationId) return;
  const selected = (name) => [...event.currentTarget.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
  try {
    await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/context`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({personal_note_ids: selected("personal_note"), annotation_ids: selected("annotation")}),
    });
    document.querySelector("#conversation-feedback").textContent = "Contexto guardado para esta conversación.";
    await loadContext(activeConversationId);
    await loadPromptPreview();
  } catch (error) { document.querySelector("#conversation-feedback").textContent = error.message; }
});

document.querySelector("#annotation-filters").addEventListener("input", () => { annotationPage = 1; loadAnnotations(); });
document.querySelector("#annotation-previous").addEventListener("click", () => { if (annotationPage > 1) { annotationPage -= 1; loadAnnotations(); } });
document.querySelector("#annotation-next").addEventListener("click", () => { if (annotationPage < annotationPages) { annotationPage += 1; loadAnnotations(); } });
loadBook();
loadAnnotations();
loadPersonal();
loadOptions();
loadConversations();
loadProviderStatus();
