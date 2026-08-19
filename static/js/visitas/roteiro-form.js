document.addEventListener('DOMContentLoaded', () => {
  const municipio = document.querySelector('#roteiro-municipio');
  const comum = document.querySelector('#roteiro-comum');
  const equipe = document.querySelector('#roteiro-equipe');
  const bairro = document.querySelector('#roteiro-bairro');
  const ajuda = document.querySelector('#roteiro-bairro-ajuda');
  const data = document.querySelector('input[name="data"]');
  const form = comum?.closest('form');
  const comuns = JSON.parse(document.querySelector('#roteiro-comuns-data')?.textContent || '[]');
  if (!municipio || !comum || !equipe || !bairro || !ajuda) return;

  const option = (value, label = value) => {
    const item = document.createElement('option'); item.value = value; item.textContent = label; return item;
  };
  const primeiroNome = (nome) => String(nome || '').trim().split(/\s+/)[0];
  const comunsDoMunicipio = () => comuns.filter((item) => item.cidade === municipio.value);
  const comumValida = () => comunsDoMunicipio().some((item) => item.comum === comum.value.trim());

  function carregarComuns(limpar = false) {
    const valorAtual = limpar ? '' : comum.value;
    comum.replaceChildren(option('', 'Pesquise ou selecione uma comum...'));
    comunsDoMunicipio().forEach((item) => comum.append(option(item.comum)));
    comum.value = comunsDoMunicipio().some((item) => item.comum === valorAtual) ? valorAtual : '';
    if (window.jQuery && jQuery.fn.select2) {
      const $comum = jQuery(comum);
      if ($comum.hasClass('select2-hidden-accessible')) $comum.select2('destroy');
      $comum.select2({
        width: '100%',
        language: 'pt-BR',
        placeholder: 'Digite o código ou nome da comum...',
        allowClear: true,
        dropdownParent: jQuery('.roteiro-comum-wrap'),
      }).on('select2:select select2:clear', comumAlterada);
    }
    equipe.replaceChildren(option('', 'Selecione primeiro a comum...')); equipe.disabled = true;
    bairro.replaceChildren(option('', 'Todos - manter sequência geral')); bairro.disabled = true;
  }

  async function carregarEquipes() {
    equipe.replaceChildren(option('', 'Carregando equipes...')); equipe.disabled = true;
    if (!comumValida()) return equipe.replaceChildren(option('', 'Selecione uma comum válida...'));
    try {
      const teamQuery = new URLSearchParams({modo:'catalogo', municipio:municipio.value, comum:comum.value});
      const response = await fetch(`/visitas/api/equipes/?${teamQuery}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Falha ao carregar equipes.');
      const ativas = payload.filter((item) => item.ativo && (item.tipo === 'REGIONAL' || item.comum === comum.value));
      equipe.replaceChildren(option('', ativas.length ? 'Selecione a equipe...' : 'Nenhuma equipe ativa cadastrada'));
      ativas.forEach((item) => {
        const integrantes = (item.integrantes || []).map(primeiroNome).filter(Boolean).join(', ');
        equipe.append(option(item.nome, integrantes ? `${item.nome} - ${integrantes}` : item.nome));
      });
      equipe.disabled = !ativas.length;
    } catch (error) { equipe.replaceChildren(option('', error.message)); }
  }

  async function carregarBairros() {
    bairro.replaceChildren(option('', 'Todos - manter sequência geral')); bairro.disabled = true;
    if (!comumValida()) { ajuda.textContent = 'Selecione uma comum válida para mapear os bairros mais próximos.'; return; }
    ajuda.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> Mapeando bairros a partir da comum...';
    try {
      const query = new URLSearchParams({ comum: comum.value }); if (data?.value) query.set('data', data.value);
      const response = await fetch(`/visitas/api/roteiro-bairros/?${query}`); const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Falha ao carregar os bairros.');
      payload.bairros.forEach((item) => {
        const distancia = item.distancia_metros == null ? 'distância não calculada' : item.distancia_metros < 1000 ? `${item.distancia_metros} m da comum` : `${(item.distancia_metros / 1000).toFixed(1).replace('.', ',')} km da comum`;
        bairro.append(option(item.nome, `${item.nome} - ${item.quantidade} casa(s) disponível(is), ${distancia}`));
      });
      bairro.disabled = false;
      ajuda.textContent = payload.bairros.length ? 'Bairros ordenados do mais próximo ao mais distante da comum.' : 'Nenhum bairro cadastrado para esta comum. A sequência geral será utilizada.';
    } catch (error) { bairro.disabled = false; ajuda.textContent = error.message; }
  }

  let debounce;
  async function comumAlterada() {
    clearTimeout(debounce); debounce = setTimeout(async () => { await Promise.all([carregarEquipes(), carregarBairros()]); }, 250);
  }
  municipio.addEventListener('change', () => carregarComuns(true));
  comum.addEventListener('change', comumAlterada);
  if (data) data.addEventListener('change', carregarBairros);
  form?.addEventListener('submit', (event) => { if (!comumValida()) { event.preventDefault(); comum.setCustomValidity('Selecione uma comum pertencente ao município informado.'); comum.reportValidity(); } else comum.setCustomValidity(''); });
  carregarComuns(false); if (comumValida()) comumAlterada();
});
