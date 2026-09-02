(() => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const flows = {
    save: {icon:'fa-floppy-disk', steps:[['fa-check','Validando dados'],['fa-floppy-disk','Salvando'],['fa-rotate','Atualizando painel']]},
    create: {icon:'fa-user-plus', steps:[['fa-check','Validando dados'],['fa-database','Cadastrando'],['fa-rotate','Atualizando painel']]},
    update: {icon:'fa-pen-to-square', steps:[['fa-check','Validando dados'],['fa-floppy-disk','Atualizando'],['fa-rotate','Atualizando painel']]},
    delete: {icon:'fa-trash-can', steps:[['fa-magnifying-glass','Localizando'],['fa-trash','Removendo'],['fa-rotate','Atualizando painel']]},
    upload: {icon:'fa-file-arrow-up', steps:[['fa-check','Validando arquivo'],['fa-cloud-arrow-up','Enviando'],['fa-rotate','Concluindo']]},
    sync: {icon:'fa-rotate', steps:[['fa-magnifying-glass','Consultando'],['fa-arrows-rotate','Sincronizando'],['fa-check','Concluindo']]}
  };
  const remove = () => document.querySelector('#app-feedback-layer')?.remove();
  const inferFlow = title => {
    const value = String(title || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (value.includes('exclu') || value.includes('remov')) return 'delete';
    if (value.includes('document') || value.includes('arquivo') || value.includes('anex')) return 'upload';
    if (value.includes('atualiz') || value.includes('edit')) return 'update';
    if (value.includes('cadastr') || value.includes('registr')) return 'create';
    if (value.includes('sincron')) return 'sync';
    return 'save';
  };
  const iconFor = (type, flow) => type === 'loading' ? flows[flow].icon : type === 'success' ? 'fa-check' : type === 'warning' ? 'fa-triangle-exclamation' : 'fa-circle-exclamation';

  function show(options = {}) {
    remove();
    const type = options.type || 'success';
    const loading = type === 'loading';
    const flow = options.flow || inferFlow(options.title);
    const config = flows[flow] || flows.save;
    const layer = document.createElement('div');
    layer.id = 'app-feedback-layer';
    layer.className = 'app-feedback-layer';
    layer.setAttribute('role', loading ? 'status' : 'dialog');
    layer.setAttribute('aria-live', 'polite');
    layer.innerHTML = `<section class="app-feedback-card ${escapeHtml(type)}"><div class="app-feedback-head"><span class="app-feedback-main-icon"><i class="fa ${iconFor(type, flow)}"></i></span><div class="app-feedback-heading"><strong>${escapeHtml(options.title || 'Operação concluída')}</strong><p>${escapeHtml(options.message || '')}</p></div>${loading ? '' : '<button class="app-feedback-close" type="button" aria-label="Fechar"><i class="fa fa-xmark"></i></button>'}</div>${loading ? `<div class="app-feedback-steps">${config.steps.map(([icon,label]) => `<div class="app-feedback-step"><span><i class="fa ${icon}"></i></span>${escapeHtml(label)}</div>`).join('')}</div>` : `<div class="app-feedback-result"><i class="fa ${type === 'success' ? 'fa-circle-check' : type === 'warning' ? 'fa-circle-info' : 'fa-circle-exclamation'}"></i><span>${escapeHtml(options.detail || (type === 'success' ? 'Operação concluída e painel atualizado.' : type === 'warning' ? 'Confira as informações antes de continuar.' : 'Revise a mensagem e tente novamente.'))}</span></div>`}</section>`;
    document.body.appendChild(layer);
    const close = () => layer.remove();
    layer.querySelector('.app-feedback-close')?.addEventListener('click', close);
    if (!loading) window.setTimeout(close, Number(options.duration || 4600));
    return {close, element:layer};
  }

  function confirm(options = {}) {
    remove();
    return new Promise(resolve => {
      const escapedMessage = escapeHtml(options.message || 'Esta aÃ§Ã£o precisa de confirmaÃ§Ã£o.');
      const escapedHighlight = escapeHtml(options.highlight || '');
      const messageHtml = escapedHighlight && escapedMessage.includes(escapedHighlight)
        ? escapedMessage.replace(escapedHighlight, `<strong class="app-feedback-highlight">${escapedHighlight}</strong>`)
        : escapedMessage;
      const layer = document.createElement('div');
      layer.id = 'app-feedback-layer';
      layer.className = 'app-feedback-layer';
      layer.setAttribute('role', 'dialog');
      layer.setAttribute('aria-modal', 'true');
      layer.innerHTML = `<section class="app-feedback-card warning"><div class="app-feedback-head"><span class="app-feedback-main-icon"><i class="fa ${escapeHtml(options.icon || 'fa-triangle-exclamation')}"></i></span><div class="app-feedback-heading"><strong>${escapeHtml(options.title || 'Confirmar operação?')}</strong><p>${messageHtml}</p></div><button class="app-feedback-close" type="button" data-result="false" aria-label="Fechar"><i class="fa fa-xmark"></i></button></div><div class="app-feedback-result"><i class="fa fa-circle-info"></i><span>${escapeHtml(options.detail || 'Confirme a ação para continuar.')}</span></div><div class="app-feedback-actions"><button class="btn btn-light" type="button" data-result="false"><i class="fa fa-xmark me-1"></i>${escapeHtml(options.cancelText || 'Cancelar')}</button><button class="btn btn-danger" type="button" data-result="true"><i class="fa ${escapeHtml(options.confirmIcon || 'fa-trash')} me-1"></i>${escapeHtml(options.confirmText || 'Sim, excluir')}</button></div></section>`;
      document.body.appendChild(layer);
      let finished = false;
      const finish = value => { if (finished) return; finished = true; document.removeEventListener('keydown', onKey); layer.remove(); resolve(value); };
      const onKey = event => { if (event.key === 'Escape') finish(false); };
      layer.querySelectorAll('[data-result]').forEach(button => button.addEventListener('click', () => finish(button.dataset.result === 'true')));
      layer.addEventListener('click', event => { if (event.target === layer) finish(false); });
      document.addEventListener('keydown', onKey);
      layer.querySelector('[data-result="true"]')?.focus();
    });
  }

  window.AppFeedback = {show, confirm, close:remove};
})();