const formatNumber = new Intl.NumberFormat("es-AR");
const list = document.querySelector("#book-list");
const empty = document.querySelector("#empty-state");
const controls = document.querySelector("#catalog-form");

const chipsContainer = document.querySelector("#collection-chips");
const toolbar = document.querySelector("#collection-toolbar");
const selectedNameLabel = document.querySelector("#selected-collection-name");
const editBtn = document.querySelector("#edit-collection-btn");
const deleteBtn = document.querySelector("#delete-collection-btn");

const modal = document.querySelector("#collection-modal");
const modalForm = document.querySelector("#collection-form");
const modalTitle = document.querySelector("#modal-title");
const inputId = document.querySelector("#collection-id-input");
const inputName = document.querySelector("#collection-name-input");
const inputDesc = document.querySelector("#collection-desc-input");
const cancelModalBtn = document.querySelector("#cancel-collection-btn");

let page = 1;
let pages = 1;
let debounce;
let view = localStorage.getItem("library-view") === "list" ? "list" : "grid";

let selectedCollection = null; // null means 'Todas'
let collectionsData = [];

const text = (element, value) => { element.textContent = value; };

function bookRow(book) {
  const article = document.createElement("article");
  article.className = "book-row";
  article.tabIndex = 0;
  article.setAttribute("role", "link");
  article.setAttribute("aria-label", `Abrir ${book.title}`);
  const open = () => { window.location.href = `/library/${encodeURIComponent(book.id)}`; };
  article.addEventListener("click", open);
  article.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
  const cover = document.createElement("div");
  cover.className = "book-cover";
  if (book.cover) {
    const image = document.createElement("img");
    image.src = `/static/covers/${encodeURIComponent(book.cover.path)}`;
    image.alt = `Portada de ${book.title}`;
    image.loading = "lazy";
    image.title = `Fuente: ${book.cover.source}`;
    cover.append(image);
  } else {
    cover.classList.add("book-cover-placeholder");
    const initials = book.title.split(/\s+/).filter(Boolean).slice(0, 3).map((word) => word[0]).join("");
    const mark = document.createElement("span");
    text(mark, initials || "B");
    cover.append(mark);
  }
  const identity = document.createElement("div");
  identity.className = "book-identity";
  const title = document.createElement("h2");
  text(title, book.title);
  const author = document.createElement("p");
  text(author, book.authors || "Autor no disponible");
  identity.append(title, author);

  const metadata = document.createElement("div");
  metadata.className = "book-metadata";
  const presence = document.createElement("span");
  presence.className = `presence ${book.presence}`;
  text(presence, book.presence === "present" ? "En el Kindle" : "Ausente");
  const annotations = document.createElement("span");
  text(annotations, `${formatNumber.format(book.annotation_count)} anotaciones`);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "book-delete-btn";
  deleteBtn.title = "Borrar libro";
  deleteBtn.setAttribute("aria-label", `Borrar ${book.title}`);
  deleteBtn.style.padding = "0.2rem 0.4rem";
  deleteBtn.style.border = "none";
  deleteBtn.style.background = "transparent";
  deleteBtn.style.cursor = "pointer";
  deleteBtn.style.fontSize = "0.85rem";
  deleteBtn.style.opacity = "0.7";
  text(deleteBtn, "🗑️");

  deleteBtn.addEventListener("mouseenter", () => { deleteBtn.style.opacity = "1"; });
  deleteBtn.addEventListener("mouseleave", () => { deleteBtn.style.opacity = "0.7"; });

  deleteBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (confirm(`¿Estás seguro de que querés borrar "${book.title}" de tu biblioteca?`)) {
      try {
        const res = await fetch(`/api/works/${encodeURIComponent(book.id)}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json();
          alert(`Error: ${err.error || "No se pudo borrar el libro"}`);
          return;
        }
        await loadCollections();
        loadBooks();
      } catch {
        alert("Error de conexión al borrar el libro.");
      }
    }
  });

  metadata.append(presence, annotations, deleteBtn);
  article.append(cover, identity, metadata);
  return article;
}

function applyView() {
  list.classList.toggle("is-grid", view === "grid");
  list.classList.toggle("is-list", view === "list");
  document.querySelector("#grid-view").setAttribute("aria-pressed", String(view === "grid"));
  document.querySelector("#list-view").setAttribute("aria-pressed", String(view === "list"));
}

async function loadBooks() {
  list.setAttribute("aria-busy", "true");
  const params = new URLSearchParams({
    q: document.querySelector("#query").value,
    presence: document.querySelector("#presence").value,
    annotated: document.querySelector("#annotated").checked,
    sort: document.querySelector("#sort").value,
    collection: selectedCollection ? selectedCollection.id : "",
    page,
  });
  try {
    const response = await fetch(`/api/works?${params}`);
    if (!response.ok) throw new Error("works unavailable");
    const data = await response.json();
    pages = data.pages;
    list.replaceChildren(...data.items.map(bookRow));
    empty.hidden = data.items.length > 0;
    text(document.querySelector("#result-count"), `${formatNumber.format(data.total)} obras`);
    text(document.querySelector("#page-status"), `Página ${data.page} de ${data.pages}`);
    text(document.querySelector("#pagination-status"), `${data.page} / ${data.pages}`);
    document.querySelector("#previous").disabled = data.page <= 1;
    document.querySelector("#next").disabled = data.page >= data.pages;
  } catch {
    list.replaceChildren();
    empty.hidden = false;
    empty.querySelector("strong").textContent = "No pudimos consultar la biblioteca";
    empty.querySelector("span").textContent = "Comprobá que la base local esté disponible.";
  } finally {
    list.removeAttribute("aria-busy");
  }
}

async function loadCollections() {
  if (!chipsContainer) return;
  try {
    const res = await fetch("/api/collections");
    if (!res.ok) return;
    const data = await res.json();
    collectionsData = data.items || [];
    renderChips();
  } catch (err) {
    console.error("Error al cargar colecciones:", err);
  }
}

function renderChips() {
  if (!chipsContainer) return;
  chipsContainer.replaceChildren();

  // 1. 'Todas' Chip
  const allChip = document.createElement("button");
  allChip.type = "button";
  allChip.className = `chip ${selectedCollection === null ? "is-active" : ""}`;
  allChip.setAttribute("aria-pressed", String(selectedCollection === null));
  text(allChip, "Todas");
  allChip.addEventListener("click", () => {
    selectedCollection = null;
    page = 1;
    updateToolbar();
    renderChips();
    loadBooks();
  });
  chipsContainer.append(allChip);

  // 2. Collection Chips
  collectionsData.forEach((col) => {
    const chip = document.createElement("button");
    chip.type = "button";
    const isActive = selectedCollection && selectedCollection.id === col.id;
    chip.className = `chip ${isActive ? "is-active" : ""}`;
    chip.setAttribute("aria-pressed", String(isActive));
    
    const nameSpan = document.createElement("span");
    text(nameSpan, col.name);
    const countSpan = document.createElement("span");
    countSpan.className = "chip-count";
    text(countSpan, formatNumber.format(col.works_count || 0));

    chip.append(nameSpan, countSpan);

    chip.addEventListener("click", () => {
      selectedCollection = col;
      page = 1;
      updateToolbar();
      renderChips();
      loadBooks();
    });
    chipsContainer.append(chip);
  });

  // 3. '+ Nueva' Chip
  const addChip = document.createElement("button");
  addChip.type = "button";
  addChip.className = "chip chip-add";
  text(addChip, "+ Nueva colección");
  addChip.addEventListener("click", openCreateModal);
  chipsContainer.append(addChip);
}

function updateToolbar() {
  if (!toolbar) return;
  if (selectedCollection) {
    toolbar.hidden = false;
    text(selectedNameLabel, selectedCollection.name);
    const isSystem = Boolean(selectedCollection.is_system || selectedCollection.id === "uncategorized");
    if (editBtn) editBtn.hidden = isSystem;
    if (deleteBtn) deleteBtn.hidden = isSystem;
    if (organizeBtn) organizeBtn.hidden = isSystem;
  } else {
    toolbar.hidden = true;
  }
}

function openCreateModal() {
  if (!modal) return;
  modalTitle.textContent = "Nueva Colección";
  inputId.value = "";
  inputName.value = "";
  inputDesc.value = "";
  if (modal.showModal) modal.showModal(); else modal.setAttribute("open", "");
}

function openEditModal() {
  if (!modal || !selectedCollection) return;
  modalTitle.textContent = "Editar Colección";
  inputId.value = selectedCollection.id;
  inputName.value = selectedCollection.name;
  inputDesc.value = selectedCollection.description || "";
  if (modal.showModal) modal.showModal(); else modal.setAttribute("open", "");
}

function closeModal() {
  if (!modal) return;
  if (modal.close) modal.close(); else modal.removeAttribute("open");
}

if (modalForm) {
  modalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = inputId.value;
    const name = inputName.value.trim();
    const description = inputDesc.value.trim() || null;
    if (!name) return;

    try {
      const isEdit = Boolean(id);
      const url = isEdit ? `/api/collections/${encodeURIComponent(id)}` : "/api/collections";
      const method = isEdit ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });

      if (!res.ok) {
        const errData = await res.json();
        alert(`Error: ${errData.error || "No se pudo guardar la colección"}`);
        return;
      }

      closeModal();
      await loadCollections();
      if (isEdit && selectedCollection && selectedCollection.id === id) {
        selectedCollection = collectionsData.find((c) => c.id === id) || null;
        updateToolbar();
      }
      loadBooks();
    } catch {
      alert("Error de conexión al guardar la colección.");
    }
  });
}

cancelModalBtn?.addEventListener("click", closeModal);
editBtn?.addEventListener("click", openEditModal);

deleteBtn?.addEventListener("click", async () => {
  if (!selectedCollection) return;
  const confirmDelete = confirm(`¿Estás seguro de eliminar la colección "${selectedCollection.name}"?\n(Los libros permanecerán en la biblioteca).`);
  if (!confirmDelete) return;

  try {
    const res = await fetch(`/api/collections/${encodeURIComponent(selectedCollection.id)}`, { method: "DELETE" });
    if (!res.ok) {
      const errData = await res.json();
      alert(`Error: ${errData.error || "No se pudo eliminar la colección"}`);
      return;
    }
    selectedCollection = null;
    updateToolbar();
    await loadCollections();
    page = 1;
    loadBooks();
  } catch {
    alert("Error de conexión al eliminar la colección.");
  }
});

function scrollToCatalogTop() {
  const target = document.querySelector("#collection-chips") || document.querySelector("#catalog-form") || list;
  if (target) {
    const yOffset = -90;
    const y = target.getBoundingClientRect().top + window.pageYOffset + yOffset;
    window.scrollTo({ top: y, behavior: "smooth" });
  }
}

controls.addEventListener("input", () => {
  page = 1;
  clearTimeout(debounce);
  debounce = setTimeout(loadBooks, 180);
});
document.querySelector("#previous").addEventListener("click", () => {
  if (page > 1) {
    page -= 1;
    loadBooks();
    scrollToCatalogTop();
  }
});
document.querySelector("#next").addEventListener("click", () => {
  if (page < pages) {
    page += 1;
    loadBooks();
    scrollToCatalogTop();
  }
});
document.querySelector("#grid-view").addEventListener("click", () => { view = "grid"; localStorage.setItem("library-view", view); applyView(); });
document.querySelector("#list-view").addEventListener("click", () => { view = "list"; localStorage.setItem("library-view", view); applyView(); });

// Selector masivo por colección
const organizeBtn = document.querySelector("#organize-collection-btn");
const pickerModal = document.querySelector("#collection-picker-dialog");
const pickerTitle = document.querySelector("#picker-dialog-title");
const pickerSearch = document.querySelector("#picker-search-input");
const pickerCount = document.querySelector("#picker-selection-count");
const pickerList = document.querySelector("#picker-book-list");
const cancelPickerBtn = document.querySelector("#cancel-picker-btn");
const closePickerBtn = document.querySelector("#close-picker-btn");
const savePickerBtn = document.querySelector("#save-picker-btn");

let allWorkOptions = [];
let selectedWorkIds = new Set();

async function openPickerModal() {
  if (!pickerModal || !selectedCollection) return;
  text(pickerTitle, `Organizar libros en "${selectedCollection.name}"`);
  pickerSearch.value = "";
  pickerList.replaceChildren();
  const loadingP = document.createElement("p");
  loadingP.className = "picker-loading";
  text(loadingP, "Cargando catálogo de libros…");
  pickerList.append(loadingP);

  if (pickerModal.showModal) pickerModal.showModal(); else pickerModal.setAttribute("open", "");

  try {
    const [worksRes, assignedRes] = await Promise.all([
      fetch("/api/work-options"),
      fetch(`/api/collections/${encodeURIComponent(selectedCollection.id)}/works`)
    ]);

    if (!worksRes.ok || !assignedRes.ok) throw new Error("Error al obtener datos");
    
    const worksData = await worksRes.json();
    const assignedData = await assignedRes.json();

    allWorkOptions = worksData.items || [];
    selectedWorkIds = new Set(assignedData.work_ids || []);

    renderPickerList();
  } catch {
    pickerList.replaceChildren();
    const errP = document.createElement("p");
    errP.className = "picker-error";
    text(errP, "Error al cargar la lista de libros.");
    pickerList.append(errP);
  }
}

function updatePickerCount() {
  if (pickerCount) {
    text(pickerCount, `${formatNumber.format(selectedWorkIds.size)} seleccionados`);
  }
}

function renderPickerList() {
  if (!pickerList) return;
  const filterText = (pickerSearch.value || "").trim().toLowerCase();

  const filtered = allWorkOptions.filter((work) =>
    !filterText || work.title.toLowerCase().includes(filterText)
  );

  if (filtered.length === 0) {
    pickerList.replaceChildren();
    const emptyP = document.createElement("p");
    emptyP.className = "picker-empty";
    text(emptyP, filterText ? "No hay coincidencias con la búsqueda." : "No hay libros registrados.");
    pickerList.append(emptyP);
    updatePickerCount();
    return;
  }

  const items = filtered.map((work) => {
    const label = document.createElement("label");
    label.className = "picker-item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = work.id;
    checkbox.checked = selectedWorkIds.has(work.id);

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedWorkIds.add(work.id);
      } else {
        selectedWorkIds.delete(work.id);
      }
      updatePickerCount();
    });

    const titleSpan = document.createElement("span");
    titleSpan.className = "picker-item-title";
    text(titleSpan, work.title);

    label.append(checkbox, titleSpan);
    return label;
  });

  pickerList.replaceChildren(...items);
  updatePickerCount();
}

function closePickerModal() {
  if (!pickerModal) return;
  if (pickerModal.close) pickerModal.close(); else pickerModal.removeAttribute("open");
}

organizeBtn?.addEventListener("click", openPickerModal);
cancelPickerBtn?.addEventListener("click", closePickerModal);
closePickerBtn?.addEventListener("click", closePickerModal);

pickerSearch?.addEventListener("input", renderPickerList);

savePickerBtn?.addEventListener("click", async () => {
  if (!selectedCollection) return;
  savePickerBtn.disabled = true;
  text(savePickerBtn, "Guardando…");

  try {
    const res = await fetch(`/api/collections/${encodeURIComponent(selectedCollection.id)}/works`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ work_ids: Array.from(selectedWorkIds) }),
    });

    if (!res.ok) {
      const err = await res.json();
      alert(`Error: ${err.error || "No se pudieron guardar las asignaciones."}`);
      return;
    }

    closePickerModal();
    await loadCollections();
    if (selectedCollection) {
      selectedCollection = collectionsData.find((c) => c.id === selectedCollection.id) || null;
      updateToolbar();
    }
    loadBooks();
  } catch {
    alert("Error de conexión al guardar los cambios.");
  } finally {
    savePickerBtn.disabled = false;
    text(savePickerBtn, "Guardar cambios");
  }
});

const recentSection = document.querySelector("#recent-section");
const recentGrid = document.querySelector("#recent-grid");

function recentCard(book) {
  const card = document.createElement("div");
  card.className = "recent-card";
  card.tabIndex = 0;
  card.setAttribute("role", "link");
  card.setAttribute("aria-label", `Abrir ${book.title}`);

  const open = () => { window.location.href = `/library/${encodeURIComponent(book.id)}`; };
  card.addEventListener("click", open);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  });

  const cover = document.createElement("div");
  cover.className = "recent-cover";
  if (book.cover) {
    const img = document.createElement("img");
    img.src = `/static/covers/${encodeURIComponent(book.cover.path)}`;
    img.alt = `Portada de ${book.title}`;
    img.loading = "lazy";
    cover.append(img);
  } else {
    cover.classList.add("recent-cover-placeholder");
    const initials = book.title.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("");
    const mark = document.createElement("span");
    text(mark, initials || "B");
    cover.append(mark);
  }

  const info = document.createElement("div");
  info.className = "recent-info";

  const title = document.createElement("strong");
  title.className = "recent-book-title";
  text(title, book.title);

  const author = document.createElement("span");
  author.className = "recent-book-author";
  text(author, book.authors || "Autor no disponible");

  info.append(title, author);

  const dismissBtn = document.createElement("button");
  dismissBtn.type = "button";
  dismissBtn.className = "recent-dismiss-btn";
  dismissBtn.title = "Quitar de últimos abiertos";
  dismissBtn.setAttribute("aria-label", `Quitar ${book.title} de últimos abiertos`);
  text(dismissBtn, "×");

  dismissBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const res = await fetch(`/api/recently-opened/${encodeURIComponent(book.id)}`, { method: "DELETE" });
      if (res.ok) {
        loadRecentlyOpened();
      }
    } catch {
      // Ignorar errores temporales
    }
  });

  card.append(cover, info, dismissBtn);
  return card;
}

async function loadRecentlyOpened() {
  if (!recentSection || !recentGrid) return;
  try {
    const res = await fetch("/api/recently-opened");
    if (!res.ok) return;
    const data = await res.json();
    const items = data.items || [];
    if (items.length === 0) {
      recentSection.hidden = true;
    } else {
      recentGrid.replaceChildren(...items.map(recentCard));
      recentSection.hidden = false;
    }
  } catch (err) {
    console.error("Error al cargar últimos abiertos:", err);
  }
}

applyView();
loadCollections();
loadBooks();
loadRecentlyOpened();

// Alta de obras (Manual y Buscador Externo)
const openAddWorkBtn = document.querySelector("#open-add-work-btn");
const addWorkDialog = document.querySelector("#add-work-dialog");
const closeAddWorkBtn = document.querySelector("#close-add-work-btn");
const tabExternalBtn = document.querySelector("#tab-external-btn");
const tabManualBtn = document.querySelector("#tab-manual-btn");
const tabExternalContent = document.querySelector("#tab-external-content");
const manualWorkForm = document.querySelector("#manual-work-form");
const externalSearchForm = document.querySelector("#external-search-form");
const externalSearchInput = document.querySelector("#external-search-input");
const externalSearchResults = document.querySelector("#external-search-results");
const externalSearchBtn = document.querySelector("#external-search-btn");
const manualTitleInput = document.querySelector("#manual-title-input");
const manualAuthorInput = document.querySelector("#manual-author-input");
const manualDisplayTitleInput = document.querySelector("#manual-display-title-input");
const cancelManualBtn = document.querySelector("#cancel-manual-btn");

function switchTab(tab) {
  if (tab === "external") {
    tabExternalContent.hidden = false;
    manualWorkForm.hidden = true;
    tabExternalBtn.style.fontWeight = "bold";
    tabExternalBtn.style.background = "var(--bg-hover, #eef2ff)";
    tabManualBtn.style.fontWeight = "normal";
    tabManualBtn.style.background = "transparent";
  } else {
    tabExternalContent.hidden = true;
    manualWorkForm.hidden = false;
    tabManualBtn.style.fontWeight = "bold";
    tabManualBtn.style.background = "var(--bg-hover, #eef2ff)";
    tabExternalBtn.style.fontWeight = "normal";
    tabExternalBtn.style.background = "transparent";
  }
}

function openAddWorkModal() {
  if (!addWorkDialog) return;
  switchTab("external");
  externalSearchInput.value = "";
  externalSearchResults.replaceChildren();
  const initMsg = document.createElement("p");
  initMsg.className = "picker-loading";
  initMsg.style.textAlign = "center";
  initMsg.style.margin = "1rem 0";
  initMsg.style.color = "var(--text-muted, #666)";
  text(initMsg, "Escribí el nombre de un libro o autor para buscar en OpenLibrary.");
  externalSearchResults.append(initMsg);

  manualTitleInput.value = "";
  manualAuthorInput.value = "";
  manualDisplayTitleInput.value = "";

  if (addWorkDialog.showModal) addWorkDialog.showModal(); else addWorkDialog.setAttribute("open", "");
}

function closeAddWorkModal() {
  if (!addWorkDialog) return;
  if (addWorkDialog.close) addWorkDialog.close(); else addWorkDialog.removeAttribute("open");
}

openAddWorkBtn?.addEventListener("click", openAddWorkModal);
closeAddWorkBtn?.addEventListener("click", closeAddWorkModal);
cancelManualBtn?.addEventListener("click", closeAddWorkModal);

tabExternalBtn?.addEventListener("click", () => switchTab("external"));
tabManualBtn?.addEventListener("click", () => switchTab("manual"));

externalSearchForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = externalSearchInput.value.trim();
  if (!query) return;

  externalSearchBtn.disabled = true;
  text(externalSearchBtn, "Buscando…");
  externalSearchResults.replaceChildren();
  const loadingP = document.createElement("p");
  loadingP.className = "picker-loading";
  loadingP.style.textAlign = "center";
  loadingP.style.margin = "1rem 0";
  text(loadingP, "Buscando en OpenLibrary…");
  externalSearchResults.append(loadingP);

  try {
    const res = await fetch(`/api/external-works/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error("Error en el buscador");
    const data = await res.json();
    const results = data.results || [];

    if (results.length === 0) {
      externalSearchResults.replaceChildren();
      const wrap = document.createElement("div");
      wrap.style.textAlign = "center";
      wrap.style.margin = "1.5rem 0";

      const noRes = document.createElement("p");
      noRes.className = "picker-empty";
      text(noRes, `No se encontró en OpenLibrary. Podés crearlo manualmente.`);
      
      const createManualBtn = document.createElement("button");
      createManualBtn.type = "button";
      createManualBtn.className = "btn-subtle btn-accent";
      createManualBtn.style.marginTop = "0.75rem";
      text(createManualBtn, `✍️ Cargar "${query}" en Ficha Manual`);
      createManualBtn.addEventListener("click", () => {
        switchTab("manual");
        if (!manualTitleInput.value) {
          manualTitleInput.value = query;
        }
      });

      wrap.append(noRes, createManualBtn);
      externalSearchResults.append(wrap);
      return;
    }

    const items = results.map((book) => {
      const card = document.createElement("div");
      card.style.display = "flex";
      card.style.alignItems = "center";
      card.style.gap = "0.75rem";
      card.style.padding = "0.6rem";
      card.style.border = "1px solid var(--border-color, #e5e7eb)";
      card.style.borderRadius = "8px";
      card.style.background = "var(--bg-surface, #fff)";

      if (book.cover_url) {
        const img = document.createElement("img");
        img.src = book.cover_url;
        img.alt = `Portada de ${book.title}`;
        img.style.width = "40px";
        img.style.height = "56px";
        img.style.objectFit = "cover";
        img.style.borderRadius = "4px";
        card.append(img);
      } else {
        const placeholder = document.createElement("div");
        placeholder.style.width = "40px";
        placeholder.style.height = "56px";
        placeholder.style.background = "var(--bg-muted, #f3f4f6)";
        placeholder.style.borderRadius = "4px";
        placeholder.style.display = "flex";
        placeholder.style.alignItems = "center";
        placeholder.style.justifyContent = "center";
        placeholder.style.fontSize = "0.8rem";
        placeholder.style.color = "var(--text-muted, #9ca3af)";
        text(placeholder, "Sin foto");
        card.append(placeholder);
      }

      const info = document.createElement("div");
      info.style.flex = "1";
      info.style.minWidth = "0";

      const titleEl = document.createElement("strong");
      titleEl.style.display = "block";
      titleEl.style.fontSize = "0.95rem";
      titleEl.style.whiteSpace = "nowrap";
      titleEl.style.overflow = "hidden";
      titleEl.style.textOverflow = "ellipsis";
      text(titleEl, book.title);

      const authorEl = document.createElement("span");
      authorEl.style.display = "block";
      authorEl.style.fontSize = "0.85rem";
      authorEl.style.color = "var(--text-muted, #666)";
      const authorText = (book.authors || []).join(", ") || "Autor desconocido";
      const yearText = book.first_publish_year ? ` (${book.first_publish_year})` : "";
      text(authorEl, `${authorText}${yearText}`);

      info.append(titleEl, authorEl);

      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "btn-subtle btn-accent";
      addBtn.style.fontSize = "0.85rem";
      addBtn.style.whiteSpace = "nowrap";
      text(addBtn, "➕ Añadir");

      addBtn.addEventListener("click", async () => {
        addBtn.disabled = true;
        text(addBtn, "Guardando…");
        try {
          const importRes = await fetch("/api/works", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title: book.title,
              author: authorText !== "Autor desconocido" ? authorText : "",
              publish_year: book.first_publish_year,
              cover_i: book.cover_i,
            }),
          });
          if (!importRes.ok) {
            const err = await importRes.json();
            alert(`Error: ${err.error || "No se pudo añadir el libro"}`);
            addBtn.disabled = false;
            text(addBtn, "➕ Añadir");
            return;
          }
          closeAddWorkModal();
          await loadCollections();
          loadBooks();
        } catch {
          alert("Error de conexión al añadir el libro.");
          addBtn.disabled = false;
          text(addBtn, "➕ Añadir");
        }
      });

      card.append(info, addBtn);
      return card;
    });

    externalSearchResults.replaceChildren(...items);
  } catch {
    externalSearchResults.replaceChildren();
    const errP = document.createElement("p");
    errP.className = "picker-error";
    errP.style.textAlign = "center";
    errP.style.margin = "1rem 0";
    text(errP, "No se pudo conectar con el buscador externo.");
    externalSearchResults.append(errP);
  } finally {
    externalSearchBtn.disabled = false;
    text(externalSearchBtn, "Buscar");
  }
});

manualWorkForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = manualTitleInput.value.trim();
  const author = manualAuthorInput.value.trim();
  const display_title = manualDisplayTitleInput.value.trim() || null;

  if (!title) return;

  const saveBtn = document.querySelector("#save-manual-btn");
  if (saveBtn) {
    saveBtn.disabled = true;
    text(saveBtn, "Guardando…");
  }

  try {
    const res = await fetch("/api/works", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, author, display_title }),
    });

    if (!res.ok) {
      const err = await res.json();
      alert(`Error: ${err.error || "No se pudo crear el libro"}`);
      return;
    }

    closeAddWorkModal();
    await loadCollections();
    loadBooks();
  } catch {
    alert("Error de conexión al crear el libro.");
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      text(saveBtn, "Guardar libro");
    }
  }
});

