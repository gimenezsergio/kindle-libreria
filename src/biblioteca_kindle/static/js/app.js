const formatNumber = new Intl.NumberFormat("es-AR");
const state = document.querySelector(".library-state");
const setText = (id, value) => { document.querySelector(`#${id}`).textContent = value; };

function showSummary(data) {
  const { catalog, annotations, organization, last_sync: lastSync } = data;
  state.classList.add("is-ready");
  setText("state-title", `${formatNumber.format(catalog.works)} obras disponibles`);
  setText("state-detail", "La biblioteca local está conectada.");
  setText("works-count", formatNumber.format(catalog.works));
  setText("editions-detail", `${formatNumber.format(catalog.editions)} ediciones locales`);
  setText("annotations-count", formatNumber.format(annotations.total));
  setText("annotations-detail", `${formatNumber.format(annotations.highlight)} subrayados`);
  setText("present-count", formatNumber.format(catalog.present));
  setText("presence-detail", `${formatNumber.format(catalog.absent)} ausentes`);
  setText("collections-count", formatNumber.format(organization.collections));
  setText("organization-detail", `${organization.notes} notas · ${organization.relations} relaciones`);
  setText("annotation-total", formatNumber.format(annotations.total));
  setText("highlight-count", formatNumber.format(annotations.highlight));
  setText("note-count", formatNumber.format(annotations.note));
  setText("bookmark-count", formatNumber.format(annotations.bookmark));
  setText("warning-count", formatNumber.format(data.warnings));
  setText("review-count", formatNumber.format(catalog.review));
  setText("provisional-detail", `${formatNumber.format(catalog.provisional)} obras conservan una identidad provisional.`);
  if (lastSync) {
    setText("sync-date", new Date(lastSync.completed_at).toLocaleString("es-AR", { dateStyle: "long", timeStyle: "short" }));
    setText("source-count", formatNumber.format(lastSync.source_count));
  } else {
    setText("sync-date", "Todavía no hay sincronizaciones completas");
    setText("source-count", "0");
  }
}

function showError() {
  state.classList.add("is-error");
  setText("state-title", "No pudimos consultar la biblioteca");
  setText("state-detail", "Comprobá que la base local esté disponible.");
}

fetch("/api/summary")
  .then((response) => {
    if (!response.ok) throw new Error("summary unavailable");
    return response.json();
  })
  .then(showSummary)
  .catch(showError);
