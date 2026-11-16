from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pymupdf
from django.test import RequestFactory
from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_conductors import summarize
from ColorAdminApp.modules.music_events_reports import build_pdf

events = [{'id': 'e', 'titulo': 'Ensaio Regional - 15/11/2026', 'data_evento': '2026-11-15',
           'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL', 'status': 'ABERTO'}]
cities = ['CAUCAIA DO ALTO', 'COTIA', 'JANDIRA', 'SANTANA DE PARNAÍBA', 'VARGEM GRANDE PAULISTA']
sites = [{'id': str(i), 'evento_id': 'e', 'nome': city} for i, city in enumerate(cities)]
records = [{'evento_id': 'e', 'local_id': str(i) if i < 5 else '3', 'nome': 'Encarregado de validação',
            'comum_informada': f'BR-22-{i+1} - Comum de validação',
            'municipio_informado': city, 'cargo': 'ENCARREGADO LOCAL', 'categoria': 'MUSICO'}
           for i, city in enumerate(cities + ['ITAPEVI', 'PIRAPORA DO BOM JESUS'])]
data = aggregate(events, records, sites, [], {})
data['conductors'] = summarize(events, records, sites, [], {})
data['report'] = 'encarregados'
data['report_identity'] = {'scope': 'Global - Itapevi', 'common': 'BR-22-0673 - VILA DOUTOR CARDOSO'}
output = Path('output/pdf/amostra_presenca_encarregados.pdf')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(build_pdf(data, 'Ricardo Grangeiro', datetime.now(ZoneInfo('America/Sao_Paulo'))))
pdf = pymupdf.open(output)
text = ''.join(page.get_text() for page in pdf)
assert 'Localidades: 5' in text
assert 'Escopo:' not in text
assert 'BR-22-0673' not in text
assert 'Comuns: Todas' not in text
images = Path('tmp/pdfs')
images.mkdir(parents=True, exist_ok=True)
for index in {0, len(pdf) - 1}:
    pdf[index].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(images / f'encarregados-{index + 1}.png')
print(f'PDF validado: {len(pdf)} páginas; 5 localidades; cabeçalho simplificado.')
