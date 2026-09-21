document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initAiConfigForm();
});

function initTabs() {
  const tabButtons = document.querySelectorAll('.settings-tabs .tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  function switchTab(targetTab) {
    tabButtons.forEach(btn => {
      const isActive = btn.dataset.tab === targetTab;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    tabPanels.forEach(panel => {
      const isActive = panel.id === `panel-${targetTab}`;
      panel.hidden = !isActive;
    });

    const url = new URL(window.location.href);
    url.searchParams.set('tab', targetTab);
    window.history.replaceState({}, '', url.toString());
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  const params = new URLSearchParams(window.location.search);
  let initialTab = params.get('tab');
  if (!initialTab) {
    const path = window.location.pathname;
    if (path.endsWith('/covers')) initialTab = 'covers';
    else if (path.endsWith('/ai-profiles')) initialTab = 'profiles';
    else if (path.endsWith('/status')) initialTab = 'status';
  }
  if (initialTab && document.getElementById(`panel-${initialTab}`)) {
    switchTab(initialTab);
  }
}

let providersCache = [];
let currentActiveProviderId = 'draft';

async function initAiConfigForm() {
  const form = document.getElementById('ai-config-form');
  if (!form) return;

  const providerSelect = document.getElementById('provider-select');
  const providerNameInput = document.getElementById('ai-provider-name');
  const fieldProviderName = document.getElementById('field-provider-name');
  const apiKeyInput = document.getElementById('ai-api-key');
  const toggleKeyBtn = document.getElementById('toggle-api-key');
  const modelInput = document.getElementById('ai-model');
  const baseUrlInput = document.getElementById('ai-base-url');
  const protocolSelect = document.getElementById('ai-protocol');
  const btnDelete = document.getElementById('btn-delete-provider');
  const feedback = document.getElementById('ai-config-feedback');
  const apiKeyHint = document.getElementById('api-key-hint');
  const saveBtn = document.getElementById('save-ai-config');
  const cardsGrid = document.getElementById('provider-cards-grid');
  const editNotice = document.getElementById('provider-edit-notice');
  const noticeTitle = document.getElementById('notice-title');
  const noticeDesc = document.getElementById('notice-desc');
  const noticeIcon = document.getElementById('notice-icon');

  // Toggle API key visibility
  if (toggleKeyBtn && apiKeyInput) {
    toggleKeyBtn.addEventListener('click', () => {
      const isPassword = apiKeyInput.type === 'password';
      apiKeyInput.type = isPassword ? 'text' : 'password';
      toggleKeyBtn.textContent = isPassword ? '🙈' : '👁️';
    });
  }

  function updateActiveBanner(activeP) {
    const banner = document.getElementById('active-provider-banner');
    const icon = document.getElementById('banner-status-icon');
    const label = document.getElementById('banner-label');
    const nameDisplay = document.getElementById('active-provider-name-display');
    const subtextDisplay = document.getElementById('active-provider-subtext-display');

    if (!banner || !activeP) return;

    const isDraft = activeP.id === 'draft';
    banner.className = `active-provider-banner${isDraft ? ' is-draft' : ''}`;
    icon.textContent = isDraft ? '📝' : '✓';
    label.textContent = isDraft
      ? 'MODO ACTUAL EN EL SISTEMA: BORRADOR LOCAL'
      : 'PROVEEDOR ACTIVO ACTUALMENTE EN EL SISTEMA';
    nameDisplay.textContent = activeP.name || activeP.id;
    subtextDisplay.textContent = isDraft
      ? 'Desconectado de APIs externas · La información no sale de tu equipo'
      : `Modelo: ${activeP.model || 'Predeterminado'} · Endpoint: ${activeP.base_url || 'API directa'}`;
  }

  function renderProviderCards() {
    if (!cardsGrid) return;
    cardsGrid.innerHTML = '';

    providersCache.forEach(p => {
      const isActiveSystem = (p.id === currentActiveProviderId);
      const isSelectedForm = (providerSelect.value === p.id);

      const card = document.createElement('div');
      card.className = `provider-card${isActiveSystem ? ' is-active-system' : ''}${isSelectedForm ? ' is-selected-form' : ''}`;
      card.dataset.id = p.id;
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');

      let badgeHtml = '';
      if (isActiveSystem) {
        badgeHtml = `<span class="provider-card-badge badge-active-system">✓ ACTIVO</span>`;
      } else if (p.id === 'draft') {
        badgeHtml = `<span class="provider-card-badge badge-draft-system">Borrador</span>`;
      } else if (p.has_api_key) {
        badgeHtml = `<span class="provider-card-badge" style="background:#edf6ef;color:#264a32;">🔑 Con Clave</span>`;
      } else {
        badgeHtml = `<span class="provider-card-badge" style="background:#fdf9ee;color:#7a5410;">⚠️ Sin Clave</span>`;
      }

      card.innerHTML = `
        <div class="provider-card-header">
          <h3 class="provider-card-name">${p.name}</h3>
          ${badgeHtml}
        </div>
        <div class="provider-card-subtext">${p.id === 'draft' ? 'Sin envíos externos' : (p.model || 'Modelo estándar')}</div>
      `;

      const selectThis = () => {
        providerSelect.value = p.id;
        selectProvider(p.id);
      };

      card.addEventListener('click', selectThis);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectThis();
        }
      });

      cardsGrid.appendChild(card);
    });

    // Tarjeta para agregar nuevo
    const newCard = document.createElement('div');
    const isNewSelected = (providerSelect.value === 'new');
    newCard.className = `provider-card${isNewSelected ? ' is-selected-form' : ''}`;
    newCard.style.borderStyle = 'dashed';
    newCard.style.opacity = '0.85';
    newCard.innerHTML = `
      <div class="provider-card-header">
        <h3 class="provider-card-name" style="font-size: 1rem;">+ Otro proveedor</h3>
      </div>
      <div class="provider-card-subtext">Groq, Ollama, vLLM, etc.</div>
    `;
    const selectNew = () => {
      providerSelect.value = 'new';
      selectProvider('new');
    };
    newCard.addEventListener('click', selectNew);
    cardsGrid.appendChild(newCard);
  }

  async function loadProviders() {
    try {
      const res = await fetch('/api/ai-providers');
      const data = await res.json();
      providersCache = data.providers || [];
      currentActiveProviderId = data.active_provider_id || 'draft';

      const activeP = providersCache.find(p => p.id === currentActiveProviderId) || { id: 'draft', name: 'Draft (Borrador)' };
      updateActiveBanner(activeP);

      providerSelect.innerHTML = '';
      providersCache.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name}${p.id === currentActiveProviderId ? ' ✓ (ACTIVO EN SISTEMA)' : ''}`;
        providerSelect.appendChild(opt);
      });

      const newOpt = document.createElement('option');
      newOpt.value = 'new';
      newOpt.textContent = '+ Agregar nuevo proveedor...';
      providerSelect.appendChild(newOpt);

      providerSelect.value = currentActiveProviderId;
      selectProvider(currentActiveProviderId);
    } catch (err) {
      console.error('Error al cargar proveedores:', err);
    }
  }

  const modelSelect = document.getElementById('ai-model-select');

  if (modelSelect && modelInput) {
    modelSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val && val !== 'custom') {
        modelInput.value = val;
      }
    });

    modelInput.addEventListener('input', () => {
      const currentVal = modelInput.value.trim();
      const matchingOpt = Array.from(modelSelect.options).find(opt => opt.value === currentVal);
      if (matchingOpt) {
        modelSelect.value = currentVal;
      } else if (currentVal) {
        modelSelect.value = 'custom';
      }
    });
  }

  function populateModelDropdown(p) {
    if (!modelSelect) return;
    modelSelect.innerHTML = '';

    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = '-- Seleccionar un modelo de la lista --';
    modelSelect.appendChild(defaultOpt);

    const modelsList = (p && p.models) ? p.models : [];
    const currentModel = p ? (p.model || '') : '';

    modelsList.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      modelSelect.appendChild(opt);
    });

    const customOpt = document.createElement('option');
    customOpt.value = 'custom';
    customOpt.textContent = '✍️ Escribir modelo personalizado...';
    modelSelect.appendChild(customOpt);

    if (currentModel && modelsList.includes(currentModel)) {
      modelSelect.value = currentModel;
    } else if (currentModel) {
      modelSelect.value = 'custom';
    } else {
      modelSelect.value = '';
    }
  }

  function selectProvider(id) {
    feedback.textContent = '';
    feedback.className = 'form-feedback';
    apiKeyInput.value = '';

    const activeP = providersCache.find(p => p.id === currentActiveProviderId) || { name: 'Draft' };

    renderProviderCards();

    if (id === 'new') {
      fieldProviderName.hidden = false;
      providerNameInput.value = '';
      baseUrlInput.value = 'https://';
      modelInput.value = '';
      populateModelDropdown(null);
      protocolSelect.value = 'chat_completions';
      btnDelete.hidden = true;
      apiKeyHint.textContent = 'Ingresá la clave API para este nuevo proveedor.';

      if (editNotice) {
        editNotice.hidden = false;
        editNotice.className = 'provider-edit-notice notice-warning';
        if (noticeIcon) noticeIcon.textContent = '➕';
        if (noticeTitle) noticeTitle.textContent = 'Configurando nuevo servicio';
        if (noticeDesc) noticeDesc.textContent = `Actualmente "${activeP.name}" sigue siendo el activo. Completá los campos y hacé clic en guardar para activarlo.`;
      }
      if (saveBtn) saveBtn.textContent = '⚡ Guardar y Activar Nuevo Proveedor';
      updateBadge('Nuevo Proveedor', false, 'new');
      return;
    }

    fieldProviderName.hidden = true;
    const p = providersCache.find(item => item.id === id);
    if (!p) return;

    providerNameInput.value = p.name || '';
    baseUrlInput.value = p.base_url || '';
    modelInput.value = p.model || '';
    populateModelDropdown(p);
    protocolSelect.value = p.protocol || 'chat_completions';

    btnDelete.hidden = p.is_preset;

    if (p.has_api_key && p.masked_api_key) {
      apiKeyHint.textContent = `Clave guardada: ${p.masked_api_key}. Dejá en blanco para no cambiarla.`;
    } else {
      apiKeyHint.textContent = p.id === 'draft' ? 'El modo Borrador no requiere clave.' : 'Sin clave guardada. Ingresá una clave API.';
    }

    if (editNotice) {
      editNotice.hidden = false;
      if (id === currentActiveProviderId) {
        editNotice.className = 'provider-edit-notice notice-active';
        if (noticeIcon) noticeIcon.textContent = '✓';
        if (noticeTitle) noticeTitle.textContent = `"${p.name}" es el proveedor actualmente activo en todo el sistema`;
        if (noticeDesc) noticeDesc.textContent = 'Los mensajes y búsquedas utilizarán este motor de IA. Podés ajustar sus valores y guardar cambios.';
        if (saveBtn) saveBtn.textContent = `💾 Guardar Cambios en ${p.name}`;
      } else {
        editNotice.className = 'provider-edit-notice notice-warning';
        if (noticeIcon) noticeIcon.textContent = '⚠️';
        if (noticeTitle) noticeTitle.textContent = `Estás editando la configuración de "${p.name}"`;
        if (noticeDesc) noticeDesc.textContent = `Importante: "${activeP.name}" sigue siendo el proveedor activo. Para cambiar a ${p.name}, hacé clic en el botón de abajo.`;
        if (saveBtn) saveBtn.textContent = `⚡ Activar "${p.name}" en todo el sistema`;
      }
    }

    updateBadge(p.name, p.has_api_key, p.id);
  }

  providerSelect.addEventListener('change', (e) => {
    selectProvider(e.target.value);
  });

  btnDelete.addEventListener('click', async () => {
    const selectedId = providerSelect.value;
    if (selectedId === 'new') return;
    if (!confirm(`¿Eliminar el proveedor personalizado "${providerNameInput.value}"?`)) return;

    try {
      const res = await fetch(`/api/ai-providers/${selectedId}`, { method: 'DELETE' });
      const result = await res.json();
      if (!res.ok) {
        feedback.textContent = result.error || 'Error al eliminar proveedor';
        feedback.className = 'form-feedback is-error';
        return;
      }
      feedback.textContent = 'Proveedor eliminado.';
      feedback.className = 'form-feedback is-success';
      await loadProviders();
    } catch (err) {
      feedback.textContent = 'Error de conexión.';
      feedback.className = 'form-feedback is-error';
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    feedback.textContent = 'Guardando y activando proveedor en todo el sistema...';
    feedback.className = 'form-feedback';

    const selectedValue = providerSelect.value;
    let providerId = selectedValue;
    let providerName = providerNameInput.value.trim();

    if (selectedValue === 'new') {
      if (!providerName) {
        feedback.textContent = 'Ingresá un nombre para el nuevo servicio.';
        feedback.className = 'form-feedback is-error';
        return;
      }
      providerId = providerName.toLowerCase().replace(/[^a-z0-9]/g, '_');
    }

    const payload = {
      id: providerId,
      name: providerName,
      base_url: baseUrlInput.value.trim(),
      model: modelInput.value.trim(),
      protocol: protocolSelect.value,
      activate: true,
    };

    if (apiKeyInput.value.trim()) {
      payload.api_key = apiKeyInput.value.trim();
    }

    try {
      const res = await fetch('/api/ai-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const result = await res.json();
      if (!res.ok) {
        feedback.textContent = result.error || 'Error al guardar configuración';
        feedback.className = 'form-feedback is-error';
        return;
      }

      feedback.textContent = `🟢 ¡Proveedor ${providerName} guardado y activado correctamente!`;
      feedback.className = 'form-feedback is-success';
      apiKeyInput.value = '';

      await loadProviders();
    } catch (err) {
      feedback.textContent = 'Error al comunicarse con el servidor.';
      feedback.className = 'form-feedback is-error';
    }
  });

  await loadProviders();
}

function updateBadge(name, isReady, id) {
  const badge = document.getElementById('ai-status-badge');
  if (!badge) return;

  if (id === 'draft') {
    badge.textContent = `${name} · Modos locales`;
    badge.className = 'status-badge badge-draft';
  } else if (isReady) {
    badge.textContent = `${name} · Listo`;
    badge.className = 'status-badge badge-active';
  } else {
    badge.textContent = `${name} · Falta API Key`;
    badge.className = 'status-badge badge-warning';
  }
}

