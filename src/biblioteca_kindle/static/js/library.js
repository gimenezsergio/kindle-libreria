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
  metadata.append(presence, annotations);
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

controls.addEventListener("input", () => {
  page = 1;
  clearTimeout(debounce);
  debounce = setTimeout(loadBooks, 180);
});
document.querySelector("#previous").addEventListener("click", () => { if (page > 1) { page -= 1; loadBooks(); } });
document.querySelector("#next").addEventListener("click", () => { if (page < pages) { page += 1; loadBooks(); } });
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

applyView();
loadCollections();
loadBooks();

