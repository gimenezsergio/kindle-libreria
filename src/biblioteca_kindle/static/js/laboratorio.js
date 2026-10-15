(function () {
  "use strict";

  const workId = window.WORK_ID;
  if (!workId) return;

  let currentWork = null;
  let allAnnotations = [];
  let currentInquiry = null;
  let selectedAnnotationIds = new Set();

  // Elementos DOM
  const workTitleEl = document.getElementById("lab-work-title");
  const providerPillEl = document.getElementById("lab-provider-pill");
  const quotesListEl = document.getElementById("lab-quotes-list");
  const quoteCounterEl = document.getElementById("lab-quote-counter");
  const outlineCardEl = document.getElementById("lab-outline-card");
  const outlineThesisEl = document.getElementById("outline-thesis-val");
  const outlineObjectionEl = document.getElementById("outline-objection-val");
  const outlineCounterEl = document.getElementById("outline-counter-val");

  const phaseTensionEl = document.getElementById("phase-tension");
  const phaseSparringEl = document.getElementById("phase-sparring");
  const phaseWritingEl = document.getElementById("phase-writing");
  const phaseCompletedEl = document.getElementById("phase-completed");

  const selectedQuotesPreviewEl = document.getElementById("selected-quotes-preview");
  const tensionFormEl = document.getElementById("tension-form");
  const tensionChapterInput = document.getElementById("tension-chapter");
  const tensionQuestionInput = document.getElementById("tension-question");

  const sparringTitleEl = document.getElementById("sparring-question-title");
  const chatMessagesEl = document.getElementById("lab-chat-messages");
  const sparringFormEl = document.getElementById("sparring-composer-form");
  const sparringInputEl = document.getElementById("sparring-input");
  const btnRequestOutline = document.getElementById("btn-request-outline");

  const essayTextEl = document.getElementById("essay-text");
  const currentWordCountEl = document.getElementById("current-word-count");
  const wordCounterBoxEl = document.getElementById("word-counter-box");
  const essayTagsInput = document.getElementById("essay-tags");
  const writingFormEl = document.getElementById("writing-form");
  const btnBackToSparring = document.getElementById("btn-back-to-sparring");

  const completedQuestionEl = document.getElementById("completed-question");
  const completedMetaEl = document.getElementById("completed-meta");
  const completedEssayBodyEl = document.getElementById("completed-essay-body");
  const completedTagsEl = document.getElementById("completed-tags");
  const btnNewFromCompleted = document.getElementById("btn-new-from-completed");
  const btnNewInquiryTop = document.getElementById("lab-new-inquiry-btn");

  const notificationEl = document.getElementById("lab-notification");
  const pastReflectionsBox = document.getElementById("lab-past-reflections-box");
  const pastItemsEl = document.getElementById("lab-past-items");

  function notify(msg, isError = false) {
    if (!notificationEl) return;
    notificationEl.textContent = msg;
    notificationEl.className = "lab-notification " + (isError ? "is-error" : "is-success");
    notificationEl.hidden = false;
    setTimeout(() => {
      notificationEl.hidden = true;
    }, 4500);
  }

  function hideAllPhases() {
    phaseTensionEl.hidden = true;
    phaseSparringEl.hidden = true;
    phaseWritingEl.hidden = true;
    phaseCompletedEl.hidden = true;
  }

  function countWords(str) {
    return (str.trim().match(/\S+/g) || []).length;
  }

  function updateWordCounter() {
    const count = countWords(essayTextEl.value);
    currentWordCountEl.textContent = count;
    if (count >= 300 && count <= 600) {
      wordCounterBoxEl.className = "word-counter-box in-range";
    } else if (count > 600) {
      wordCounterBoxEl.className = "word-counter-box over-range";
    } else {
      wordCounterBoxEl.className = "word-counter-box under-range";
    }
  }

  // Renderizar citas en el panel lateral
  function renderQuotes() {
    if (!allAnnotations || allAnnotations.length === 0) {
      quotesListEl.innerHTML = `<p class="lab-empty-state">No hay citas registradas en este libro.</p>`;
      quoteCounterEl.textContent = "0 citas";
      return;
    }

    quoteCounterEl.textContent = `${allAnnotations.length} cita${allAnnotations.length === 1 ? "" : "s"}`;
    quotesListEl.innerHTML = "";

    allAnnotations.forEach((ann) => {
      const card = document.createElement("div");
      card.className = "lab-quote-card" + (selectedAnnotationIds.has(ann.id) ? " is-selected" : "");
      card.dataset.id = ann.id;

      const hasContext = Boolean(ann.surrounding_before || ann.surrounding_after);

      card.innerHTML = `
        <label class="lab-quote-checkbox-row">
          <input type="checkbox" class="quote-check" ${selectedAnnotationIds.has(ann.id) ? "checked" : ""}>
          <span class="quote-text">«${escapeHtml(ann.text)}»</span>
        </label>
        <div class="quote-meta">
          ${ann.chapter_title ? `<span class="quote-chapter">${escapeHtml(ann.chapter_title)}</span>` : ""}
          ${ann.position ? `<span class="quote-loc">Pos. ${escapeHtml(ann.position)}</span>` : ""}
          ${hasContext ? `<button type="button" class="btn-toggle-context">🔍 Ver contexto</button>` : ""}
        </div>
        ${hasContext ? `
          <div class="quote-context-drawer" hidden>
            ${ann.surrounding_before ? `<p class="context-before">...${escapeHtml(ann.surrounding_before)}</p>` : ""}
            <p class="context-anchor"><strong>[Pasaje subrayado]</strong></p>
            ${ann.surrounding_after ? `<p class="context-after">${escapeHtml(ann.surrounding_after)}...</p>` : ""}
          </div>
        ` : ""}
      `;

      // Checkbox listener
      const check = card.querySelector(".quote-check");
      check.addEventListener("change", (e) => {
        if (e.target.checked) {
          selectedAnnotationIds.add(ann.id);
          card.classList.add("is-selected");
        } else {
          selectedAnnotationIds.delete(ann.id);
          card.classList.remove("is-selected");
        }
        updateSelectedQuotesPreview();
      });

      // Context toggle
      if (hasContext) {
        const toggleBtn = card.querySelector(".btn-toggle-context");
        const drawer = card.querySelector(".quote-context-drawer");
        toggleBtn.addEventListener("click", () => {
          const isHidden = drawer.hidden;
          drawer.hidden = !isHidden;
          toggleBtn.textContent = isHidden ? "✕ Ocultar contexto" : "🔍 Ver contexto";
        });
      }

      quotesListEl.appendChild(card);
    });
  }

  function updateSelectedQuotesPreview() {
    if (selectedAnnotationIds.size === 0) {
      selectedQuotesPreviewEl.innerHTML = `<em>No seleccionaste ninguna cita todavía (podés tildarlas a la izquierda o continuar con una inquietud general).</em>`;
      return;
    }

    const selectedList = allAnnotations.filter((a) => selectedAnnotationIds.has(a.id));
    selectedQuotesPreviewEl.innerHTML = `
      <strong>Pasajes seleccionados (${selectedList.length}):</strong>
      <ul>
        ${selectedList.map((a) => `<li>«${escapeHtml(a.text)}»</li>`).join("")}
      </ul>
    `;
  }

  function renderOutlineCard(inquiry) {
    if (inquiry && inquiry.outline_thesis) {
      outlineThesisEl.textContent = inquiry.outline_thesis;
      outlineObjectionEl.textContent = inquiry.outline_objection || "—";
      outlineCounterEl.textContent = inquiry.outline_counterargument || "—";
      outlineCardEl.hidden = false;
    } else {
      outlineCardEl.hidden = true;
    }
  }

  function renderPastReflections(inquiries) {
    const completed = inquiries.filter((i) => i.status === "completed");
    if (!completed || completed.length === 0) {
      pastReflectionsBox.hidden = true;
      return;
    }

    pastReflectionsBox.hidden = false;
    pastItemsEl.innerHTML = "";
    completed.forEach((item) => {
      const el = document.createElement("div");
      el.className = "past-reflection-item";
      el.innerHTML = `
        <div class="past-item-q">${escapeHtml(item.dilemma_question)}</div>
        <div class="past-item-meta">${item.word_count || 0} palabras · ${item.completed_at ? item.completed_at.slice(0, 10) : ""}</div>
      `;
      el.addEventListener("click", () => {
        loadInquiry(item.id);
      });
      pastItemsEl.appendChild(el);
    });
  }

  // Transiciones de Fases
  function showPhaseTension() {
    hideAllPhases();
    phaseTensionEl.hidden = false;
    tensionQuestionInput.focus();
  }

  function showPhaseSparring(inquiry) {
    hideAllPhases();
    currentInquiry = inquiry;
    sparringTitleEl.textContent = inquiry.dilemma_question;
    renderChatMessages(inquiry.messages || []);
    renderOutlineCard(inquiry);
    phaseSparringEl.hidden = false;
    sparringInputEl.focus();
  }

  function showPhaseWriting(inquiry) {
    hideAllPhases();
    currentInquiry = inquiry;
    renderOutlineCard(inquiry);
    if (!essayTextEl.value && inquiry.final_text) {
      essayTextEl.value = inquiry.final_text;
    }
    updateWordCounter();
    phaseWritingEl.hidden = false;
    essayTextEl.focus();
  }

  function showPhaseCompleted(inquiry) {
    hideAllPhases();
    currentInquiry = inquiry;
    completedQuestionEl.textContent = inquiry.dilemma_question;
    completedMetaEl.textContent = `${inquiry.word_count || 0} palabras · Registrado el ${inquiry.completed_at || inquiry.updated_at || ""}`;
    completedEssayBodyEl.textContent = inquiry.final_text || "";

    completedTagsEl.innerHTML = "";
    if (inquiry.tags && inquiry.tags.length > 0) {
      inquiry.tags.forEach((t) => {
        const tag = document.createElement("span");
        tag.className = "lab-tag";
        tag.textContent = `#${t}`;
        completedTagsEl.appendChild(tag);
      });
    }

    renderOutlineCard(inquiry);
    phaseCompletedEl.hidden = false;
  }

  function renderChatMessages(messages) {
    chatMessagesEl.innerHTML = "";
    if (!messages || messages.length === 0) {
      const placeholder = document.createElement("div");
      placeholder.className = "sparring-empty-turn";
      placeholder.innerHTML = `
        <p>👋 Planteá tu primera postura respecto al dilema:</p>
        <p class="sparring-quote-prompt"><em>«${escapeHtml(currentInquiry.dilemma_question)}»</em></p>
      `;
      chatMessagesEl.appendChild(placeholder);
      return;
    }

    messages.forEach((msg) => {
      const bubble = document.createElement("div");
      bubble.className = "lab-chat-bubble " + (msg.role === "user" ? "user-bubble" : "tutor-bubble");
      bubble.innerHTML = `
        <div class="bubble-header">
          <strong>${msg.role === "user" ? "Vos (Lector)" : "Colega Exigente"}</strong>
        </div>
        <div class="bubble-content">${escapeHtml(msg.content).replace(/\n\n/g, "<br><br>")}</div>
      `;
      chatMessagesEl.appendChild(bubble);
    });

    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  }

  // Cargar una indagación existente
  async function loadInquiry(inquiryId) {
    try {
      const res = await fetch(`/api/laboratorio/inquiries/${inquiryId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "No se pudo cargar la indagación");

      currentInquiry = data.inquiry;
      // Seleccionar citas asociadas
      selectedAnnotationIds = new Set((currentInquiry.annotations || []).map((a) => a.id));
      renderQuotes();

      if (currentInquiry.status === "completed") {
        showPhaseCompleted(currentInquiry);
      } else if (currentInquiry.status === "ready_to_write") {
        showPhaseWriting(currentInquiry);
      } else {
        showPhaseSparring(currentInquiry);
      }
    } catch (err) {
      notify(err.message, true);
    }
  }

  // Event Listeners
  // 1. Submit Fase 1 (Tensión)
  tensionFormEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = tensionQuestionInput.value.trim();
    if (!question) return;

    const chapter = tensionChapterInput.value.trim();
    const annotationIds = Array.from(selectedAnnotationIds);

    try {
      const res = await fetch(`/api/works/${workId}/laboratorio/inquiries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dilemma_question: question,
          chapter_or_section: chapter,
          annotation_ids: annotationIds,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Error al crear la indagación");

      notify("Indagación iniciada. Comienza el sparring.", false);
      showPhaseSparring(data.inquiry);
    } catch (err) {
      notify(err.message, true);
    }
  });

  // 2. Submit Fase 2 (Sparring message)
  sparringFormEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!currentInquiry) return;

    const content = sparringInputEl.value.trim();
    if (!content) return;

    sparringInputEl.value = "";
    sparringInputEl.disabled = true;

    // Optimistic user bubble
    const tempUserMsg = { role: "user", content: content };
    const currentMsgs = (currentInquiry.messages || []).concat(tempUserMsg);
    renderChatMessages(currentMsgs);

    try {
      const res = await fetch(`/api/laboratorio/inquiries/${currentInquiry.id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Error al enviar mensaje");

      currentInquiry = data.inquiry;
      renderChatMessages(currentInquiry.messages);
    } catch (err) {
      notify(err.message, true);
    } finally {
      sparringInputEl.disabled = false;
      sparringInputEl.focus();
    }
  });

  // 3. Solicitar Andamiaje / Pasar a Redacción
  btnRequestOutline.addEventListener("click", async () => {
    if (!currentInquiry) return;
    btnRequestOutline.disabled = true;
    btnRequestOutline.textContent = "Generando andamiaje…";

    try {
      const res = await fetch(`/api/laboratorio/inquiries/${currentInquiry.id}/outline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Error al generar el esquema");

      currentInquiry = data.inquiry;
      notify("Esquema generado. Pasando al editor de cierre.", false);
      showPhaseWriting(currentInquiry);
    } catch (err) {
      notify(err.message, true);
    } finally {
      btnRequestOutline.disabled = false;
      btnRequestOutline.textContent = "✍️ Listo para escribir →";
    }
  });

  // 4. Volver a sparring desde redacción
  btnBackToSparring.addEventListener("click", () => {
    if (currentInquiry) {
      showPhaseSparring(currentInquiry);
    }
  });

  // Word counter listener
  essayTextEl.addEventListener("input", updateWordCounter);

  // 5. Guardar texto final (Fase 3 -> Fase 4)
  writingFormEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!currentInquiry) return;

    const text = essayTextEl.value.trim();
    if (!text) {
      notify("El texto no puede estar vacío.", true);
      return;
    }

    const rawTags = essayTagsInput.value.split(",").map((t) => t.trim()).filter(Boolean);

    try {
      const res = await fetch(`/api/laboratorio/inquiries/${currentInquiry.id}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          final_text: text,
          tags: rawTags,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Error al guardar reflexión");

      currentInquiry = data.inquiry;
      notify("¡Reflexión registrada con éxito!", false);
      showPhaseCompleted(currentInquiry);
      refreshPastReflections();
    } catch (err) {
      notify(err.message, true);
    }
  });

  // Nueva indagación
  function resetToNewInquiry() {
    currentInquiry = null;
    selectedAnnotationIds.clear();
    renderQuotes();
    tensionQuestionInput.value = "";
    tensionChapterInput.value = "";
    essayTextEl.value = "";
    outlineCardEl.hidden = true;
    showPhaseTension();
  }

  btnNewInquiryTop.addEventListener("click", resetToNewInquiry);
  btnNewFromCompleted.addEventListener("click", resetToNewInquiry);

  async function refreshPastReflections() {
    try {
      const res = await fetch(`/api/works/${workId}/laboratorio/inquiries`);
      const data = await res.json();
      if (res.ok && data.inquiries) {
        renderPastReflections(data.inquiries);
      }
    } catch (_) {}
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Inicialización
  async function init() {
    try {
      const res = await fetch(`/api/works/${workId}/laboratorio/init`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "No se pudo iniciar el laboratorio");

      currentWork = data.work;
      allAnnotations = data.annotations || [];
      workTitleEl.textContent = currentWork.title || "Obra sin título";

      if (data.ai_status) {
        providerPillEl.textContent = `IA: ${data.ai_status.provider || "Borrador"}`;
        providerPillEl.classList.toggle("is-ready", data.ai_status.ready);
      }

      renderQuotes();
      renderPastReflections(data.inquiries || []);

      // Si hay una indagación activa reciente no completada, cargarla
      const activeInquiry = (data.inquiries || []).find((i) => i.status !== "completed");
      if (activeInquiry) {
        loadInquiry(activeInquiry.id);
      } else {
        showPhaseTension();
      }
    } catch (err) {
      notify(err.message, true);
    }
  }

  init();
})();
