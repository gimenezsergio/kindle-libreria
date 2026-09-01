const formatNumber = new Intl.NumberFormat("es-AR");
const setText = (id, value) => { document.querySelector(`#${id}`).textContent = value; };
let annotationPage = 1;
let annotationPages = 1;

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
  setText("identity-state", book.merge_status === "normal" ? "Identidad confirmada" : book.merge_status === "review" ? "Identidad por revisar" : "Identidad provisional");
  setText("book-annotation-total", formatNumber.format(book.annotations.total));
  const present = book.editions.some((edition) => edition.presence === "present");
  setText("book-presence", present ? "Presente" : "Ausente");
  setText("edition-count", formatNumber.format(book.editions.length));
  setText("edition-detail", book.editions.map((edition) => edition.language || edition.format_hint).filter(Boolean).join(" · ") || "Sin metadatos adicionales");
  if (book.progress) {
    setText("progress-position", book.progress.last_position_native || "Disponible");
    const bits = [];
    if (book.progress.progress_fraction !== null) bits.push(`${Math.round(book.progress.progress_fraction * 100)} % estimado`);
    if (book.progress.words_read !== null) bits.push(`${formatNumber.format(book.progress.words_read)} palabras`);
    setText("progress-detail", bits.join(" · ") || "Posición nativa del Kindle");
  } else {
    setText("progress-position", "Sin datos");
    setText("progress-detail", "No se encontró un estado de lectura vinculado");
  }
  const personalTotal = book.personal.collections + book.personal.notes + book.personal.relations;
  setText("personal-count", formatNumber.format(personalTotal));
  setText("personal-detail", `${book.personal.collections} colecciones · ${book.personal.notes} notas · ${book.personal.relations} relaciones`);
}

function annotationCard(annotation) {
  const article = document.createElement("article");
  article.className = `annotation-card ${annotation.kind}`;
  const meta = document.createElement("div");
  meta.className = "annotation-meta";
  const kind = {highlight: "Subrayado", note: "Nota", bookmark: "Marcador"}[annotation.kind] || "Anotación";
  const position = annotation.start_position_native ? ` · Posición ${annotation.start_position_native}` : "";
  meta.textContent = `${kind}${position} · ${(annotation.sources || "fuente desconocida").toUpperCase()}`;
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
  const [collections, works] = await Promise.all([
    jsonRequest("/api/collections"), jsonRequest("/api/work-options"),
  ]);
  const collectionSelect = document.querySelector("#collection-select");
  collectionSelect.replaceChildren(...collections.items.map((item) => new Option(item.name, item.id)));
  collectionSelect.disabled = collections.items.length === 0;
  const relationSelect = document.querySelector("#relation-target");
  const alternatives = works.items.filter((item) => item.id !== window.WORK_ID);
  relationSelect.replaceChildren(...alternatives.map((item) => new Option(item.title, item.id)));
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

document.querySelector("#annotation-filters").addEventListener("input", () => { annotationPage = 1; loadAnnotations(); });
document.querySelector("#annotation-previous").addEventListener("click", () => { if (annotationPage > 1) { annotationPage -= 1; loadAnnotations(); } });
document.querySelector("#annotation-next").addEventListener("click", () => { if (annotationPage < annotationPages) { annotationPage += 1; loadAnnotations(); } });
loadBook();
loadAnnotations();
loadPersonal();
loadOptions();
