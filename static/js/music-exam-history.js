(function (root) {
  'use strict';
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/\s+/g, ' ').trim();
  const administrations = ['ITAPEVI', 'JANDIRA', 'COTIA / CAUCAIA / VGP', 'SANTANA / PIRAPORA', 'OUTRAS ADMINISTRAÇÕES'];
  function administration(city) {
    const value = normalize(city);
    if (/COTIA|CAUCAIA|VARGEM GRANDE|VGP/.test(value)) return administrations[2];
    if (/SANTANA|PIRAPORA|FAZENDINHA/.test(value)) return administrations[3];
    if (value.includes('JANDIRA')) return administrations[1];
    if (value.includes('ITAPEVI')) return administrations[0];
    return administrations[4];
  }
  function category(row) {
    return normalize(row.categoria).includes('ORGANISTA') || ['ORGAO', 'ORGANISTA'].includes(normalize(row.instrumento)) ? 'Organistas' : 'Músicos';
  }
  function resultLabel(value, row = {}) {
    if (normalize(value) === 'APROVADO' || normalize(value) === 'APROVADA') {
      return category(row) === 'Organistas' ? 'APROVADA' : 'APROVADO';
    }
    return value || 'AGENDADO';
  }
  function stage(row) {
    const kind = normalize(row.tipo_exame);
    if (/ESPECIAL|EMERGEN/.test(kind)) return {key:'especial',label:'Exame especial',rank:3,icon:'fa-bolt',tone:'special'};
    if (/\bRJM\b/.test(kind)) return {key:'rjm',label:'RJM',rank:0,icon:'fa-music',tone:'rjm'};
    if (kind.includes('CULTO OFICIAL')) return {key:'culto',label:'Culto Oficial',rank:1,icon:'fa-users',tone:'culto'};
    if (kind.includes('OFICIALIZA')) return {key:'oficializacao',label:'Oficialização',rank:2,icon:'fa-award',tone:'oficializacao'};
    if (kind.includes('TROCA') && kind.includes('INSTRUMENT')) return {key:'troca',label:'Troca de instrumento',rank:4,icon:'fa-arrows-rotate',tone:'other'};
    return {key:'outros',label:'Outros exames',rank:5,icon:'fa-clipboard-check',tone:'other'};
  }
  function levels(rows) {
    const groups = new Map();
    rows.forEach(row => {const info=stage(row);if(!groups.has(info.key))groups.set(info.key,{...info,rows:[]});groups.get(info.key).rows.push(row)});
    return [...groups.values()].sort((a,b)=>a.rank-b.rank);
  }
  function group(rows) {
    const groups = new Map();
    rows.forEach(row => {
      const admin = administration(row.municipio), kind = category(row), day = String(row.data_exame || '').slice(0, 10);
      if (!groups.has(admin)) groups.set(admin, {label: admin, count: 0, sessions: new Map()});
      const item = groups.get(admin), key = JSON.stringify([admin, kind, day]);
      if (!item.sessions.has(key)) item.sessions.set(key, {key, administration: admin, category: kind, day, rows: [], approved: 0, types: {}});
      const session = item.sessions.get(key);
      session.rows.push(row);
      session.approved += normalize(row.resultado) === 'APROVADO' ? 1 : 0;
      session.types[row.tipo_exame || 'Não informado'] = (session.types[row.tipo_exame || 'Não informado'] || 0) + 1;
      item.count++;
    });
    return [...groups.values()].sort((a, b) => administrations.indexOf(a.label) - administrations.indexOf(b.label)).map(item => ({
      ...item,
      sessions: [...item.sessions.values()].sort((a, b) => a.category.localeCompare(b.category, 'pt-BR') || b.day.localeCompare(a.day)).map(session => ({
        ...session, rows: session.rows.sort((a, b) => stage(a).rank-stage(b).rank || String(a.nome_aluno || '').localeCompare(String(b.nome_aluno || ''), 'pt-BR'))
      }))
    }));
  }
  function page(rows, number, size = 10) {
    const pages = Math.max(1, Math.ceil(rows.length / size));
    number = Math.min(pages, Math.max(1, Number(number) || 1));
    return {rows: rows.slice((number - 1) * size, number * size), number, pages, total: rows.length};
  }
  function notes(value) {
    return String(value || '').split('\n').filter(line => !/^(Importado de:|Data confirmada pelo solicitante:|Nome anterior no cadastro:|Nome no documento:)/i.test(line.trim()) && !/^Agenda: .* \| (\d{4}-\d{2}-\d{2}|\d{2}\/\d{2}\/\d{4}) .* \| ID: [a-f0-9]+\s*$/i.test(line.trim())).join('\n').trim();
  }
  root.ExamHistory = {administration, category, resultLabel, stage, levels, group, page, notes};
})(typeof window !== 'undefined' ? window : globalThis);
