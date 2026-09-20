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

  // Toggle API key visibility
  if (toggleKeyBtn && apiKeyInput) {
    toggleKeyBtn.addEventListener('click', () => {
      const isPassword = apiKeyInput.type === 'password';
      apiKeyInput.type = isPassword ? 'text' : 'password';
      toggleKeyBtn.textContent = isPassword ? '🙈' : '👁️';
    });
  }

  async function loadProviders() {
    try {
      const res = await fetch('/api/ai-providers');
      const data = await res.json();
      providersCache = data.providers || [];

      providerSelect.innerHTML = '';
      providersCache.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name}${p.is_active ? ' (Activo)' : ''}`;
        providerSelect.appendChild(opt);
      });

      const newOpt = document.createElement('option');
      newOpt.value = 'new';
      newOpt.textContent = '+ Agregar nuevo proveedor...';
      providerSelect.appendChild(newOpt);

      const activeId = data.active_provider_id || 'draft';
      providerSelect.value = activeId;
      selectProvider(activeId);
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

    if (id === 'new') {
      fieldProviderName.hidden = false;
      providerNameInput.value = '';
      baseUrlInput.value = 'https://';
      modelInput.value = '';
      populateModelDropdown(null);
      protocolSelect.value = 'chat_completions';
      btnDelete.hidden = true;
      apiKeyHint.textContent = 'Ingresá la clave API para este nuevo proveedor.';
      updateBadge('Nuevo Proveedor', false);
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
    feedback.textContent = 'Guardando y activando proveedor...';
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

      feedback.textContent = '✅ ' + (result.message || 'Proveedor guardado y activado.');
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
