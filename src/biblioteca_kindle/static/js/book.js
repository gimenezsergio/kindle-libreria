const formatNumber = new Intl.NumberFormat("es-AR");
const setText = (id, value) => { document.querySelector(`#${id}`).textContent = value; };
const languageNames = {de: "Alemán", en: "Inglés", es: "Español", fr: "Francés", it: "Italiano", pt: "Portugués"};
let annotationPage = 1;
let annotationPages = 1;
let activeConversationId = null;
let librarySearchResults = [];
let previewSearchQuery = "";
let contextOptionsData = {notes: [], annotations: []};

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
  const searchWorks = document.querySelector("#library-search-works");
  searchWorks.replaceChildren(...works.items.map((item) => new Option(item.title, item.id)));
}

function messageCard(message) {
  const article = document.createElement("article");
  article.className = `conversation-message ${message.role}`;
  const label = document.createElement("strong");
  label.textContent = message.role === "assistant" ? "Acompañante" : "Vos";
  const content = document.createElement("p");
  content.textContent = message.content;
  article.append(label, content);
  if (message.role === "assistant" && message.library_sources?.length) {
    const details = document.createElement("details");
    details.className = "answer-sources";
    const summary = document.createElement("summary");
    summary.textContent = `${message.library_sources.length} fuentes de la biblioteca usadas`;
    const list = document.createElement("ol");
    message.library_sources.forEach((source, index) => {
      const item = document.createElement("li");
      const heading = document.createElement("strong");
      heading.textContent = `[B${index + 1}] ${source.label} · ${source.work_title}`;
      const excerpt = document.createElement("p");
      excerpt.textContent = `${source.content}${source.reference ? ` · ${source.reference}` : ""}`;
      item.append(heading, excerpt); list.append(item);
    });
    details.append(summary, list); article.append(details);
  }
  return article;
}

function searchScopePayload() {
  const scope = document.querySelector("#library-search-scope").value;
  return {
    search_scope: scope,
    search_work_ids: scope === "selected"
      ? [...document.querySelector("#library-search-works").selectedOptions].map((option) => option.value)
      : [],
  };
}

function selectedLibraryKeys() {
  return [...document.querySelectorAll('#library-search-results input[type="checkbox"]:checked')]
    .map((input) => input.value);
}

function librarySearchPayload() {
  const content = document.querySelector("#conversation-message").value.trim();
  const payload = {
    search_library: document.querySelector("#library-search-enabled").checked,
    search_query: content,
    ...searchScopePayload(),
  };
  if (previewSearchQuery === content) payload.library_source_keys = selectedLibraryKeys();
  return payload;
}

function renderLibraryResults(items) {
  const container = document.querySelector("#library-search-results");
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "No encontramos evidencia textual para esta consulta.";
    container.replaceChildren(empty);
    document.querySelector("#pin-library-context").hidden = true;
    return;
  }
  const cards = items.map((item) => {
    const label = document.createElement("label"); label.className = "library-result";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = item.key; input.checked = true;
    const body = document.createElement("span");
    const heading = document.createElement("strong"); heading.textContent = `${item.label} · ${item.work_title}`;
    const content = document.createElement("span"); content.textContent = `${item.content}${item.reference ? ` · ${item.reference}` : ""}`;
    body.append(heading, content); label.append(input, body); return label;
  });
  container.replaceChildren(...cards);
  document.querySelector("#pin-library-context").hidden = false;
}

async function previewLibrarySearch() {
  if (!activeConversationId) return;
  const query = document.querySelector("#conversation-message").value.trim();
  if (!query) throw new Error("Escribí primero la pregunta que querés explorar.");
  const data = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/library-search`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({search_query: query, ...searchScopePayload()}),
  });
  librarySearchResults = data.items; previewSearchQuery = query; renderLibraryResults(data.items);
}

function contextChoice(item, type, selected) {
  const label = document.createElement("label");
  const readableStart = /^\d+$/.test(item.start_position_native || "");
  const readableEnd = /^\d+$/.test(item.end_position_native || "");
  const position = readableStart
    ? `${item.position_type === "page" ? "Página" : "Ubicación"} ${item.start_position_native}${readableEnd && item.end_position_native !== item.start_position_native ? `–${item.end_position_native}` : ""}`
    : "";
  label.dataset.searchText = `${item.content} ${position}`.toLocaleLowerCase("es");
  const input = document.createElement("input");
  input.type = "checkbox"; input.name = type; input.value = item.id; input.checked = selected.includes(item.id);
  const body = document.createElement("span");
  if (position) { const meta = document.createElement("small"); meta.textContent = position; body.append(meta); }
  const text = document.createElement("span"); text.textContent = item.content;
  body.append(text); label.append(input, body);
  return label;
}

function renderAttachedMaterial(data, selectedNotes, selectedAnnotations) {
  const selectedItems = [
    ...data.notes.filter((item) => selectedNotes.includes(item.id)).map((item) => ({...item, type: "personal_note", label: "Nota propia"})),
    ...data.annotations.filter((item) => selectedAnnotations.includes(item.id)).map((item) => ({...item, type: "annotation", label: item.kind === "note" ? "Nota Kindle" : "Subrayado"})),
  ];
  const container = document.querySelector("#attached-material");
  const cards = selectedItems.map((item) => {
    const article = document.createElement("article"); article.className = "attached-item";
    const body = document.createElement("div");
    const label = document.createElement("strong"); label.textContent = item.label;
    const content = document.createElement("p"); content.textContent = item.content;
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "remove-attached"; remove.setAttribute("aria-label", `Quitar ${item.label}`); remove.textContent = "×";
    remove.addEventListener("click", async () => {
      const checkbox = document.querySelector(`#context-form input[name="${item.type}"][value="${CSS.escape(item.id)}"]`);
      if (checkbox) checkbox.checked = false;
      await saveContextSelection();
    });
    body.append(label, content); article.append(body, remove); return article;
  });
  if (!cards.length) {
    const empty = document.createElement("p"); empty.textContent = "No agregaste fragmentos todavía. La ficha del libro se incluye siempre.";
    cards.push(empty);
  }
  container.replaceChildren(...cards);
}

async function loadContext(identifier) {
  const data = await jsonRequest(`/api/conversations/${encodeURIComponent(identifier)}/context`);
  contextOptionsData = data;
  const selectedNotes = data.selected.personal_note || [];
  const selectedAnnotations = data.selected.annotation || [];
  document.querySelector("#context-notes").replaceChildren(...data.notes.map((item) => contextChoice(item, "personal_note", selectedNotes)));
  document.querySelector("#context-annotations").replaceChildren(...data.annotations.map((item) => contextChoice(item, "annotation", selectedAnnotations)));
  for (const [selector, emptyText] of [["#context-notes", "No hay notas propias"], ["#context-annotations", "No hay anotaciones recuperadas"]]) {
    const container = document.querySelector(selector);
    if (!container.children.length) { const empty = document.createElement("p"); empty.textContent = emptyText; container.append(empty); }
  }
  const selectedCount = selectedNotes.length + selectedAnnotations.length;
  setText("context-count", `${selectedCount} ${selectedCount === 1 ? "seleccionada" : "seleccionadas"}`);
  setText("annotation-option-count", `(${data.annotations.length})`);
  setText("note-option-count", `(${data.notes.length})`);
  setText("material-summary-count", `${selectedCount} ${selectedCount === 1 ? "adjunto" : "adjuntos"}`);
  setText("attached-count", selectedCount ? `${selectedCount} ${selectedCount === 1 ? "fragmento adjunto" : "fragmentos adjuntos"}` : "Sin material adjunto");
  renderAttachedMaterial(data, selectedNotes, selectedAnnotations);
}

function currentContextSelection() {
  const selected = (name) => [...document.querySelectorAll(`#context-form input[name="${name}"]:checked`)].map((input) => input.value);
  return {personal_note_ids: selected("personal_note"), annotation_ids: selected("annotation")};
}

function updateContextSelectionCount() {
  const count = document.querySelectorAll('#context-form input[type="checkbox"]:checked').length;
  setText("context-count", `${count} ${count === 1 ? "seleccionada" : "seleccionadas"}`);
}

async function loadPromptPreview() {
  if (!activeConversationId) return;
  const packet = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/prompt-preview`);
  document.querySelector("#prompt-preview-content").textContent = `INSTRUCCIONES DEL PERFIL\n${packet.instructions}\n\nMENSAJES Y CONTEXTO\n${JSON.stringify(packet.input, null, 2)}`;
}

async function loadProviderStatus() {
  const status = await jsonRequest("/api/ai/status");
  document.querySelector("#provider-notice").textContent = status.ready
    ? `● ${status.provider} activo`
    : "● Modo borrador";
  document.querySelector("#provider-description").textContent = status.ready
    ? "El mensaje y el contexto seleccionado se enviarán a este proveedor."
    : "El mensaje se guarda, pero nada se envía fuera de esta computadora.";
}

async function openConversation(identifier) {
  const conversation = await jsonRequest(`/api/conversations/${encodeURIComponent(identifier)}`);
  activeConversationId = identifier;
  librarySearchResults = []; previewSearchQuery = "";
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
  container.scrollTop = container.scrollHeight;
  document.querySelector("#conversation-list").value = identifier;
  await loadContext(identifier);
  await loadPromptPreview();
}

async function loadConversations(preferredId = activeConversationId) {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`);
  const list = document.querySelector("#conversation-list");
  const options = data.items.map((conversation) => new Option(
    `${conversation.title || "Conversación sobre la lectura"} · ${conversation.message_count} mensajes`, conversation.id,
  ));
  list.replaceChildren(...options);
  list.disabled = !options.length;
  if (!options.length) {
    list.append(new Option("Sin conversaciones", ""));
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
  const form = event.currentTarget;
  try {
    await action();
    form.reset();
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
document.querySelector("#conversation-list").addEventListener("change", (event) => {
  if (event.target.value) openConversation(event.target.value);
});
document.querySelector("#conversation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversationId) return;
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const result = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/respond`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({content: document.querySelector("#conversation-message").value, ...currentContextSelection(), ...librarySearchPayload()}),
    });
    form.reset();
    document.querySelector("#conversation-feedback").textContent = result.mode === "draft" ? "Mensaje guardado. No se envió a una IA porque está activo el modo borrador." : "El acompañante respondió.";
    await loadConversations(activeConversationId);
  } catch (error) {
    document.querySelector("#conversation-feedback").textContent = error.message;
  } finally { button.disabled = false; }
});
document.querySelector("#library-search-scope").addEventListener("change", (event) => {
  document.querySelector("#library-search-works-label").hidden = event.target.value !== "selected";
  librarySearchResults = []; previewSearchQuery = "";
});
document.querySelector("#preview-library-search").addEventListener("click", async (event) => {
  const button = event.currentTarget; button.disabled = true;
  try { await previewLibrarySearch(); }
  catch (error) { document.querySelector("#conversation-feedback").textContent = error.message; }
  finally { button.disabled = false; }
});
document.querySelector("#pin-library-context").addEventListener("click", async () => {
  try {
    const payload = {...librarySearchPayload(), library_source_keys: selectedLibraryKeys()};
    const result = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/library-context/pin`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
    });
    document.querySelector("#conversation-feedback").textContent = `${result.pinned} fuentes quedaron fijadas.`;
    await loadContext(activeConversationId); await loadPromptPreview();
  } catch (error) { document.querySelector("#conversation-feedback").textContent = error.message; }
});
async function saveContextSelection() {
  if (!activeConversationId) return;
  await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/context`, {
    method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(currentContextSelection()),
  });
  document.querySelector("#conversation-feedback").textContent = "Contexto guardado para esta conversación.";
  await loadContext(activeConversationId);
  await loadPromptPreview();
}
document.querySelector("#context-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await saveContextSelection();
    document.querySelector("#context-dialog").close();
  } catch (error) { document.querySelector("#conversation-feedback").textContent = error.message; }
});
document.querySelector("#open-context-picker").addEventListener("click", () => {
  document.querySelector("#context-search").value = "";
  document.querySelectorAll(".context-options label").forEach((label) => { label.hidden = false; });
  document.querySelector("#context-dialog").showModal();
  document.querySelector("#context-search").focus();
});
document.querySelector("#cancel-context-picker").addEventListener("click", () => {
  document.querySelector("#context-dialog").close();
  loadContext(activeConversationId);
});
document.querySelector("#context-search").addEventListener("input", (event) => {
  const query = event.target.value.trim().toLocaleLowerCase("es");
  document.querySelectorAll(".context-options label").forEach((label) => {
    label.hidden = Boolean(query) && !label.dataset.searchText.includes(query);
  });
});
document.querySelector("#context-form").addEventListener("change", updateContextSelectionCount);
document.querySelector("#library-search-enabled").addEventListener("click", (event) => event.stopPropagation());
document.querySelectorAll("[data-context-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-context-tab]").forEach((item) => item.setAttribute("aria-selected", String(item === tab)));
    document.querySelectorAll("[data-context-panel]").forEach((panel) => { panel.hidden = panel.dataset.contextPanel !== tab.dataset.contextTab; });
  });
});

document.querySelector("#annotation-filters").addEventListener("input", () => { annotationPage = 1; loadAnnotations(); });
document.querySelector("#annotation-previous").addEventListener("click", () => { if (annotationPage > 1) { annotationPage -= 1; loadAnnotations(); } });
document.querySelector("#annotation-next").addEventListener("click", () => { if (annotationPage < annotationPages) { annotationPage += 1; loadAnnotations(); } });
document.querySelectorAll("[data-book-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    const selected = tab.dataset.bookTab;
    document.querySelectorAll("[data-book-tab]").forEach((item) => {
      item.setAttribute("aria-selected", String(item === tab));
      item.tabIndex = item === tab ? 0 : -1;
    });
    document.querySelectorAll("[data-book-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.bookPanel !== selected;
    });
    history.replaceState(null, "", `#panel-${selected}`);
  });
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const tabs = [...document.querySelectorAll("[data-book-tab]")];
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(tabs.indexOf(tab) + direction + tabs.length) % tabs.length];
    event.preventDefault(); next.focus(); next.click();
  });
});
const requestedPanel = location.hash.replace("#panel-", "");
const requestedTab = document.querySelector(`[data-book-tab="${requestedPanel}"]`);
if (requestedTab) requestedTab.click();
loadBook();
loadAnnotations();
loadPersonal();
loadOptions();
loadConversations();
loadProviderStatus();
