(() => {
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
  const values = select => select ? [...select.selectedOptions].map(option => option.value).filter(Boolean) : [];
  const normalizedValues = select => values(select).map(normalize);

  function refresh(select) {
    if (select?._musicMultiSelect) select._musicMultiSelect.sync();
  }

  function setValues(select, selectedValues = [], dispatch = false) {
    if (!select) return;
    const wanted = new Set([].concat(selectedValues || []).map(normalize).filter(Boolean));
    [...select.options].forEach(option => { option.selected = !!option.value && wanted.has(normalize(option.value)); });
    refresh(select);
    if (dispatch) select.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function setOptions(select, optionValues, placeholder, preserve = true) {
    if (!select) return;
    const previous = preserve ? normalizedValues(select) : [];
    select.innerHTML = '';
    optionValues.forEach(value => select.add(new Option(String(value), String(value))));
    select.dataset.placeholder = placeholder;
    setValues(select, previous);
  }

  function setup(select) {
    if (!select || select._musicMultiSelect) return select?._musicMultiSelect;
    select.multiple = true;
    select.classList.add('music-multi-native');
    const wrapper = document.createElement('div');
    wrapper.className = 'music-multi';
    wrapper.innerHTML = '<button type="button" class="music-multi-toggle" aria-expanded="false"></button><div class="music-multi-menu"><div class="music-multi-search"><input type="search"></div><div class="music-multi-options"></div></div>';
    select.insertAdjacentElement('afterend', wrapper);
    const toggle = wrapper.querySelector('.music-multi-toggle');
    const search = wrapper.querySelector('input');
    const options = wrapper.querySelector('.music-multi-options');
    const placeholder = () => select.dataset.placeholder || 'Todas as opções';
    const render = query => {
      const term = normalize(query);
      const available = [...select.options].filter(option => option.value && (!term || normalize(option.textContent).includes(term)));
      options.innerHTML = '';
      if (!term) {
        const all = document.createElement('button');
        const hasSelection = values(select).length > 0;
        all.type = 'button';
        all.className = `music-multi-option ${hasSelection ? '' : 'selected'}`;
        all.innerHTML = `<span class="music-multi-mark">${hasSelection ? '' : '✓'}</span><span></span>`;
        all.lastElementChild.textContent = placeholder();
        all.onclick = () => setValues(select, [], true);
        options.appendChild(all);
      }
      available.forEach(option => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = `music-multi-option ${option.selected ? 'selected' : ''}`;
        item.innerHTML = `<span class="music-multi-mark">${option.selected ? '✓' : ''}</span><span></span>`;
        item.lastElementChild.textContent = option.textContent;
        item.onclick = () => { option.selected = !option.selected; select.dispatchEvent(new Event('change', {bubbles: true})); sync(); };
        options.appendChild(item);
      });
      if (!available.length) options.innerHTML = '<div class="music-multi-empty">Nenhuma opção encontrada</div>';
    };
    const sync = () => {
      const labels = [...select.selectedOptions].filter(option => option.value).map(option => option.textContent.trim());
      const display = labels.length ? labels.join(', ') : placeholder();
      toggle.textContent = display;
      toggle.title = display;
      toggle.disabled = select.disabled;
      render(search.value);
    };
    toggle.onclick = event => {
      event.stopPropagation();
      document.querySelectorAll('.music-multi.open').forEach(item => { if (item !== wrapper) item.classList.remove('open'); });
      wrapper.classList.toggle('open');
      toggle.setAttribute('aria-expanded', wrapper.classList.contains('open') ? 'true' : 'false');
      if (wrapper.classList.contains('open')) { search.value = ''; render(''); setTimeout(() => search.focus(), 0); }
    };
    search.placeholder = select.dataset.search || 'Pesquisar…';
    search.onclick = event => event.stopPropagation();
    search.oninput = () => render(search.value);
    wrapper.querySelector('.music-multi-menu').onclick = event => event.stopPropagation();
    select._musicMultiSelect = {wrapper, sync, render};
    sync();
    return select._musicMultiSelect;
  }

  document.addEventListener('click', () => document.querySelectorAll('.music-multi.open').forEach(item => {
    item.classList.remove('open');
    item.querySelector('.music-multi-toggle')?.setAttribute('aria-expanded', 'false');
  }));

  window.MusicMultiSelect = {
    setup,
    setupAll: root => (root || document).querySelectorAll('select[data-music-multiple]').forEach(setup),
    values,
    normalizedValues,
    matches: (select, value) => { const selected = normalizedValues(select); return !selected.length || selected.includes(normalize(value)); },
    labels: (select, fallback) => { const selected = values(select); return selected.length ? selected.join(', ') : fallback; },
    setValues,
    setOptions,
    clear: (select, dispatch = false) => setValues(select, [], dispatch),
    refresh,
    normalize
  };
})();
