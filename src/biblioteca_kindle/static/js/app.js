const state = document.querySelector(".library-state");
const title = document.querySelector("#state-title");
const detail = document.querySelector("#state-detail");

fetch("/api/status")
  .then((response) => {
    if (!response.ok) throw new Error("status unavailable");
    return response.json();
  })
  .then((data) => {
    if (!data.database_available) {
      state.classList.add("is-error");
      title.textContent = "La base local todavía no está disponible";
      detail.textContent = "Podrás conectarla sin necesidad del Kindle.";
      return;
    }
    state.classList.add("is-ready");
    title.textContent = `${data.works} obras disponibles`;
    detail.textContent = "La biblioteca local está conectada.";
  })
  .catch(() => {
    state.classList.add("is-error");
    title.textContent = "No pudimos consultar la biblioteca";
    detail.textContent = "Volvé a intentar cuando el servidor esté disponible.";
  });
