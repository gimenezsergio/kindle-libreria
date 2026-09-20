const formatNumber = new Intl.NumberFormat("es-AR");
const setText = (id, value) => {
  const element = document.querySelector(`#${id}`);
  if (element) element.textContent = value;
};
const languageNames = {de: "Alemán", en: "Inglés", es: "Español", fr: "Francés", it: "Italiano", pt: "Portugués"};
let annotationPage = 1;
let annotationPages = 1;
let activeConversationId = null;
let librarySearchResults = [];
let previewSearchQuery = "";
let responseAnimation = null;
const CHAT_BOTTOM_TOLERANCE = 48;
let conversationScrollState = null;
let currentBookTitle = "este libro";
let companionActions = [];
let actionDraft = null;
let actionDialogReturnsFocus = true;

function setCompanionFocus(active) {
  document.body.classList.toggle("is-companion-focused", active);
  if (!active) {
    const dialog = document.querySelector("#new-conversation-dialog");
    if (dialog?.open) dialog.close();
    const material = document.querySelector(".material-column");
    material?.classList.remove("is-mobile-open");
    document.querySelector("#mobile-material-toggle")?.setAttribute("aria-expanded", "false");
    return;
  }
  window.requestAnimationFrame(() => scrollConversationToBottom());
}

function exitCompanionFocus() {
  const memoryTab = document.querySelector('[data-book-tab="memory"]');
  if (memoryTab) memoryTab.click();
  else setCompanionFocus(false);
  window.requestAnimationFrame(() => {
    memoryTab?.scrollIntoView({block: "start"});
    memoryTab?.focus({preventScroll: true});
  });
}

function openNewConversationDialog() {
  const dialog = document.querySelector("#new-conversation-dialog");
  const profile = document.querySelector("#conversation-profile");
  if (!dialog || !profile?.options.length || profile.disabled) return;
  dialog.showModal();
  window.requestAnimationFrame(() => profile.focus());
}

function disposeConversationScroll() {
  if (!conversationScrollState) return;
  const {container, onScroll, frame} = conversationScrollState;
  container.removeEventListener("scroll", onScroll);
  if (frame) window.cancelAnimationFrame(frame);
  conversationScrollState = null;
}

function isConversationNearBottom(container) {
  return container.scrollHeight - container.scrollTop - container.clientHeight <= CHAT_BOTTOM_TOLERANCE;
}

function setupConversationScroll(container) {
  disposeConversationScroll();
  const state = {container, autoFollow: true, frame: null};
  state.onScroll = () => {
    state.autoFollow = isConversationNearBottom(container);
  };
  container.addEventListener("scroll", state.onScroll, {passive: true});
  conversationScrollState = state;
  return state;
}

function scrollConversationToBottom({force = false} = {}) {
  const state = conversationScrollState;
  if (!state || (!force && !state.autoFollow)) return;
  if (state.frame) return;
  state.frame = window.requestAnimationFrame(() => {
    state.frame = null;
    if (force || state.autoFollow) state.container.scrollTop = state.container.scrollHeight;
  });
}

function resumeConversationAutoFollow() {
  if (conversationScrollState) conversationScrollState.autoFollow = true;
}

function conversationDisplayTitle(conversation) {
  if (String(conversation.title || "").trim()) return conversation.title;
  return conversation.title_origin === "pending" ? "Nueva conversación" : "Conversación sobre la lectura";
}
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
  if (response.status === 404) {
    setText("book-title", "No encontramos esta obra");
    return;
  }
  if (!response.ok) throw new Error(`La aplicación respondió con el estado ${response.status}`);
  const book = await response.json();
  currentBookTitle = book.title || "este libro";
  document.title = `${book.title} · Biblioteca personal`;
  setText("book-title", book.title);
  setText("focus-book-context", `${book.title} · ${book.authors || "Autor no disponible"}`);
  const coverImage = document.querySelector("#book-cover-image");
  const coverPlaceholder = document.querySelector("#book-cover-placeholder");
  if (book.cover) {
    coverImage.src = `/static/covers/${encodeURIComponent(book.cover.path)}`;
    coverImage.alt = `Portada de ${book.title}`;
    coverImage.title = `Fuente: ${book.cover.source}`;
    coverImage.hidden = false;
    coverPlaceholder.hidden = true;
  } else {
    coverImage.hidden = true;
    coverPlaceholder.hidden = false;
    coverPlaceholder.textContent = book.title.trim().charAt(0).toUpperCase() || "B";
  }
  setText("original-title", book.original_title);
  document.querySelector("#display-title-input").value = book.display_title || book.title;
  setText("book-author", book.authors || "Autor no disponible");
  setText("identity-state", book.merge_status === "review" ? "Identidad por revisar" : "Ficha de lectura");
  setText("book-annotation-total", formatNumber.format(book.annotations.total));
  const present = book.editions.some((edition) => edition.presence === "present");
  setText("book-presence", present ? "Presente" : "Ausente");
  document.querySelector("#book-presence").classList.toggle("is-present", present);
  const languages = [...new Set(book.editions.map((edition) => edition.language).filter(Boolean).map(languageName))];
  setText("book-language", languages.join(" · ") || "Idioma no disponible");
  const editionTotal = book.editions.length;
  setText("edition-count", languages.join(" · ") || (editionTotal ? `${formatNumber.format(editionTotal)} documento${editionTotal === 1 ? "" : "s"}` : "Sin datos"));
  setText("edition-detail", editionTotal ? `${formatNumber.format(editionTotal)} ${editionTotal === 1 ? "edición registrada" : "ediciones registradas"}` : "El Kindle no expuso datos del documento");
  if (book.progress) {
    setText("progress-position", "Actividad registrada");
    setText("book-activity", "Actividad registrada");
    const bits = [];
    if (book.progress.progress_fraction !== null) bits.push(`${Math.round(book.progress.progress_fraction * 100)} % estimado`);
    if (book.progress.words_read !== null) bits.push(`${formatNumber.format(book.progress.words_read)} palabras registradas`);
    setText("progress-detail", bits.join(" · ") || "El Kindle conserva una posición de lectura");
  } else {
    setText("progress-position", "Sin datos");
    setText("book-activity", "Sin seguimiento");
    setText("progress-detail", "El Kindle no expuso seguimiento para este libro");
  }
  const personalTotal = book.personal.collections + book.personal.notes + book.personal.relations;
  setText("personal-count", personalTotal ? `${formatNumber.format(personalTotal)} ${personalTotal === 1 ? "elemento" : "elementos"}` : "Sin organizar");
  setText("personal-detail", personalTotal ? `${book.personal.collections} colecciones · ${book.personal.notes} notas · ${book.personal.relations} relaciones` : "Podés agregar categorías, notas o relaciones");
  renderCompanionActionScope();
}

function showBookLoadError(error) {
  console.error("No se pudo cargar la ficha del libro", error);
  setText("book-title", "No pudimos cargar esta ficha");
  setText("book-author", "La información del libro no llegó desde la aplicación.");
  const feedback = document.querySelector("#book-load-feedback");
  const detail = error instanceof Error && error.message ? error.message : "Error de red desconocido";
  if (feedback) {
    feedback.textContent = `Error de carga: ${detail}. Verificá que el servidor siga activo y recargá la página.`;
    feedback.hidden = false;
  }
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
  const userCollections = collections.items.filter((item) => !item.is_system);
  collectionSelect.replaceChildren(...userCollections.map((item) => new Option(item.name, item.id)));
  collectionSelect.disabled = userCollections.length === 0;
  const relationSelect = document.querySelector("#relation-target");
  const alternatives = works.items.filter((item) => item.id !== window.WORK_ID);
  relationSelect.replaceChildren(...alternatives.map((item) => new Option(item.title, item.id)));
  const profileSelect = document.querySelector("#conversation-profile");
  profileSelect.replaceChildren(...profiles.items.map((item) => new Option(item.name, item.id, item.is_default, item.is_default)));
  document.querySelector("#new-conversation").disabled = profiles.items.length === 0;
  document.querySelector("#open-new-conversation").disabled = profiles.items.length === 0;
  const searchWorks = document.querySelector("#library-search-works");
  searchWorks.replaceChildren(...works.items.map((item) => new Option(item.title, item.id)));
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function highlightCode(code, lang) {
  const escaped = escapeHtml(code);
  const normalizedLang = (lang || "").toLowerCase().trim();
  const tokens = [];
  const addToken = (cls, text) => {
    tokens.push(`<span class="token-${cls}">${text}</span>`);
    return `___TOKEN_${tokens.length - 1}___`;
  };

  let highlighted = escaped;
  highlighted = highlighted.replace(/(["'`])(?:(?=(\\?))\2[\s\S])*?\1/g, (match) => addToken("string", match));
  highlighted = highlighted.replace(/(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)/g, (match) => addToken("comment", match));
  highlighted = highlighted.replace(/\b\d+(\.\d+)?\b/g, (match) => addToken("number", match));
  const keywordsRegex = /\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|class|extends|import|export|from|async|await|def|self|None|True|False|with|yield|lambda|SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|GROUP|BY|ORDER|LIMIT|CREATE|TABLE|DROP|ALTER|PRIMARY|KEY|FOREIGN|REFERENCES|AND|OR|NOT|IN|IS|NULL)\b/g;
  highlighted = highlighted.replace(keywordsRegex, (match) => addToken("keyword", match));
  highlighted = highlighted.replace(/\b([a-zA-Z_]\w*)\s*(?=\()/g, (match, p1) => addToken("function", p1));
  highlighted = highlighted.replace(/___TOKEN_(\d+)___/g, (match, idx) => tokens[Number(idx)]);

  return `<pre class="code-block"><code class="language-${escapeHtml(normalizedLang)}">${highlighted}</code></pre>`;
}

function renderMarkdown(rawText, librarySources = []) {
  let text = String(rawText || "");

  text = text.replace(/\[B(\d+)\]/g, (match, number) => {
    const source = librarySources?.[Number(number) - 1];
    return source ? `**[${source.label}: ${source.work_title}]**` : "**[Fuente de la biblioteca]**";
  });

  const codeBlocks = [];
  text = text.replace(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (match, lang, code) => {
    codeBlocks.push(highlightCode(code.trimEnd(), lang));
    return `\n\n___CODE_BLOCK_${codeBlocks.length - 1}___\n\n`;
  });

  text = escapeHtml(text);

  const inlineCodes = [];
  text = text.replace(/`([^`]+)`/g, (match, code) => {
    inlineCodes.push(`<code class="inline-code">${code}</code>`);
    return `___INLINE_CODE_${inlineCodes.length - 1}___`;
  });

  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, url) => {
    const safeUrl = (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("/")) ? url : "#";
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  text = text.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  text = text.replace(/___([^_]+)___/g, "<strong><em>$1</em></strong>");
  text = text.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  text = text.replace(/_([^_]+)_/g, "<em>$1</em>");
  text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");

  const lines = text.split("\n");
  const htmlResult = [];
  let inList = null;
  let inBlockquote = false;
  let blockquoteBuffer = [];

  const closeList = () => {
    if (inList) {
      htmlResult.push(`</${inList}>`);
      inList = null;
    }
  };

  const closeBlockquote = () => {
    if (inBlockquote) {
      htmlResult.push(`<blockquote><p>${blockquoteBuffer.join("<br>")}</p></blockquote>`);
      inBlockquote = false;
      blockquoteBuffer = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    const codeMatch = trimmed.match(/^___CODE_BLOCK_(\d+)___$/);
    if (codeMatch) {
      closeList();
      closeBlockquote();
      htmlResult.push(codeBlocks[Number(codeMatch[1])]);
      continue;
    }

    if (!trimmed) {
      closeList();
      closeBlockquote();
      continue;
    }

    if (trimmed.startsWith("&gt; ")) {
      closeList();
      inBlockquote = true;
      blockquoteBuffer.push(trimmed.slice(5));
      continue;
    } else if (inBlockquote) {
      closeBlockquote();
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      closeList();
      closeBlockquote();
      const level = headingMatch[1].length;
      htmlResult.push(`<h${level}>${headingMatch[2]}</h${level}>`);
      continue;
    }

    if (/^(---|[*]{3,}|_{3,})$/.test(trimmed)) {
      closeList();
      closeBlockquote();
      htmlResult.push("<hr>");
      continue;
    }

    const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (ulMatch) {
      closeBlockquote();
      if (inList !== "ul") {
        closeList();
        inList = "ul";
        htmlResult.push("<ul>");
      }
      htmlResult.push(`<li>${ulMatch[1]}</li>`);
      continue;
    }

    const olMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (olMatch) {
      closeBlockquote();
      if (inList !== "ol") {
        closeList();
        inList = "ol";
        htmlResult.push("<ol>");
      }
      htmlResult.push(`<li>${olMatch[2]}</li>`);
      continue;
    }

    closeList();
    closeBlockquote();
    htmlResult.push(`<p>${trimmed}</p>`);
  }

  closeList();
  closeBlockquote();

  let finalHtml = htmlResult.join("");
  finalHtml = finalHtml.replace(/___INLINE_CODE_(\d+)___/g, (match, idx) => inlineCodes[Number(idx)]);

  return finalHtml;
}

function messageCard(message) {
  const article = document.createElement("article");
  article.className = `conversation-message ${message.role}`;
  const label = document.createElement("strong");
  label.textContent = message.role === "assistant" ? "Acompañante" : "Vos";
  const content = document.createElement("div");
  content.className = "conversation-message-content";
  content.innerHTML = renderMarkdown(message.content || "", message.library_sources);
  article.append(label, content);
  if (message.role === "user" && message.companion_action_label_snapshot) {
    const action = document.createElement("small");
    action.className = "conversation-action-label";
    action.textContent = `Atajo: ${message.companion_action_label_snapshot}`;
    article.append(action);
  }
  if (message.role === "assistant" && message.library_sources?.length) {
    const details = document.createElement("details");
    details.className = "answer-sources";
    const summary = document.createElement("summary");
    summary.textContent = `${message.library_sources.length} fuentes de la biblioteca usadas`;
    const list = document.createElement("ol");
    message.library_sources.forEach((source) => {
      const item = document.createElement("li");
      const heading = document.createElement("strong");
      const reference = readableSourceReference(source.reference);
      heading.textContent = `${source.label} de «${source.work_title}»${reference ? ` · ${reference}` : ""}`;
      const excerpt = document.createElement("p");
      excerpt.textContent = source.content;
      item.append(heading, excerpt); list.append(item);
    });
    details.append(summary, list); article.append(details);
  }
  return article;
}

function readableSourceReference(reference) {
  const text = String(reference || "");
  const page = text.match(/\b(?:page|página)\s+(\d+)/i);
  const location = text.match(/\b(?:location|ubicación|posición)\s+(\d+)(?:\s*[-–]\s*(\d+))?/i);
  const parts = [];
  if (page) parts.push(`Página ${page[1]}`);
  if (location) parts.push(`Ubicación ${location[1]}${location[2] ? `–${location[2]}` : ""}`);
  return parts.join(" · ");
}

function pendingMessageCard(profileName) {
  const article = document.createElement("article");
  article.className = "conversation-message assistant conversation-message-pending";
  article.setAttribute("role", "status");
  const label = document.createElement("strong");
  label.textContent = profileName || "Acompañante";
  const content = document.createElement("div");
  content.className = "conversation-message-content thinking-status";
  content.append(document.createTextNode("Está pensando"));
  const dots = document.createElement("span");
  dots.className = "thinking-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<i></i><i></i><i></i>";
  content.append(dots);
  article.append(label, content);
  return article;
}

function cancelResponseAnimation({finish = false} = {}) {
  if (!responseAnimation) return;
  if (finish && responseAnimation.finish) {
    responseAnimation.finish();
    return;
  }
  clearTimeout(responseAnimation.timer);
  responseAnimation.cancelled = true;
  responseAnimation = null;
}

function revealAssistantResponse(pendingCard, answer, librarySources = []) {
  cancelResponseAnimation({finish: true});
  const card = messageCard({role: "assistant", content: answer, library_sources: librarySources});
  const content = card.querySelector(".conversation-message-content");
  const text = answer;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  pendingCard.replaceWith(card);
  scrollConversationToBottom();
  if (reducedMotion || !text) return Promise.resolve();

  content.innerHTML = "";
  content.setAttribute("aria-live", "off");
  card.setAttribute("aria-busy", "true");
  let resolveAnimation;
  const state = {timer: null, cancelled: false, finish: null};
  responseAnimation = state;
  let position = 0;
  state.finish = () => {
    clearTimeout(state.timer);
    state.cancelled = true;
    content.innerHTML = renderMarkdown(text, librarySources);
    card.removeAttribute("aria-busy");
    content.removeAttribute("aria-live");
    if (responseAnimation === state) responseAnimation = null;
    if (resolveAnimation) resolveAnimation();
  };
  return new Promise((resolve) => {
    resolveAnimation = resolve;
    const step = () => {
      if (state.cancelled) return resolve();
      const remaining = text.length - position;
      const chunk = remaining > 240 ? 5 : remaining > 100 ? 3 : 2;
      position = Math.min(text.length, position + chunk);
      content.innerHTML = renderMarkdown(text.slice(0, position), librarySources);
      scrollConversationToBottom();
      if (position >= text.length) {
        card.removeAttribute("aria-busy");
        content.removeAttribute("aria-live");
        if (responseAnimation === state) responseAnimation = null;
        return resolve();
      }
      state.timer = window.setTimeout(step, 20);
    };
    step();
  });
}

function appendTransientExchange(content) {
  cancelResponseAnimation({finish: true});
  const container = document.querySelector("#conversation-messages");
  resumeConversationAutoFollow();
  container.querySelectorAll(".conversation-message-empty, .conversation-message-transient").forEach((item) => item.remove());
  const user = messageCard({role: "user", content});
  const pending = pendingMessageCard(document.querySelector("#active-conversation-profile").textContent);
  user.classList.add("conversation-message-transient");
  pending.classList.add("conversation-message-transient");
  container.append(user, pending);
  scrollConversationToBottom({force: true});
  return pending;
}

function showResponseError(card, message) {
  card.classList.remove("conversation-message-pending");
  card.classList.add("conversation-message-error");
  const content = card.querySelector(".conversation-message-content") || card.querySelector("p");
  if (content) {
    content.textContent = `No pude responder: ${message}`;
  }
}

function selectedContextCount() {
  const selected = contextOptionsData.selected || {};
  return (selected.personal_note || []).length + (selected.annotation || []).length;
}

function libraryScopeLabel() {
  const scope = document.querySelector("#library-search-scope")?.value;
  if (scope === "current") return "solo este libro";
  if (scope === "selected") {
    const count = document.querySelector("#library-search-works")?.selectedOptions.length || 0;
    return count ? `${count} ${count === 1 ? "libro elegido" : "libros elegidos"}` : "los libros elegidos";
  }
  return "toda tu biblioteca";
}

function renderCompanionActionScope() {
  const target = document.querySelector("#companion-action-scope");
  if (!target) return;
  const selectedCount = selectedContextCount();
  const material = selectedCount
    ? `${selectedCount} ${selectedCount === 1 ? "fragmento adjunto" : "fragmentos adjuntos"}`
    : "ningún fragmento adjunto";
  const libraryEnabled = document.querySelector("#library-search-enabled")?.checked;
  const library = libraryEnabled
    ? `La búsqueda de conexiones consultará ${libraryScopeLabel()}.`
    : "La búsqueda de conexiones está desactivada.";
  target.textContent = `Incluye la ficha de «${currentBookTitle}» y ${material}. ${library} La aplicación no contiene el texto completo.`;
}

function invalidateContextReview() {
  const summary = document.querySelector("#prompt-preview-summary");
  const details = document.querySelector("#prompt-preview-details");
  if (!summary || !details) return;
  summary.textContent = "El borrador cambió. Revisá el contexto antes de enviarlo.";
  details.hidden = true;
  details.removeAttribute("open");
  document.querySelector("#prompt-preview-content").textContent = "";
}

function renderCompanionActions() {
  const container = document.querySelector("#companion-action-list");
  const groupsContainer = document.querySelector("#companion-action-groups");
  if (!container || !groupsContainer) return;
  if (!companionActions.length) {
    container.replaceChildren(Object.assign(document.createElement("span"), {
      className: "companion-actions-loading", textContent: "No pudimos preparar los accesos directos.",
    }));
    groupsContainer.replaceChildren();
    return;
  }

  const makeButton = (action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.companionAction = action.id;
    button.dataset.searchText = `${action.label} ${action.description} ${action.group}`.toLocaleLowerCase("es");
    button.textContent = action.label;
    button.title = action.description;
    button.setAttribute("aria-label", `${action.label}. ${action.description}`);
    button.addEventListener("click", () => prepareCompanionAction(action));
    return button;
  };
  container.replaceChildren(...companionActions
    .filter((action) => action.is_primary)
    .map(makeButton));

  const groupedActions = new Map();
  companionActions.filter((action) => !action.is_primary).forEach((action) => {
    const group = groupedActions.get(action.group) || [];
    group.push(action);
    groupedActions.set(action.group, group);
  });
  const groups = [...groupedActions].map(([group, actions]) => {
    const section = document.createElement("section");
    section.className = "companion-action-group";
    const heading = document.createElement("h5");
    heading.textContent = group;
    const list = document.createElement("div");
    list.className = "companion-action-group-list";
    list.append(...actions.map(makeButton));
    section.append(heading, list);
    return section;
  });
  groupsContainer.replaceChildren(...groups);
  filterCompanionActions();
}

function filterCompanionActions() {
  const query = document.querySelector("#companion-action-search")?.value.trim().toLocaleLowerCase("es") || "";
  const buttons = [...document.querySelectorAll("[data-companion-action]")];
  let matches = 0;
  buttons.forEach((button) => {
    const visible = !query || button.dataset.searchText.includes(query);
    button.hidden = !visible;
    if (visible) matches += 1;
  });
  document.querySelectorAll(".companion-action-group").forEach((group) => {
    group.hidden = ![...group.querySelectorAll("[data-companion-action]")].some((button) => !button.hidden);
  });
  const primary = document.querySelector("#companion-primary-actions-title")?.parentElement;
  if (primary) primary.hidden = Boolean(query) && ![...primary.querySelectorAll("[data-companion-action]")].some((button) => !button.hidden);
  const empty = document.querySelector("#companion-actions-empty");
  if (empty) empty.hidden = matches > 0;
}

async function loadCompanionActions() {
  try {
    const data = await jsonRequest("/api/companion-actions");
    companionActions = data.items || [];
  } catch (error) {
    console.error("No se pudieron cargar los accesos directos", error);
    companionActions = [];
  }
  renderCompanionActions();
}

function prepareCompanionAction(action) {
  if (!activeConversationId) return;
  closeCompanionActionsForSelection();
  const textarea = document.querySelector("#conversation-message");
  const searchEnabled = document.querySelector("#library-search-enabled");
  const previous = textarea.value;
  let didEnableLibrarySearch = false;
  if (action.search_behavior === "enable" && searchEnabled && !searchEnabled.checked) {
    searchEnabled.checked = true;
    didEnableLibrarySearch = true;
    renderCompanionActionScope();
  }
  const proposal = action.message_template;
  textarea.value = previous.trim() ? `${previous.trim()}\n\n${proposal}` : proposal;
  actionDraft = {
    previous, proposal, didEnableLibrarySearch,
    actionId: action.id, actionLabel: action.label,
  };
  const draft = document.querySelector("#companion-action-draft");
  draft.hidden = false;
  const profile = document.querySelector("#companion-action-profile")?.textContent || "Perfil no disponible";
  setText("companion-action-draft-label", `${action.label} · ${profile}`);
  const materialHint = action.requirements?.material === "recomendado" && !selectedContextCount()
    ? " Esta acción suele aprovechar mejor un pasaje o una nota seleccionados."
    : "";
  document.querySelector("#conversation-feedback").textContent = didEnableLibrarySearch
    ? `Propuesta lista para editar. Se activó la búsqueda en ${libraryScopeLabel()}; no se envió nada todavía.${materialHint}`
    : `Propuesta lista para editar o descartar; no se envió nada todavía.${materialHint}`;
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  invalidateContextReview();
}

function discardCompanionActionDraft() {
  if (!actionDraft) return;
  const textarea = document.querySelector("#conversation-message");
  textarea.value = actionDraft.previous;
  if (actionDraft.didEnableLibrarySearch) {
    document.querySelector("#library-search-enabled").checked = false;
    renderCompanionActionScope();
  }
  actionDraft = null;
  document.querySelector("#companion-action-draft").hidden = true;
  document.querySelector("#conversation-feedback").textContent = "Propuesta descartada.";
  invalidateContextReview();
  textarea.focus();
}

function openCompanionActionsDialog() {
  if (!activeConversationId) return;
  const dialog = document.querySelector("#companion-actions-dialog");
  const search = document.querySelector("#companion-action-search");
  if (!dialog || dialog.open) return;
  actionDialogReturnsFocus = true;
  dialog.showModal();
  if (search) {
    search.value = "";
    filterCompanionActions();
    window.requestAnimationFrame(() => search.focus());
  }
}

function closeCompanionActionsForSelection() {
  const dialog = document.querySelector("#companion-actions-dialog");
  if (!dialog?.open) return;
  actionDialogReturnsFocus = false;
  dialog.close();
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
    if (item.reason) { const reason = document.createElement("small"); reason.className = "library-result-reason"; reason.textContent = item.reason; body.append(reason); }
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
  const nativePosition = readableStart
    ? `${item.position_type === "page" ? "Página" : "Ubicación"} ${item.start_position_native}${readableEnd && item.end_position_native !== item.start_position_native ? `–${item.end_position_native}` : ""}`
    : "";
  const position = item.reference || nativePosition;
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
  setText("mobile-material-count", `${selectedCount} ${selectedCount === 1 ? "adjunto" : "adjuntos"}`);
  setText("attached-count", selectedCount ? `${selectedCount} ${selectedCount === 1 ? "fragmento adjunto" : "fragmentos adjuntos"}` : "Sin material adjunto");
  renderAttachedMaterial(data, selectedNotes, selectedAnnotations);
  renderCompanionActionScope();
}

function currentContextSelection() {
  const selected = (name) => [...document.querySelectorAll(`#context-form input[name="${name}"]:checked`)].map((input) => input.value);
  return {personal_note_ids: selected("personal_note"), annotation_ids: selected("annotation")};
}

function updateContextSelectionCount() {
  const count = document.querySelectorAll('#context-form input[type="checkbox"]:checked').length;
  setText("context-count", `${count} ${count === 1 ? "seleccionada" : "seleccionadas"}`);
}

function currentCompanionActionId() {
  return actionDraft?.actionId || null;
}

function contextReviewPayload() {
  return {
    content: document.querySelector("#conversation-message").value.trim(),
    ...currentContextSelection(),
    ...librarySearchPayload(),
    companion_action_id: currentCompanionActionId(),
  };
}

function contextReviewScope(preview) {
  if (!preview.scope.search_library) return "No se buscarán conexiones adicionales en la biblioteca.";
  const scope = preview.scope.search_scope;
  if (scope === "current") return "Buscará conexiones solo en este libro.";
  if (scope === "selected") return `Buscará conexiones en ${preview.scope.search_work_ids.length} libro(s) elegido(s).`;
  return "Buscará conexiones en toda tu biblioteca.";
}

function contextMaterialLabel(item) {
  if (item.type === "personal_note") return "nota propia";
  const labels = {
    highlight: "subrayado",
    note: "nota del Kindle",
    bookmark: "marcador",
  };
  return labels[item.label] || "anotación";
}

function renderContextReview(preview) {
  const action = preview.action ? `Acción: ${preview.action.label}.` : "Mensaje libre.";
  const provider = preview.provider.ready
    ? `Proveedor: ${preview.provider.name}.`
    : "Modo borrador: nada se enviará fuera de esta computadora.";
  const materialKinds = preview.material.items.map(contextMaterialLabel).join(", ");
  const material = preview.material.count
    ? `${preview.material.count} ${preview.material.count === 1 ? "fragmento adjunto" : "fragmentos adjuntos"}: ${materialKinds}.`
    : "Sin fragmentos adjuntos; se incluye la ficha del libro.";
  const sourceNames = preview.library_sources.slice(0, 3)
    .map((source) => `${source.label} de «${source.work_title}»`).join(", ");
  const sources = preview.library_sources.length
    ? `${preview.library_sources.length} ${preview.library_sources.length === 1 ? "fuente recuperada" : "fuentes recuperadas"}: ${sourceNames}${preview.library_sources.length > 3 ? "…" : ""}.`
    : "Sin fuentes adicionales recuperadas.";
  document.querySelector("#prompt-preview-summary").textContent =
    `Responderá: ${preview.profile.name}. ${provider} ${action} ${contextReviewScope(preview)} ${material} ${sources} La aplicación no contiene el texto completo.`;
  const details = document.querySelector("#prompt-preview-details");
  details.hidden = false;
  details.open = true;
  document.querySelector("#prompt-preview-content").textContent =
    `INSTRUCCIONES DEL PERFIL\n${preview.packet.instructions}\n\nMENSAJES Y CONTEXTO\n${JSON.stringify(preview.packet.input, null, 2)}`;
  details.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function reviewContext() {
  if (!activeConversationId) return;
  const textarea = document.querySelector("#conversation-message");
  const content = textarea.value.trim();
  if (!content) {
    textarea.focus();
    throw new Error("Escribí o prepará un mensaje antes de revisar el contexto.");
  }
  const preview = await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/prompt-preview`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(contextReviewPayload()),
  });
  renderContextReview(preview);
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
  cancelResponseAnimation();
  disposeConversationScroll();
  const conversation = await jsonRequest(`/api/conversations/${encodeURIComponent(identifier)}`);
  activeConversationId = identifier;
  actionDraft = null;
  document.querySelector("#companion-action-draft").hidden = true;
  invalidateContextReview();
  librarySearchResults = []; previewSearchQuery = "";
  document.querySelector("#conversation-empty").hidden = true;
  document.querySelector("#conversation-active").hidden = false;
  setText("active-conversation-profile", conversation.profile_name_snapshot);
  setText("companion-action-profile", conversation.profile_name_snapshot || "Perfil no disponible");
  setText("active-conversation-title", conversationDisplayTitle(conversation));
  const focusConversation = document.querySelector("#focus-conversation-context");
  focusConversation.textContent = `${conversation.profile_name_snapshot || "Perfil no disponible"} · ${conversationDisplayTitle(conversation)}`;
  focusConversation.hidden = false;
  document.querySelector("#active-conversation-title-input").value = conversation.title || "";
  document.querySelector("#conversation-title-form").closest("details").removeAttribute("open");
  const messages = conversation.messages.map(messageCard);
  const container = document.querySelector("#conversation-messages");
  container.replaceChildren(...messages);
  if (!messages.length) {
    const empty = document.createElement("p");
    empty.className = "conversation-message-empty";
    empty.textContent = "La conversación está lista. Escribí el primer mensaje.";
    container.append(empty);
  }
  setupConversationScroll(container);
  scrollConversationToBottom({force: true});
  document.querySelector("#conversation-list").value = identifier;
  await loadContext(identifier);
}

async function loadConversations(preferredId = activeConversationId) {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`);
  renderConversationOptions(data.items, preferredId);
  if (!data.items.length) return;
  const next = data.items.some((item) => item.id === preferredId) ? preferredId : data.items[0].id;
  await openConversation(next);
}

function renderConversationOptions(items, preferredId) {
  const list = document.querySelector("#conversation-list");
  const options = items.map((conversation) => new Option(
    `${conversation.profile_name_snapshot || "Perfil no disponible"} · ${conversationDisplayTitle(conversation)} · ${conversation.message_count} mensajes`, conversation.id,
  ));
  list.replaceChildren(...options);
  list.disabled = !options.length;
  if (!options.length) {
    list.append(new Option("Sin conversaciones", ""));
  }
  if (preferredId && items.some((item) => item.id === preferredId)) list.value = preferredId;
}

async function refreshConversationOptions(preferredId = activeConversationId) {
  const data = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`);
  renderConversationOptions(data.items, preferredId);
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
document.querySelector("#open-new-conversation").addEventListener("click", openNewConversationDialog);
document.querySelector("#exit-companion-focus")?.addEventListener("click", exitCompanionFocus);
document.querySelector("#cancel-new-conversation").addEventListener("click", () => {
  document.querySelector("#new-conversation-dialog").close();
});
document.querySelector("#new-conversation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#new-conversation");
  button.disabled = true;
  try {
    const created = await jsonRequest(`/api/works/${encodeURIComponent(window.WORK_ID)}/conversations`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({profile_id: document.querySelector("#conversation-profile").value, title: document.querySelector("#conversation-title-input").value}),
    });
    document.querySelector("#conversation-title-input").value = "";
    await loadConversations(created.id);
    document.querySelector("#new-conversation-dialog").close();
    document.querySelector("#conversation-message").focus();
  } catch (error) {
    document.querySelector("#conversation-feedback").textContent = error.message;
  } finally { button.disabled = false; }
});
document.querySelector("#mobile-material-toggle").addEventListener("click", (event) => {
  const column = document.querySelector(".material-column");
  const expanded = !column.classList.contains("is-mobile-open");
  column.classList.toggle("is-mobile-open", expanded);
  event.currentTarget.setAttribute("aria-expanded", String(expanded));
});
document.querySelector("#conversation-list").addEventListener("change", (event) => {
  if (event.target.value) openConversation(event.target.value);
});
document.querySelector("#conversation-title-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversationId) return;
  try {
    await jsonRequest(`/api/conversations/${encodeURIComponent(activeConversationId)}/title`, {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({title: document.querySelector("#active-conversation-title-input").value}),
    });
    document.querySelector("#conversation-feedback").textContent = "Título de la conversación actualizado.";
    await loadConversations(activeConversationId);
  } catch (error) {
    document.querySelector("#conversation-feedback").textContent = error.message;
  }
});
document.querySelector("#conversation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversationId) return;
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const textarea = document.querySelector("#conversation-message");
  const content = textarea.value.trim();
  if (!content) return;
  const payload = {
    content, ...currentContextSelection(), ...librarySearchPayload(),
    companion_action_id: currentCompanionActionId(),
  };
  const requestConversationId = activeConversationId;
  const pendingCard = appendTransientExchange(content);
  button.disabled = true;
  button.textContent = "Pensando…";
  form.setAttribute("aria-busy", "true");
  document.querySelector("#conversation-feedback").textContent = "";
  try {
    const result = await jsonRequest(`/api/conversations/${encodeURIComponent(requestConversationId)}/respond`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    if (activeConversationId !== requestConversationId) return;
    form.reset();
    actionDraft = null;
    document.querySelector("#companion-action-draft").hidden = true;
    invalidateContextReview();
    document.querySelector("#conversation-feedback").textContent = result.mode === "draft" ? "Mensaje guardado. No se envió a una IA porque está activo el modo borrador." : "El acompañante respondió.";
    if (result.answer) {
      revealAssistantResponse(pendingCard, result.answer, result.library_sources);
      await refreshConversationOptions(activeConversationId);
    } else {
      await loadConversations(activeConversationId);
    }
  } catch (error) {
    showResponseError(pendingCard, error.message);
    document.querySelector("#conversation-feedback").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Enviar";
    form.removeAttribute("aria-busy");
  }
});
document.querySelector("#library-search-scope").addEventListener("change", (event) => {
  document.querySelector("#library-search-works-label").hidden = event.target.value !== "selected";
  librarySearchResults = []; previewSearchQuery = "";
  renderCompanionActionScope();
  invalidateContextReview();
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
    await loadContext(activeConversationId); invalidateContextReview();
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
  invalidateContextReview();
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
document.querySelector("#context-form").addEventListener("change", () => {
  updateContextSelectionCount();
  invalidateContextReview();
});
document.querySelector("#library-search-enabled").addEventListener("click", (event) => event.stopPropagation());
document.querySelector("#library-search-enabled").addEventListener("change", () => {
  renderCompanionActionScope();
  invalidateContextReview();
});
document.querySelector("#library-search-works").addEventListener("change", () => {
  renderCompanionActionScope();
  invalidateContextReview();
});
document.querySelector("#library-search-results").addEventListener("change", invalidateContextReview);
document.querySelector("#conversation-message").addEventListener("input", invalidateContextReview);
document.querySelector("#review-context").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try { await reviewContext(); }
  catch (error) { document.querySelector("#conversation-feedback").textContent = error.message; }
  finally { button.disabled = false; }
});
document.querySelector("#open-companion-actions").addEventListener("click", openCompanionActionsDialog);
document.querySelector("#companion-action-search").addEventListener("input", filterCompanionActions);
document.querySelector("#companion-actions-dialog").addEventListener("close", () => {
  if (actionDialogReturnsFocus) document.querySelector("#open-companion-actions")?.focus();
  actionDialogReturnsFocus = true;
});
document.querySelector("#clear-action-draft").addEventListener("click", discardCompanionActionDraft);
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
    setCompanionFocus(selected === "companion");
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

async function loadCoverDialogData() {
  const feedback = document.querySelector("#cover-dialog-feedback");
  const grid = document.querySelector("#cover-candidates-grid");
  if (feedback) feedback.textContent = "";
  if (grid) grid.innerHTML = "<p>Cargando candidatas…</p>";

  try {
    const data = await jsonRequest(`/api/cover-setup/${encodeURIComponent(window.WORK_ID)}`);
    renderCoverCandidates(data);
  } catch (error) {
    if (grid) grid.innerHTML = "<p class='is-error'>No se pudieron cargar las candidatas de portada.</p>";
  }
}

function renderCoverCandidates(data) {
  const grid = document.querySelector("#cover-candidates-grid");
  if (!grid) return;
  if (!data.candidates || data.candidates.length === 0) {
    grid.innerHTML = "<p class='empty-candidates'>No hay portadas candidatas registradas todavía. Podés buscar en internet.</p>";
    return;
  }

  const cards = data.candidates.map((candidate) => {
    const isSelected = data.status === "confirmed" && data.selected_path === candidate.path;
    const card = document.createElement("article");
    card.className = `cover-candidate-card${isSelected ? " is-selected" : ""}`;
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");

    const img = document.createElement("img");
    img.src = `/static/covers/${encodeURIComponent(candidate.path)}`;
    img.alt = `Portada ${candidate.source}`;

    const info = document.createElement("span");
    info.textContent = `${candidate.source}${isSelected ? " (Actual)" : ""}`;

    card.append(img, info);

    const applyCover = async () => {
      if (isSelected) return;
      const feedback = document.querySelector("#cover-dialog-feedback");
      if (feedback) feedback.textContent = "Guardando portada…";
      try {
        await jsonRequest(`/api/cover-setup/${encodeURIComponent(window.WORK_ID)}`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({selected_path: candidate.path, review_status: "confirmed"}),
        });
        if (feedback) feedback.textContent = "Portada actualizada correctamente.";
        await loadBook();
        await loadCoverDialogData();
      } catch (err) {
        if (feedback) feedback.textContent = err.message || "Error al actualizar la portada.";
      }
    };

    card.addEventListener("click", applyCover);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        applyCover();
      }
    });

    return card;
  });

  grid.replaceChildren(...cards);
}

async function searchOnlineCoverForBook() {
  const button = document.querySelector("#search-online-cover");
  const feedback = document.querySelector("#cover-dialog-feedback");
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Buscando…";
  }
  if (feedback) feedback.textContent = "Buscando portadas en internet, esto puede tomar unos segundos…";

  try {
    const res = await jsonRequest(`/api/cover-setup/${encodeURIComponent(window.WORK_ID)}/search`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
    if (feedback) {
      feedback.textContent = res.added > 0 
        ? `Se agregaron ${res.added} nuevas candidatas desde internet.`
        : "No se encontraron nuevas portadas en internet.";
    }
    await loadBook();
    await loadCoverDialogData();
  } catch (err) {
    if (feedback) feedback.textContent = err.message || "Error durante la búsqueda online.";
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "🔎 Buscar en internet";
    }
  }
}

async function removeCoverForBook() {
  const feedback = document.querySelector("#cover-dialog-feedback");
  if (feedback) feedback.textContent = "Quitando portada…";
  try {
    await jsonRequest(`/api/cover-setup/${encodeURIComponent(window.WORK_ID)}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({selected_path: null, review_status: "none"}),
    });
    if (feedback) feedback.textContent = "Se quitó la portada del libro.";
    await loadBook();
    await loadCoverDialogData();
  } catch (err) {
    if (feedback) feedback.textContent = err.message || "Error al quitar la portada.";
  }
}

async function uploadLocalCoverForBook(file) {
  if (!file) return;
  const feedback = document.querySelector("#cover-dialog-feedback");
  if (feedback) feedback.textContent = "Subiendo imagen…";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`/api/cover-setup/${encodeURIComponent(window.WORK_ID)}/upload`, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "No se pudo subir la imagen");

    if (feedback) feedback.textContent = "Portada subida y seleccionada correctamente.";
    await loadBook();
    await loadCoverDialogData();
  } catch (err) {
    if (feedback) feedback.textContent = err.message || "Error al subir la imagen.";
  }
}

document.querySelector("#open-cover-dialog")?.addEventListener("click", () => {
  const dialog = document.querySelector("#book-cover-dialog");
  if (dialog) {
    dialog.showModal();
    loadCoverDialogData();
  }
});
document.querySelector("#close-cover-dialog")?.addEventListener("click", () => {
  document.querySelector("#book-cover-dialog")?.close();
});
document.querySelector("#search-online-cover")?.addEventListener("click", searchOnlineCoverForBook);
document.querySelector("#remove-cover")?.addEventListener("click", removeCoverForBook);
document.querySelector("#upload-cover-input")?.addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (file) {
    uploadLocalCoverForBook(file);
    event.target.value = "";
  }
});

loadBook().catch(showBookLoadError);
loadAnnotations();
loadPersonal();
loadOptions();
loadConversations();
loadProviderStatus();
loadCompanionActions();
