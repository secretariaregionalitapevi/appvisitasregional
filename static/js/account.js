(() => {
  'use strict';
  const feedback = (type, title, message) => window.AppFeedback.show({type, title, message});
  const form = document.getElementById('account-profile-form');
  if (form) {
    const input = document.getElementById('account-name');
    const preview = document.getElementById('account-name-preview');
    const state = document.getElementById('account-save-state');
    const file = document.getElementById('account-avatar');
    const removal = document.getElementById('account-remove-avatar-value');
    const avatarHost = form.querySelector('[data-avatar-host]');
    const initials = form.querySelector('[data-avatar-initials]');
    let savedAvatar = avatarHost.querySelector('img')?.getAttribute('src') || '';
    let previewUrl = '';
    let saving = false;
    const showAvatar = source => {
      let image = avatarHost.querySelector('img');
      if (source) {
        if (!image) { image = document.createElement('img'); image.alt = 'Sua foto de perfil'; image.dataset.accountAvatar = ''; avatarHost.prepend(image); }
        image.src = source;
        image.hidden = false;
      } else image?.remove();
      initials.hidden = Boolean(source);
    };
    const updatePreview = () => {
      const name = input.value.trim() || 'Seu nome';
      if (preview) preview.textContent = name;
      form.querySelectorAll('[data-account-display-name]').forEach(node => { node.textContent = name; });
      initials.textContent = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
    };
    const markDirty = () => { state.textContent = 'Alterações ainda não salvas'; updatePreview(); };
    const cep = document.getElementById('account-cep');
    const street = document.getElementById('account-street');
    const number = document.getElementById('account-number');
    const neighborhood = document.getElementById('account-neighborhood');
    const cepStatus = document.getElementById('account-cep-status');
    const maskCep = value => {
      const digits = value.replace(/\D/g, '').slice(0, 8);
      return digits.length > 5 ? digits.slice(0, 5) + '-' + digits.slice(5) : digits;
    };
    let cepController = null, cepVersion = 0, lastCep = '', cepPending = false;
    const cepCache = new Map();
    cep.value = maskCep(cep.value);
    const cancelCep = () => { cepVersion++; cepController?.abort(); cepPending = false; };
    async function lookupCep() {
      cep.value = maskCep(cep.value);
      const digits = cep.value.replace(/\D/g, '');
      cancelCep();
      if (digits.length !== 8) {
        lastCep = '';
        cepStatus.textContent = 'Digite o CEP para buscar o endereço.';
        return;
      }
      if (digits === lastCep) return;
      const version = cepVersion;
      const originalStreet = street.value, originalNeighborhood = neighborhood.value;
      const controller = new AbortController();
      cepController = controller;
      cepPending = true;
      cepStatus.textContent = 'Buscando endereço…';
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        let address = cepCache.get(digits);
        if (!address) {
          const response = await fetch(form.dataset.cepUrl + '?cep=' + digits, {signal: controller.signal, credentials: 'same-origin'});
          if (response.redirected) throw Error('Sua sessão expirou. Entre novamente.');
          address = await response.json();
          if (!response.ok) throw Error(address.error || 'Não foi possível consultar o CEP. Preencha o endereço manualmente ou tente novamente.');
        }
        if (version !== cepVersion || saving) return;
        if (address.erro) throw Error('CEP não encontrado. Confira os números ou preencha o endereço manualmente.');
        if (typeof address.logradouro !== 'string' || typeof address.bairro !== 'string') throw Error('Não foi possível confirmar o endereço deste CEP. Preencha os campos manualmente.');
        cepCache.set(digits, address);
        lastCep = digits;
        if (street.value === originalStreet) street.value = address.logradouro;
        if (neighborhood.value === originalNeighborhood) neighborhood.value = address.bairro;
        cepStatus.textContent = [address.localidade, address.uf].filter(Boolean).join(' / ') + (address.logradouro ? ' · Informe o número.' : ' · Informe o logradouro e o número.');
        markDirty();
        if (document.activeElement === cep) (address.logradouro ? number : street).focus();
      } catch (error) {
        if (version !== cepVersion) return;
        cepStatus.textContent = 'Preencha o endereço manualmente ou confira o CEP.';
        feedback('error', 'Confira o CEP', error.name === 'AbortError' ? 'A consulta demorou mais que o esperado. Tente novamente ou preencha o endereço manualmente.' : error.message);
      } finally {
        clearTimeout(timeout);
        if (version === cepVersion) cepPending = false;
      }
    }
    cep.addEventListener('input', lookupCep);
    cep.addEventListener('blur', () => { if (!cepPending && !lastCep) lookupCep(); });
    // A previously saved postcode may already be present when the page opens.
    if (cep.value.replace(/\D/g, '').length === 8 && (!street.value.trim() || !neighborhood.value.trim())) lookupCep();
    form.addEventListener('input', markDirty);
    file.addEventListener('change', () => {
      const selected = file.files[0];
      if (!selected) return;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type) || selected.size > 5 * 1024 * 1024) {
        file.value = '';
        return feedback('error', 'Confira a foto', 'Escolha uma imagem JPG, PNG ou WebP de até 5 MB.');
      }
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(selected);
      removal.value = '0';
      showAvatar(previewUrl);
      markDirty();
    });
    document.getElementById('account-remove-avatar').addEventListener('click', () => {
      file.value = '';
      removal.value = '1';
      showAvatar('');
      markDirty();
    });
    form.addEventListener('reset', () => {
      cancelCep(); lastCep = '';
      setTimeout(() => {
      if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = ''; }
      removal.value = '0';
      showAvatar(savedAvatar);
      updatePreview();
      state.textContent = 'Dados do seu cadastro';
      cep.value = maskCep(cep.value);
      cepStatus.textContent = 'Digite o CEP para buscar o endereço.';
    }, 0);
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving || !form.reportValidity()) return;
      if (cepPending) return feedback('warning', 'Consulta de CEP em andamento', 'Aguarde a busca do endereço antes de salvar.');
      saving = true;
      const button = form.querySelector('[type=submit]');
      const original = button.innerHTML;
      const body = new FormData(form);
      const controls = [...form.querySelectorAll('input,button')].map(node => [node, node.disabled]);
      controls.forEach(([node]) => { node.disabled = true; });
      button.innerHTML = '<i class="fa fa-spinner fa-spin me-2" aria-hidden="true"></i>Salvando…';
      try {
        const response = await fetch(form.action, {method: 'POST', credentials: 'same-origin', body});
        if (response.redirected) throw Error('Sua sessão expirou. Entre novamente.');
        if (!(response.headers.get('content-type') || '').includes('application/json')) throw Error('Não foi possível salvar seu perfil. Atualize a página e tente novamente.');
        const result = await response.json();
        if (!response.ok) throw Error(result.error || 'Não foi possível salvar seu perfil.');
        input.value = result.full_name;
        form.querySelectorAll('input:not([type=file]):not([type=hidden])').forEach(node => { node.defaultValue = node.value; });
        updatePreview();
        document.querySelectorAll('.navbar-user .fw-bold, .menu-profile-info .flex-grow-1').forEach(node => { node.textContent = result.full_name; });
        if (Object.hasOwn(result, 'avatar_url')) {
          savedAvatar = result.avatar_url || '';
          showAvatar(savedAvatar);
          document.querySelectorAll('.navbar-user>a>img, .menu-profile-image img').forEach(node => {
            if (savedAvatar) node.src = savedAvatar;
            else node.src = '/static/img/account-avatar.svg';
          });
        }
        file.value = '';
        removal.value = '0';
        if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = ''; }
        state.textContent = 'Perfil atualizado com sucesso';
        feedback('success', 'Perfil atualizado', 'Seus dados foram salvos. Os próximos relatórios usarão o nome atualizado.');
      } catch (error) {
        feedback('error', 'Não foi possível salvar', error.message);
      } finally {
        controls.forEach(([node, disabled]) => { node.disabled = disabled; });
        button.innerHTML = original;
        saving = false;
      }
    });
    avatarHost.addEventListener('error', event => {
      if (event.target.tagName === 'IMG') { event.target.hidden = true; initials.hidden = false; }
    }, true);
  }
  const themeButtons = [...document.querySelectorAll('[data-account-theme]')];
  const refreshTheme = () => {
    const selected = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
    themeButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.accountTheme === selected)));
  };
  themeButtons.forEach(button => button.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
    if (current !== button.dataset.accountTheme) document.getElementById('header-theme-toggle')?.click();
    refreshTheme();
  }));
  if (themeButtons.length) {
    refreshTheme();
    new MutationObserver(refreshTheme).observe(document.documentElement, {attributes: true, attributeFilter: ['data-bs-theme']});
  }
  document.querySelectorAll('.account-settings-nav, .account-form-nav').forEach(nav => {
    const links = [...nav.querySelectorAll('a[href^="#"]')];
    links.forEach(link => link.addEventListener('click', () => {
      links.forEach(item => item.classList.toggle('active', item === link));
    }));
    const sections = links.map(link => document.querySelector(link.hash));
    let scheduled = false;
    const refreshSection = () => {
      let current = 0;
      sections.forEach((section, index) => { if (section && section.getBoundingClientRect().top <= 170) current = index; });
      links.forEach((link, index) => link.classList.toggle('active', index === current));
      scheduled = false;
    };
    window.addEventListener('scroll', () => {
      if (!scheduled) { scheduled = true; requestAnimationFrame(refreshSection); }
    }, {passive: true});
    refreshSection();
  });
})();
