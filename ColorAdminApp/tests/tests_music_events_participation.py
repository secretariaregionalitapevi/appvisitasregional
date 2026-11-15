import io
from datetime import datetime

from django.test import SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_participation import participation, participation_sheets
from ColorAdminApp.modules.music_events_registry import instrument_family
from ColorAdminApp.modules.music_events_reports import build_excel, build_pdf


def sample():
    events = [dict(id='e', titulo='Ensaio Regional - 15/11/2026', data_evento='2026-11-15',
                   tipo='ENSAIO_REGIONAL', familia='GERAL', status='ABERTO', base_id=None)]
    catalog = [dict(comum='BR-22-001 - CENTRAL', cidade='JANDIRA'),
               dict(comum='BR-22-002 - CENTRAL', cidade='COTIA')]
    people = []
    for city, common, size in [('JANDIRA', catalog[0]['comum'], 500), ('COTIA', catalog[1]['comum'], 100)]:
        for i in range(size):
            people.append(dict(id=f'{city}-{i}', nome_aluno=f'Pessoa {city} {i}', municipio=city,
                               comum_congregacao=common, status='Ativo', nivel='Candidato' if i % 2 else 'Oficializado',
                               instrumento=['VIOLINO', 'FLAUTA', 'TROMBONE'][i % 3], updated_at='2026-11-15T10:00:00'))
        for i in range(20):
            people.append(dict(id=f'{city}-o-{i}', municipio=city, comum_congregacao=common,
                               status='Alerta', nivel='Candidata', instrumento='ÓRGÃO'))
    records = [dict(id=f'p-{i}', evento_id='e', local_id='l', sam_pessoa_id=people[i]['id'],
                    nome=f'Pessoa JANDIRA {i}', municipio_informado='JANDIRA',
                    comum_informada=catalog[0]['comum'], categoria='MUSICO', situacao='PRESENTE',
                    instrumento=people[i]['instrumento'], nivel=people[i]['nivel']) for i in range(250)]
    sites = [dict(id='l', evento_id='e', nome='COTIA')]
    data = aggregate(events, records, sites, [], {'evento':'e'}, catalog)
    data['sam_participation'] = participation(data, people, records, catalog)
    return data, people, records, catalog


class SamParticipationTests(SimpleTestCase):
    def test_unassigned_locality_is_excluded_from_both_sides_and_all_groups(self):
        data, people, records, catalog = sample()
        baseline=data['sam_participation']
        for index, (instrument, level) in enumerate([
                ('TROMBONE','Oficializado'),('ÓRGÃO','Oficializada'),
                ('VIOLINO','Candidato'),('ÓRGÃO','Candidata')]):
            people.append(dict(id=f'unknown-{index}',municipio='',
                               comum_congregacao='SEM LOCALIDADE',instrumento=instrument,nivel=level))
            records.append(dict(records[0],id=f'unknown-{index}',sam_pessoa_id=f'unknown-{index}',
                                municipio_informado='',comum_informada='SEM LOCALIDADE',
                                instrumento=instrument,nivel=level))
        overview=participation(data,people,records,catalog)
        self.assertEqual(overview['rows'],baseline['rows'])
        self.assertEqual(overview['summaries'],baseline['summaries'])
        self.assertNotIn('LOCALIDADE A CONFERIR',overview['scope_cities'])

    def test_candidates_are_separate_even_with_musical_role_and_undefined_instrument(self):
        from ColorAdminApp.modules.music_sam_population import current_sam_people
        data, _, _, catalog = sample()
        states = [dict(source_key=str(i), source_common=catalog[0]['comum'],
                       source_level=level, source_instrument=instrument,
                       source_payload={'city':'JANDIRA','ministry':role})
                  for i, (role,level,instrument) in enumerate([
                      ('MUSICO','Oficializado','VIOLINO'),
                      ('INSTRUTOR','Candidato','A definir'),
                      ('ORGANISTA','Candidata','ÓRGÃO'),
                      ('INSTRUTORA','Oficializada','ÓRGÃO'),
                      ('SECRETARIO (A) DA MUSICA','Oficializado','VIOLINO')])]
        states.append(dict(states[0],source_key='removed',missing_since='2026-11-14'))
        people=current_sam_people(states,[],catalog)
        overview=participation(data,people,[],catalog)
        music=self.find(overview)
        organ=self.find(overview,'ORGANISTA')
        self.assertEqual((music['registered'],music['candidate_base']),(1,1))
        self.assertEqual((organ['registered'],organ['candidate_base']),(1,1))
        self.assertEqual(self.find(overview,'OUTROS')['candidate_base'],1)
        self.assertEqual(overview['non_musical_registry'],1)

    def find(self, overview, group='MUSICO', city='JANDIRA', event='e'):
        return next(r for r in overview['rows'] if (r['group'], r['city'], r['event_id']) == (group, city, event))

    def test_city_denominator_and_weighted_regional_percentage(self):
        data, _, _, _ = sample()
        self.assertEqual(data['totals']['MUSICO'],125)
        self.assertEqual(data['totals']['total'],250)
        self.assertEqual(data['totals']['candidatos'],125)
        overview = data['sam_participation']
        city = self.find(overview)
        self.assertEqual((city['registered'], city['present'], city['percent']), (250,125,50))
        self.assertEqual((city['candidate_base'],city['candidate_present'],city['candidate_percent']), (250,125,50))
        other = self.find(overview, city='COTIA')
        self.assertEqual((other['registered'],other['present'],other['percent']), (50,0,0))
        total = next(r for r in overview['summaries'] if r['group']=='MUSICO')
        self.assertEqual((total['registered'],total['present'],total['percent']), (300,125,41.67))
        families = [self.find(overview, group=g) for g in ['CORDAS','MADEIRAS','METAIS']]
        self.assertEqual(sum(r['registered'] for r in families),250)
        self.assertEqual(sum(r['present'] for r in families),125)
        self.assertEqual(self.find(overview, 'ORGANISTA')['registered'],0)
        self.assertEqual(self.find(overview, 'ORGANISTA')['candidate_base'],20)

    def test_filters_scope_duplicates_inactive_and_missing_instruments(self):
        data, people, records, catalog = sample()
        people += [people[0],dict(people[0],id='inactive',status='Inativo'),
                   dict(people[0],id='undefined',instrumento='A definir'),
                   dict(people[0],id='unresolved',comum_congregacao='DESCONHECIDA')]
        records += [dict(records[0],id='duplicate',local_id='elsewhere')]
        data['filters'].update(municipios=['JANDIRA'])
        overview = participation(data,people,records,catalog)
        self.assertEqual(self.find(overview)['present'],125)
        self.assertEqual(self.find(overview)['registered'],252)
        self.assertEqual(overview['undefined_instrument'],1)
        self.assertEqual(overview['unresolved_registry'],1)
        self.assertEqual({r['city'] for r in overview['rows']},{'JANDIRA'})
        data['filters'].update(local='elsewhere')
        self.assertEqual(self.find(participation(data,people,records,catalog))['present'],1)
        data['filters'].update(origem='visitantes')
        self.assertEqual(participation(data,people,records,catalog)['rows'],[])

    def test_multiple_events_missing_base_and_family_rt(self):
        data, people, records, catalog = sample()
        data['events'].append(dict(data['events'][0],id='e2',titulo='Segundo evento'))
        records += [dict(records[0],evento_id='e2')]
        overview = participation(data,people,records,catalog)
        self.assertEqual(self.find(overview,event='e2')['percent'],0.4)
        self.assertEqual(self.find(overview)['percent'],50)
        no_base = participation(data,[],records,catalog)
        self.assertIsNone(self.find(no_base)['percent'])
        self.assertTrue(self.find(no_base)['divergent'])
        data['events']=[dict(data['events'][0],tipo='REUNIAO_TECNICA',familia='METAIS')]
        self.assertEqual({r['group'] for r in participation(data,people,records,catalog)['rows']},{'METAIS'})

    def test_export_files_share_data_and_institutional_identity(self):
        data, _, _, _ = sample()
        data['report']='participacao'
        now=datetime(2026,11,15,12,30)
        tables=participation_sheets(data)
        self.assertEqual(len(tables),2)
        book=load_workbook(io.BytesIO(build_excel(data,'Usuário de teste',now)),rich_text=True)
        for sheet in book:
            self.assertEqual(sheet['A1'].value,'CONGREGAÇÃO CRISTÃ NO BRASIL')
            self.assertIn('Secretaria Regional da Música',str(sheet['A5'].value))
            self.assertIn('Impresso por:',sheet.oddFooter.right.text)
            self.assertEqual(sheet.freeze_panes,'A10')
            self.assertEqual(sheet['G10'].number_format,'0.00%')
            self.assertEqual(sheet.page_setup.fitToWidth,1)
        text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(build_pdf(data,'Usuário de teste',now))).pages)
        for label in ['CONGREGAÇÃO CRISTÃ NO BRASIL','Secretaria Regional da Música','Impresso por:',
                      '15/11/2026 12:30','JANDIRA','50.00%','Cordas','Madeiras','Metais']:
            self.assertIn(label,text)

    def test_family_classification(self):
        for instrument, expected in [('TROMBONE','METAIS'),('SAXOFONE','MADEIRAS'),
                                     ('CONTRABAIXO','CORDAS'),('ACORDEÃO','CORDAS')]:
            self.assertEqual(instrument_family(instrument),expected)
