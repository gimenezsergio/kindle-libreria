const formatNumber = new Intl.NumberFormat("es-AR");
const setText = (id, value) => { document.querySelector(`#${id}`).textContent = value; };
let annotationPage = 1;
let annotationPages = 1;

async function loadBook() {
  const response = await fetch(`/api/works/${encodeURIComponent(window.WORK_ID)}`);
  if (!response.ok) { setText("book-title", "No encontramos esta obra"); return; }
  const book = await response.json();
  document.title = `${book.title} · Biblioteca personal`;
  setText("book-title", book.title);
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

document.querySelector("#annotation-filters").addEventListener("input", () => { annotationPage = 1; loadAnnotations(); });
document.querySelector("#annotation-previous").addEventListener("click", () => { if (annotationPage > 1) { annotationPage -= 1; loadAnnotations(); } });
document.querySelector("#annotation-next").addEventListener("click", () => { if (annotationPage < annotationPages) { annotationPage += 1; loadAnnotations(); } });
loadBook();
loadAnnotations();
