(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const city = $('ram-city'), common = $('ram-church'), eventSelect = $('ram-event-select');
  const name = $('ram-person'), reason = $('ram-reason'), submit = $('ram-submit');
  const reasonType = $('ram-reason-type');
  let data, selectedCommon, person, saving = false, peopleVersion = 0, timer, searchController;
  const searchCache = new Map();
  const formatDate = day => day?.split('-').reverse().join('/') || '';
  const label = value => value.toLocaleLowerCase('pt-BR').split(/\s+/).map((w, i) =>
    i && ['de', 'da', 'do', 'das', 'dos', 'e'].includes(w) ? w : w.charAt(0).toLocaleUpperCase('pt-BR') + w.slice(1)).join(' ');
  const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Sao_Paulo', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  const event = () => data?.events.find(e => e.id === eventSelect.value);
  const feedback = (message, type = 'error') => window.AppFeedback.show({type, title:type === 'success' ? 'Justificativa registrada' : 'Confira a justificativa', message});
  const option = (value, text) => new Option(text, value);
  const cityTrigger = $('ram-city-trigger');
  const cityMenu = document.createElement('div');
  cityMenu.id = 'ram-city-options'; cityMenu.className = 'ram-city-menu'; cityMenu.hidden = true;
  cityMenu.setAttribute('role', 'listbox'); cityMenu.setAttribute('aria-label', 'Município');
  document.body.append(cityMenu);
  let activeCity = 0, citySearch = '', citySearchTime = 0;
  function closeCities() {
    cityMenu.hidden = true;
    cityTrigger.setAttribute('aria-expanded', 'false');
    cityTrigger.removeAttribute('aria-activedescendant');
  }
  function syncCity() {
    $('ram-city-label').textContent = city.selectedOptions[0]?.textContent || 'Selecione o município';
    cityTrigger.classList.toggle('has-value', !!city.value);
    closeCities();
  }
  function highlightCity(index) {
    const entries = [...cityMenu.children];
    activeCity = (index + entries.length) % entries.length;
    entries.forEach((item, i) => item.classList.toggle('active', i === activeCity));
    cityTrigger.setAttribute('aria-activedescendant', entries[activeCity].id);
    entries[activeCity].scrollIntoView?.({block:'nearest'});
  }
  function chooseCity(index) {
    if (saving || cityTrigger.matches(':disabled')) return;
    city.value = city.options[index].value;
    city.dispatchEvent(new Event('change', {bubbles:true}));
    cityTrigger.focus();
  }
  function openCities(index = city.selectedIndex) {
    if (!data || saving || cityTrigger.matches(':disabled')) return;
    closeCommons();
    cityMenu.replaceChildren(...[...city.options].map((item, i) => {
      const entry = document.createElement('button');
      entry.type = 'button'; entry.tabIndex = -1; entry.id = `ram-city-option-${i}`;
      entry.className = 'ram-city-option'; entry.setAttribute('role', 'option');
      entry.setAttribute('aria-selected', String(item.value === city.value));
      const pin = document.createElement('i'); pin.className = item.value ? 'fa fa-location-dot ram-city-pin' : 'ram-city-pin'; pin.setAttribute('aria-hidden', 'true');
      const text = document.createElement('span'); text.textContent = item.textContent;
      const check = document.createElement('i'); check.className = 'fa fa-check ram-city-check'; check.hidden = !item.value || item.value !== city.value; check.setAttribute('aria-hidden', 'true');
      entry.append(pin, text, check);
      entry.addEventListener('pointerdown', e => e.preventDefault());
      entry.addEventListener('click', () => chooseCity(i));
      entry.addEventListener('mouseenter', () => highlightCity(i));
      return entry;
    }));
    const rect = cityTrigger.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom, above = below < 180 && rect.top > below;
    Object.assign(cityMenu.style, {left:rect.left + 'px', width:rect.width + 'px',
      maxHeight:Math.min(280, Math.max(80, (above ? rect.top : below) - 12)) + 'px',
      top:above ? 'auto' : rect.bottom + 5 + 'px', bottom:above ? window.innerHeight - rect.top + 5 + 'px' : 'auto'});
    cityMenu.hidden = false;
    cityTrigger.setAttribute('aria-expanded', 'true');
    highlightCity(Math.max(0, index));
  }
  cityTrigger.addEventListener('click', () => cityMenu.hidden ? openCities() : closeCities());
  cityTrigger.addEventListener('keydown', e => {
    if (e.key === 'Escape' || e.key === 'Tab') {closeCities(); return;}
    if (['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(e.key)) {
      e.preventDefault();
      if (e.key === 'Enter' || e.key === ' ') {if (cityMenu.hidden) openCities(); else chooseCity(activeCity);}
      else if (e.key === 'Home' || e.key === 'End') {const index = e.key === 'Home' ? 0 : city.options.length - 1; if (cityMenu.hidden) openCities(index); else highlightCity(index);}
      else if (cityMenu.hidden) openCities();
      else highlightCity(activeCity + (e.key === 'ArrowDown' ? 1 : -1));
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const now = Date.now(); citySearch = (now - citySearchTime < 700 ? citySearch : '') + e.key.toLocaleLowerCase('pt-BR'); citySearchTime = now;
      const index = [...city.options].findIndex(o => o.textContent.toLocaleLowerCase('pt-BR').startsWith(citySearch));
      if (index >= 0) {if (cityMenu.hidden) chooseCity(index); else highlightCity(index);}
    }
  });
  cityTrigger.addEventListener('blur', closeCities);
  document.addEventListener('pointerdown', e => {if (!cityTrigger.contains(e.target) && !cityMenu.contains(e.target)) closeCities();});
  window.addEventListener('resize', closeCities);
  window.addEventListener('scroll', e => {if (!cityMenu.contains(e.target)) closeCities();}, true);
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  function closeCommons() {
    $('ram-commons').hidden = true;
    common.setAttribute('aria-expanded', 'false');
  }
  function openCommons() {
    if (common.disabled || saving || !data) return;
    const query = selectedCommon ? '' : normalize(common.value).trim();
    const matches = data.commons.filter(c => c.municipio === city.value &&
      query.split(/\s+/).every(term => normalize(c.nome).includes(term)))
      .sort((a,b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    const menu = $('ram-commons');
    menu.replaceChildren(...matches.map(c => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'ram-common-option';
      button.setAttribute('role', 'option');
      button.setAttribute('aria-selected', String(c.codigo === selectedCommon?.codigo));
      const title = document.createElement('strong'), municipality = document.createElement('small');
      title.textContent = c.nome; municipality.textContent = c.municipio;
      button.append(title, municipality);
      button.addEventListener('mousedown', e => e.preventDefault());
      button.addEventListener('click', () => {
        common.value = c.nome;
        common.dispatchEvent(new Event('input', {bubbles:true}));
        closeCommons();
        common.focus();
        closeCommons();
      });
      return button;
    }));
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = 'Nenhuma comum encontrada neste município.';
      menu.append(empty);
    }
    menu.hidden = false;
    common.setAttribute('aria-expanded', 'true');
  }
  function ready() {
    submit.disabled = saving || !selectedCommon || !person || !event() || event().data_evento < today() || !reasonType.value || (reasonType.value === 'Outros' && reason.value.trim().length < 5);
    const completed = [!!city.value, !!selectedCommon,
      !!selectedCommon && !!event() && event().data_evento >= today(), !!person];
    const current = completed.findIndex(done => !done);
    document.querySelectorAll('.ram-steps li').forEach((li, index) => {
      li.classList.toggle('done', completed[index]);
      li.classList.toggle('current', !completed[index] && index === current);
      if (!completed[index] && index === current) li.setAttribute('aria-current', 'step');
      else li.removeAttribute('aria-current');
      li.querySelector('span').innerHTML = completed[index]
        ? '<i class="fa fa-check" aria-hidden="true" style="color:#fff;font-size:10px"></i>'
        : String(index + 1);
    });
  }
  function hideResults() {
    $('ram-results').hidden = true;
    name.setAttribute('aria-expanded', 'false');
    name.removeAttribute('aria-activedescendant');
  }
  function clearPerson() {
    peopleVersion++;
    clearTimeout(timer);
    searchController?.abort();
    person = null;
    name.value = '';
    hideResults();
    name.disabled = !selectedCommon;
    name.placeholder = selectedCommon ? 'Digite seu nome completo' : 'Selecione primeiro sua comum';
    $('ram-name-help').textContent = 'Digite pelo menos 2 letras e selecione seu nome na lista.';
    ready();
  }
  function showEvent() {
    const item = event();
    $('ram-event-date').textContent = item ? `${formatDate(item.data_evento)}${item.hora ? ' · ' + item.hora : ''}` : 'Nenhum evento disponível';
    $('ram-event-location').textContent = item ? item.local || label(city.value) : 'Agenda musical';
    $('ram-event-help').textContent = item ? `Recebimento até ${formatDate(item.data_evento)}, às 23h59 (São Paulo). Confira o evento antes de enviar.` : 'Não há eventos futuros na agenda para este município.';
    ready();
  }
  city.addEventListener('change', () => {
    syncCity();
    selectedCommon = null;
    common.value = '';
    common.disabled = !city.value;
    common.placeholder = city.value ? 'Pesquise e selecione sua comum' : 'Selecione primeiro o município';
    closeCommons();
    $('ram-commons').replaceChildren();
    const choices = data.events.filter(e => e.municipios.includes(city.value) && e.data_evento >= today())
      .sort((a,b) => a.data_evento.localeCompare(b.data_evento) || (a.hora || '').localeCompare(b.hora || '') || a.titulo.localeCompare(b.titulo,'pt-BR')).slice(0,3);
    eventSelect.replaceChildren(...(choices.length ? choices.map((e,index) => {
      const item = option(e.id, `${formatDate(e.data_evento)} · ${e.titulo}${index === 2 ? ' · Em breve' : ''}`);
      item.disabled = index === 2;
      return item;
    }) : [option('', city.value ? 'Nenhum evento futuro disponível' : 'Selecione primeiro o município')]));
    eventSelect.disabled = true;
    clearPerson();
    showEvent();
  });
  common.addEventListener('focus', openCommons);
  common.addEventListener('click', openCommons);
  common.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeCommons();
    if (e.key === 'ArrowDown') {
      e.preventDefault(); openCommons(); $('ram-commons').querySelector('button')?.focus();
    }
  });
  $('ram-commons').addEventListener('keydown', e => {
    const buttons = [...$('ram-commons').querySelectorAll('button')];
    const index = buttons.indexOf(document.activeElement);
    if (['ArrowDown','ArrowUp'].includes(e.key)) {
      e.preventDefault(); buttons[(index + (e.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length]?.focus();
    }
    if (e.key === 'Escape') {common.focus(); closeCommons();}
  });
  common.closest('.ram-common-picker').addEventListener('focusout', e => {
    if (!common.closest('.ram-common-picker').contains(e.relatedTarget)) closeCommons();
  });
  document.addEventListener('click', e => {
    if (!common.closest('.ram-common-picker').contains(e.target)) closeCommons();
  });
  common.addEventListener('input', () => {
    const next = data.commons.find(c => c.municipio === city.value && c.nome === common.value);
    if (next?.codigo !== selectedCommon?.codigo) {
      selectedCommon = next;
      clearPerson();
    }
    common.setCustomValidity(next || !common.value ? '' : 'Selecione uma comum da lista.');
    eventSelect.disabled = !selectedCommon || !eventSelect.value;
    showEvent();
    openCommons();
  });
  eventSelect.addEventListener('change', showEvent);
  reason.addEventListener('input', ready);
  reasonType.addEventListener('change', () => {
    const other = reasonType.value === 'Outros';
    $('ram-reason-details').hidden = !other;
    reason.disabled = !other;
    reason.required = other;
    reasonType.setAttribute('aria-expanded', String(other));
    if (!other) reason.value = '';
    ready();
    if (other) reason.focus();
  });
  name.addEventListener('input', () => {
    person = null;
    const version = ++peopleVersion;
    searchController?.abort();
    clearTimeout(timer);
    hideResults();
    ready();
    if (!selectedCommon || name.value.trim().length < 2) return;
    const commonCode = selectedCommon.codigo, query = name.value.trim();
    $('ram-name-help').textContent = 'Pesquisando nomes e cargos…';
    const cacheKey = commonCode + '|' + normalize(query).trim();
    const cached = searchCache.get(cacheKey);
    timer = setTimeout(async () => {
      const controller = new AbortController(); searchController = controller;
      let timedOut = false;
      const deadline = setTimeout(() => {timedOut = true; controller.abort();}, 25000);
      try {
        let result;
        if (cached && Date.now() - cached.at < 45000) result = cached.result;
        else {
          const params = new URLSearchParams({comum:commonCode, q:query});
          const response = await fetch(`/justificativas/api/?${params}`, {signal:controller.signal});
          result = await response.json();
          if (!response.ok) throw Error(result.error || 'Não foi possível pesquisar os nomes.');
          if (searchCache.size >= 40) searchCache.delete(searchCache.keys().next().value);
          searchCache.set(cacheKey, {at:Date.now(), result});
        }
        if (version !== peopleVersion || selectedCommon?.codigo !== commonCode) return;
        const buttons = result.people.map((item, index) => {
          const li = document.createElement('li'), button = document.createElement('button');
          button.type = 'button'; button.id = `ram-option-${index}`; button.setAttribute('role', 'option');
          const avatar = document.createElement('span');
          avatar.className = 'ram-avatar'; avatar.setAttribute('aria-hidden', 'true');
          avatar.textContent = item.nome.trim().charAt(0).toLocaleUpperCase('pt-BR');
          const summary = document.createElement('div'); summary.className = 'ram-person-summary';
          const fullName = document.createElement('strong'); fullName.textContent = label(item.nome);
          const role = document.createElement('small'); role.textContent = [item.cargo || 'Cargo Musical',item.comum,item.municipio].filter(Boolean).join(' · ');
          summary.append(fullName, role); button.append(avatar, summary);
          button.classList.toggle('active', index === 0);
          button.addEventListener('focus', () => {
            $('ram-people-list').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
          });
          button.addEventListener('click', () => {person = item; name.value = label(item.nome); hideResults(); $('ram-name-help').textContent = [item.cargo,item.comum,item.municipio && item.municipio !== city.value ? 'Origem: '+label(item.municipio)+' · Fora do Município' : ''].filter(Boolean).join(' · '); showEvent(); reasonType.focus();});
          li.append(button); return li;
        });
        $('ram-people-list').replaceChildren(...buttons);
        $('ram-results').hidden = !buttons.length;
        name.setAttribute('aria-expanded', String(!!buttons.length));
        $('ram-name-help').textContent = buttons.length ? 'Selecione seu nome na lista.' : 'Nenhum nome ativo com cargo musical encontrado. Confira a comum ou solicite a atualização do cadastro à secretaria.';
      } catch (error) {
        if ((timedOut || error.name !== 'AbortError') && version === peopleVersion) {
          $('ram-name-help').textContent = 'Não foi possível pesquisar. Digite novamente para tentar.';
          feedback(timedOut ? 'A pesquisa demorou mais que o esperado. Digite novamente para tentar.' : error.message);
        }
      } finally {clearTimeout(deadline);}
    }, cached && Date.now() - cached.at < 45000 ? 0 : 180);
  });
  name.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideResults();
    if (e.key === 'ArrowDown' && !$('ram-results').hidden) {e.preventDefault(); $('ram-people-list').querySelector('button')?.focus();}
  });
  $('ram-people-list').addEventListener('keydown', e => {
    const buttons = [...$('ram-people-list').querySelectorAll('button')], index = buttons.indexOf(document.activeElement);
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) {e.preventDefault(); buttons[(index + (e.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length]?.focus();}
    if (e.key === 'Escape') {hideResults(); name.focus();}
  });
  document.addEventListener('click', e => {if (e.target !== name && !$('ram-results').contains(e.target)) hideResults();});
  document.addEventListener('visibilitychange', () => {if (!document.hidden) ready();});
  $('ram-form').addEventListener('submit', async e => {
    e.preventDefault();
    ready();
    if (submit.disabled || saving) return;
    const payload = {evento:eventSelect.value, evento_municipio:city.value, comum:selectedCommon.codigo, pessoa:person.token, motivo:reasonType.value};
    if (reasonType.value === 'Outros') payload.detalhe = reason.value.trim();
    saving = true;
    closeCities();
    $('ram-fields').disabled = true;
    submit.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i>Enviando justificativa…';
    ready();
    try {
      const response = await fetch('/justificativas/api/', {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify(payload)});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Não foi possível enviar a justificativa.');
      $('ram-receipt-name').textContent = label(person.nome || name.value);
      $('ram-receipt-event').textContent = `${result.evento}, em ${formatDate(result.data)}`;
      $('ram-receipt-common').textContent = label(selectedCommon.nome.replace(/^BR-\d+-\d+\s*-?\s*/i,''));
      $('ram-receipt-city').textContent = label(selectedCommon.municipio);
      $('ram-form').hidden = true;
      $('ram-success').hidden = false;
      $('ram-success-title').focus({preventScroll:true});
      document.querySelector('.ram-page').scrollTop = 0;
      reason.value = '';
      reasonType.value = '';
      reasonType.dispatchEvent(new Event('change'));
      clearPerson();
    } catch (error) {feedback(error.message);}
    finally {saving = false; $('ram-fields').disabled = false; submit.innerHTML = '<i class="fa fa-circle-check" aria-hidden="true"></i>Enviar justificativa'; showEvent();}
  });
  $('ram-another').addEventListener('click', () => {
    $('ram-success').hidden = true;
    $('ram-form').hidden = false;
    clearPerson();
    name.focus();
  });
  async function load() {
    $('ram-retry').hidden = true;
    $('ram-status').textContent = 'Carregando municípios e agenda musical…';
    try {
      const response = await fetch('/justificativas/api/');
      data = await response.json();
      if (!response.ok) throw Error(data.error || 'Não foi possível carregar a agenda.');
      const cities = [...new Set(data.commons.map(c => c.municipio))].sort((a,b) => a.localeCompare(b, 'pt-BR'));
      city.replaceChildren(option('', 'Selecione o município'), ...cities.map(c => option(c, label(c))));
      syncCity();
      $('ram-fields').disabled = false;
      $('ram-status').textContent = 'Encontre seu evento e registre o motivo da sua ausência.';
    } catch (error) {$('ram-status').textContent = 'A agenda não pôde ser carregada. Tente novamente.'; $('ram-retry').hidden = false; feedback(error.message);}
  }
  $('ram-retry').addEventListener('click', load);
  load();
})();
