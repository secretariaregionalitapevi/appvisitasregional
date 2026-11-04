"""Captura integral das listagens Membros e Alunos, com paginação verificada."""
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from .sam_catalog import clean_html, norm


def normalize_page(payload, headers, kind):
    positions = {norm(h): i for i, h in enumerate(headers)}
    def column(*names):
        return next((positions[norm(n)] for n in names if norm(n) in positions), None)
    fields = [column('Nome', 'Aluno'), column('Comum Congregação', 'Comum'),
              column('Cargo/Ministério', 'Cargo / Ministério', 'Ministério'), column('Instrumento'), column('Nível')]
    if any(index is None for index in fields):
        raise ValueError(f'Colunas desconhecidas na listagem {kind}: {headers}')
    result = []
    for raw in payload.get('data', payload.get('aaData', [])):
        if not isinstance(raw, list) or len(raw) <= max(fields):
            raise ValueError(f'Linha inválida na listagem {kind}')
        identity = clean_html(raw[0])
        if not identity:
            control = BeautifulSoup(str(raw[0]), 'html.parser').select_one('input[value]')
            identity = control.get('value') if control else None
        if not identity or not str(identity).isdigit() or not clean_html(raw[fields[0]]):
            raise ValueError(f'Identidade ausente na listagem {kind}')
        values = [str(raw[i] or '') for i in fields]
        values[0] = re.sub(r'\s*\(compartilhado\)\s*$', '', clean_html(values[0]), flags=re.I)
        result.append({'cells': [str(identity), *values],
                       'source_kind': kind, 'history_available': kind == 'students'})
    return result


def fetch_listing(session, path, kind, page_size=500):
    base = session.module.config.SITE_URL.rstrip('/') + '/'
    page = session.scraper.page
    document = page.evaluate("""async url => {
        const r = await fetch(url,{credentials:'same-origin'});
        if(!r.ok) throw new Error(`Catálogo HTTP ${r.status}`);
        return await r.text();
    }""", urljoin(base, path))
    soup = BeautifulSoup(document, 'html.parser')
    headers = [th.get_text(' ', strip=True) for th in soup.select('#table-grp thead th')]
    script = '\n'.join(s.get_text() for s in soup.find_all('script'))
    ajax = re.search(r'ajax\s*:\s*\{\s*url\s*:\s*[\"\']([^\"\']+)[\"\']\s*,\s*type\s*:\s*[\"\'](GET|POST)[\"\']', script, re.I)
    if not ajax or not headers:
        raise ValueError(f'Endpoint da listagem {kind} não identificado; nenhuma escrita autorizada.')
    endpoint, method = urljoin(base, ajax[1]), ajax[2].upper()
    if urlsplit(endpoint).netloc != urlsplit(base).netloc:
        raise ValueError('Endpoint SAM fora da origem autenticada')
    rows, seen, expected, extent, start, received, previous = [], {}, None, None, 0, 0, None
    def request(offset, length):
        return page.evaluate("""async ({url,method,start,length,columns}) => {
                    const form=new URLSearchParams({draw:String(start+1),start:String(start),length:String(length),
                        'search[value]':'','search[regex]':'false','order[0][column]':'0','order[0][dir]':'asc'});
                    for(let i=0;i<columns;i++) {
                        form.set(`columns[${i}][data]`,String(i));form.set(`columns[${i}][name]`,'');
                        form.set(`columns[${i}][searchable]`,i?'true':'false');
                        form.set(`columns[${i}][orderable]`,i?'true':'false');
                        form.set(`columns[${i}][search][value]`,'');form.set(`columns[${i}][search][regex]`,'false');
                    }
                    const options={method,credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}};
                    if(method==='POST'){options.body=form;options.headers['Content-Type']='application/x-www-form-urlencoded; charset=UTF-8';}
                    else url+=(url.includes('?')?'&':'?')+form.toString();
                    const response=await fetch(url,options);
                    if(!response.ok) throw new Error(`Catálogo HTTP ${response.status}`);
                    return await response.json();
                }""", {'url': endpoint, 'method': method, 'start': offset, 'length': length, 'columns': len(headers)})
    while extent is None or start < extent:
        payload = request(start, page_size)
        total = int(payload.get('recordsTotal', payload.get('iTotalRecords', -1)))
        filtered = int(payload.get('recordsFiltered', payload.get('iTotalDisplayRecords', total)))
        # Os dois endpoints usam contadores diferentes para seus recortes.
        # Conferir as identidades retornadas e confirmar por censo independente
        # qualquer divergência entre contadores e conteúdo.
        declared = total if kind == 'students' else filtered
        if total < 1 or filtered < 1 or expected is not None and (expected != declared or extent != filtered):
            raise ValueError(f'Catálogo {kind} incompleto ou alterado: total={total}, recorte={filtered}, esperado={expected}')
        expected, extent = declared, filtered
        batch = normalize_page(payload, headers, kind)
        if not batch and len(rows) == expected:
            break
        signature = [r['cells'] for r in batch]
        if not batch or signature == previous:
            raise ValueError(f'Paginação interrompida ou repetida em {kind}: {start}/{expected}')
        previous = signature
        for row in batch:
            old = seen.get(row['cells'][0])
            if old and (kind == 'members' or norm(old['cells'][1]) != norm(row['cells'][1])):
                raise ValueError(f'Identidade repetida ou conflitante em {kind}: {row["cells"][0]} ({old["cells"][1]!r} / {row["cells"][1]!r})')
            if not old:
                rows.append(row)
                seen[row['cells'][0]] = row
        received += len(batch)
        # Alunos devolve menos linhas que o tamanho solicitado mesmo havendo
        # outras páginas. O offset segue o tamanho solicitado nessa listagem.
        start += page_size if kind == 'students' else len(batch)
    discrepancy = len(rows) != expected
    # Os contadores do SAM podem estar desatualizados. Nessa situação,
    # uma segunda leitura integral independente deve confirmar exatamente
    # todas as identidades obtidas pela paginação antes de permitir escrita.
    if discrepancy:
        if max(total, filtered) > 10000:
            raise ValueError(f'Contadores divergentes em {kind}; captura não homologada')
        census = normalize_page(request(0, 10000), headers, kind)
        census_ids = {(r['cells'][0], norm(r['cells'][1])) for r in census}
        captured_ids = {(r['cells'][0], norm(r['cells'][1])) for r in rows}
        if census_ids != captured_ids:
            raise ValueError(f'Captura paginada e integral divergem em {kind}')
    return {'rows': rows, 'total': len(rows), 'source_rows': received, 'declared_total': expected,
            'counter_discrepancy': discrepancy, 'kind': kind}



def full_catalog(session):
    students = fetch_listing(session, 'alunos', 'students')
    members = fetch_listing(session, 'grp_musical', 'members')
    merged = {r['cells'][0]: r for r in students['rows']}
    for row in members['rows']:
        old = merged.get(row['cells'][0])
        if old and norm(old['cells'][1]) != norm(row['cells'][1]):
            raise ValueError('Identificador SAM associado a nomes distintos entre Membros e Alunos')
        # Membros é a origem do cargo/comum atual. Alunos conserva a indicação
        # de histórico pedagógico e o município apenas quando a comum concorda.
        if old:
            row = {**row, 'history_available': True}
            if norm(clean_html(old['cells'][2]).split('|')[0]) == norm(clean_html(row['cells'][2]).split('|')[0]):
                row['cells'][2] = old['cells'][2]
        merged[row['cells'][0]] = row
    return {'rows': list(merged.values()), 'total': len(merged), 'complete': True,
            'coverage': {'students': students['total'], 'members': members['total'],
                         'students_source_rows': students.get('source_rows'),
                         'students_declared_total': students.get('declared_total'),
                         'students_counter_discrepancy': students.get('counter_discrepancy', False)}}
