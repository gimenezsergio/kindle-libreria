const formatNumber = new Intl.NumberFormat("es-AR");
const list = document.querySelector("#book-list");
const empty = document.querySelector("#empty-state");
const controls = document.querySelector("#catalog-form");
let page = 1;
let pages = 1;
let debounce;

const text = (element, value) => { element.textContent = value; };

function bookRow(book) {
  const article = document.createElement("article");
  article.className = "book-row";
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
  const status = document.createElement("span");
  status.className = "identity-status";
  text(status, book.merge_status === "normal" ? "Identidad confirmada" : book.merge_status === "review" ? "Revisar identidad" : "Identidad provisional");
  metadata.append(presence, annotations, status);
  article.append(identity, metadata);
  return article;
}

async function loadBooks() {
  list.setAttribute("aria-busy", "true");
  const params = new URLSearchParams({
    q: document.querySelector("#query").value,
    presence: document.querySelector("#presence").value,
    annotated: document.querySelector("#annotated").checked,
    sort: document.querySelector("#sort").value,
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

controls.addEventListener("input", () => {
  page = 1;
  clearTimeout(debounce);
  debounce = setTimeout(loadBooks, 180);
});
document.querySelector("#previous").addEventListener("click", () => { if (page > 1) { page -= 1; loadBooks(); } });
document.querySelector("#next").addEventListener("click", () => { if (page < pages) { page += 1; loadBooks(); } });
loadBooks();
