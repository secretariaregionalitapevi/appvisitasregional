"""Executar com python manage.py shell -c \"exec(open('scripts/validation/validate_music_ministry.py',encoding='utf-8').read())\"."""
from datetime import datetime
from pathlib import Path
from io import BytesIO

from pypdf import PdfReader
from openpyxl import load_workbook
import pypdfium2 as pdfium

from ColorAdminApp.modules.music_events_dashboard import REGIONAL
from ColorAdminApp.modules.music_ministry_domain import history
from ColorAdminApp.modules.music_ministry_reports import build_pdf, build_excel

people, entries = [], []
events = [dict(id='bras', titulo='Reunião do Ministério da Música', tipo='REUNIAO_MINISTERIO',
               data_evento='2026-10-06', modalidade='PRESENCIAL', local='Brás'),
          dict(id='online', titulo='Reunião do Ministério da Música - online', tipo='REUNIAO_MINISTERIO',
               data_evento='2026-11-20', modalidade='ONLINE', local='Plataforma online')]
for index, city in enumerate(REGIONAL):
    key = f'teste:{index}'
    person = dict(key=key, aliases=[key], nome=f'Pessoa de demonstração {index + 1}',
                  comum=f'BR-22-{index+1} - Comum de demonstração', municipio=city,
                  roles=['ENCARREGADO_LOCAL'], source='teste')
    people.append(person)
    for event, state in [('bras', 'SEM_REGISTRO' if index % 2 else 'PRESENTE'), ('online', 'SEM_DADOS')]:
        entries.append(dict(event_id=event, person_key=key, nome=person['nome'], comum=person['comum'],
                            municipio=city, roles=person['roles'], situacao=state, observacoes='', version=1))
output = Path('tmp/pdfs/ministerio')
output.mkdir(parents=True, exist_ok=True)
for name, cities in [('regional', []), ('municipios', ['ITAPEVI', 'PIRAPORA DO BOM JESUS'])]:
    filters = dict(ano=2026, municipios=cities, cargo='ENCARREGADO_LOCAL')
    data = history(people, events, entries, [], [], [], {'level': 'regional'}, filters)
    data['filters'] = filters
    pdf_content = build_pdf(data, 'Operador de validação', datetime(2026,11,3,17,30))
    excel_content = build_excel(data, 'Operador de validação', datetime(2026,11,3,17,30))
    (output / f'{name}.pdf').write_bytes(pdf_content)
    (output / f'{name}.xlsx').write_bytes(excel_content)
    pdf = PdfReader(BytesIO(pdf_content))
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert 'CONGREGAÇÃO CRISTÃ NO BRASIL' in text
    assert '03/11/2026 17:30' in text
    assert '06/10/2026' in text
    assert 'Sem dados' in text
    if cities:
        assert 'CAUCAIA DO ALTO' not in text
        assert data['summary']['people'] == 2
    document = pdfium.PdfDocument(pdf_content)
    for index in [0, len(document) - 1]:
        document[index].render(scale=1.5).to_pil().save(str(output / f'{name}-{index+1}.png'))
    workbook = load_workbook(BytesIO(excel_content))
    assert workbook['Resumo']['A1'].value == 'CONGREGAÇÃO CRISTÃ NO BRASIL'
    assert workbook['Resumo']['A7'].fill.fgColor.rgb == '001E4B7A'
    for sheet in workbook:
        assert sheet.page_setup.fitToWidth == 1
        assert sheet.print_title_rows == '$1:$7'
    print(f'{name}: {len(pdf.pages)} páginas, {len(data["rows"])} pessoas; PDF e Excel validados.')
