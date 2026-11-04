from datetime import datetime
from io import BytesIO
from unittest.mock import patch
import json

from django.test import RequestFactory, SimpleTestCase
from django.core.cache import cache
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules import music_ministry as api
from ColorAdminApp.modules.music_ministry_domain import (roster, history, event_payload, parse_meeting,
                                                        match_person, include_directory, person_matcher, attendance_summary)
from ColorAdminApp.modules.music_ministry_reports import build_pdf, build_excel


def fixture():
    catalog = [{'comum': 'BR-22-1 - Central', 'cidade': 'ITAPEVI'},
               {'comum': 'BR-22-2 - Vila', 'cidade': 'COTIA'}]
    registry = [{'id': '1', 'nome_aluno': 'José Silva', 'comum_congregacao': catalog[0]['comum'],
                 'municipio': 'ITAPEVI', 'cargo_ministerio': 'Encarregado Local', 'instrumento': 'VIOLINO', 'status': 'ATIVO'},
                {'id': '2', 'nome_aluno': 'Maria Souza', 'comum_congregacao': catalog[1]['comum'],
                 'municipio': 'COTIA', 'cargo_ministerio': 'Examinadora', 'instrumento': 'ORGAO', 'status': 'ATIVO'}]
    members = [{'id': 'member', 'nome': 'José Silva', 'comum': catalog[0]['comum'], 'cidade': 'ITAPEVI',
                'cargo_outros': 'Encarregado Local', 'status': 'ATIVO'}]
    return catalog, registry, members


def raw_event(**extra):
    return {'titulo': 'Reunião do Ministério da Música', 'tipo': 'REUNIAO_MINISTERIO', 'data_evento': '2026-10-06',
            'modalidade': 'PRESENCIAL', 'local': 'Brás', 'familia': 'GERAL',
            'municipios': ['ITAPEVI', 'COTIA'], 'cargos': ['ENCARREGADO_LOCAL', 'EXAMINADORA'], **extra}


def source_data():
    catalog, registry, members = fixture()
    return {'catalog': catalog, 'registry': registry, 'members': members, 'directory': [],
            'events': [], 'entries': [], 'legacy_events': [], 'legacy_records': [], 'legacy_reviews': [], 'available': True}


class MinistryDomainTests(SimpleTestCase):
    def setUp(self):
        self.catalog, self.registry, self.members = fixture()
        self.people = roster(self.registry, self.members, self.catalog)

    def test_common_with_two_leaders_counts_once_and_preserves_both_people(self):
        rows = [dict(municipio='ITAPEVI', comum='BR-22-1 - Central', present=3, verified=4, pending=0),
                dict(municipio='ITAPEVI', comum='BR-22-1 - Central', present=0, verified=4, pending=0),
                dict(municipio='ITAPEVI', comum='BR-22-2 - Vila', present=0, verified=2, pending=1),
                dict(municipio='COTIA', comum='BR-22-3 - Centro', present=0, verified=4, pending=0)]
        result = attendance_summary(rows)
        self.assertEqual(result['commons'], 3)
        self.assertEqual(result['people'], 4)
        self.assertEqual(result['people_present'], 1)
        self.assertEqual(result['without_presence'], 3)
        self.assertEqual(result['present'], 3)
        self.assertEqual(result['commons_present'], 1)
        self.assertEqual(result['commons_without_presence'], 1)
        self.assertEqual(result['commons_pending'], 1)
        self.assertEqual(sum(result[k] for k in ['commons_present', 'commons_without_presence', 'commons_pending']), result['commons'])

    def test_two_sources_share_one_identity_with_aliases(self):
        self.assertEqual(len(self.people), 2)
        person = next(p for p in self.people if p['nome'] == 'José Silva')
        self.assertEqual(set(person['aliases']), {'sam:1', 'irmandade:member'})
        self.assertEqual(person['families'], ['CORDAS'])

    def test_homonyms_with_two_ids_in_same_source_are_not_merged(self):
        duplicated = [*self.registry, dict(self.registry[0], id='other')]
        people = roster(duplicated, self.members, self.catalog)
        matches = match_person({'nome': 'José Silva', 'comum': self.catalog[0]['comum']}, people)
        self.assertEqual(len(matches), 3)
        self.assertEqual(len(match_person({'sam_pessoa_id': 'other'}, people)), 1)

    def test_indexed_matcher_preserves_homonyms_and_stable_ids(self):
        people = roster([*self.registry, dict(self.registry[0], id='other')], self.members, self.catalog)
        match = person_matcher(people)
        self.assertEqual(len(match({'nome': 'José Silva', 'comum': self.catalog[0]['comum']})), 3)
        self.assertEqual(match({'sam_pessoa_id': 'other'})[0]['key'], 'sam:other')
        self.assertEqual(match({'nome': 'Inexistente', 'comum': self.catalog[0]['comum']}), [])

    def test_planned_event_does_not_create_absences(self):
        result = event_payload(raw_event(), self.people)
        self.assertTrue(all(r['situacao'] == 'SEM_DADOS' for r in result['registros']))

    def test_registered_local_leader_missing_from_import_is_absent(self):
        maria = next(p for p in self.people if p['nome'] == 'Maria Souza')
        source = {'row': 5, 'nome': maria['nome'], 'comum': maria['comum'], 'municipio': maria['municipio'],
                  'roles': maria['roles'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        result = event_payload(raw_event(lista_completa=False), self.people, [source], [{'row': 5, 'key': maria['key']}])
        self.assertEqual(next(r for r in result['registros'] if r['nome'] == 'José Silva')['situacao'], 'SEM_REGISTRO')

    def test_annual_absence_filter_does_not_turn_occasional_absence_into_zero_presence(self):
        events = [dict(id='jan', titulo='January', tipo='ENSAIO_REGIONAL', data_evento='2026-01-18'),
                  dict(id='may', titulo='May', tipo='ENSAIO_REGIONAL', data_evento='2026-05-17')]
        people = roster([*self.registry, dict(self.registry[0], id='second', nome_aluno='Outro encarregado')], self.members, self.catalog)
        records = [dict(evento_id='jan', sam_pessoa_id='1', nome='Present', comum_codigo='BR-22-1', situacao='PRESENTE'),
                   dict(evento_id='may', nome='Unknown', comum_codigo='BR-22-1', situacao='PRESENTE')]
        args = (people, [], [], events, records, self.catalog, {'level': 'regional'})
        annual = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'})
        absent = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'situacao': 'SEM_REGISTRO'})
        self.assertEqual(absent['summary'], annual['summary'])
        self.assertEqual(absent['summary']['people'], 2)
        self.assertEqual(absent['summary']['people_present'], 1)
        self.assertEqual(absent['summary']['without_presence'], 1)
        self.assertEqual([p['key'] for p in absent['rows']], ['sam:second'])
        may = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'evento': 'legado:may', 'situacao': 'SEM_REGISTRO'})
        self.assertEqual(len(may['rows']), 2)
        self.assertEqual(may['summary']['without_presence'], 2)

    def test_loaded_legacy_list_marks_missing_registered_local_leader_absent(self):
        event = {'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'}
        records = [{'evento_id': 'jan', 'nome': 'Outro participante', 'comum_codigo': 'BR-22-1', 'situacao': 'PRESENTE'}]
        result = history(self.people, [], [], [event], records, self.catalog, {'level': 'regional'}, {'ano': 2026})
        jose = next(r for r in result['rows'] if r['nome'] == 'José Silva')
        self.assertEqual(jose['cells'][0]['situacao'], 'SEM_REGISTRO')
        self.assertEqual((jose['present'], jose['verified']), (0, 1))

    def test_legacy_attendance_is_individual_and_missing_stays_pending(self):
        events = [{'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'},
                  {'id': 'may', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-05-17'}]
        records = [{'evento_id': 'jan', 'sam_pessoa_id': '1', 'nome': 'José Silva',
                    'comum_codigo': 'BR-22-1', 'cargo': 'Encarregado Local', 'situacao': 'PRESENTE'}]
        result = history(self.people, [], [], events, records, self.catalog, {'level': 'regional'}, {'ano': 2026})
        jose = next(r for r in result['rows'] if r['nome'] == 'José Silva')
        self.assertEqual((jose['present'], jose['verified'], jose['pending']), (1, 1, 1))
        maria = next(r for r in result['rows'] if r['nome'] == 'Maria Souza')
        self.assertEqual(maria['cells'], [])

    def test_manual_legacy_review_counts_absence_without_overwriting_nominal_presence(self):
        event = {'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'}
        key = next(p['key'] for p in self.people if p['nome'] == 'José Silva')
        review = dict(event_id='jan', person_key=key, nome='José Silva', comum=self.catalog[0]['comum'],
                      municipio='ITAPEVI', roles=['ENCARREGADO_LOCAL'], situacao='SEM_REGISTRO', observacoes='Conferido', version=1)
        result = history(self.people, [], [], [event], [], self.catalog, {'level': 'regional'}, {'ano': 2026}, [review])
        row = next(p for p in result['rows'] if p['key'] == key)
        self.assertEqual((row['present'], row['verified']), (0, 1))

    def test_scope_and_city_filters_apply_before_summaries(self):
        result = history(self.people, [], [], [], [], self.catalog,
                         {'level': 'municipal', 'municipio': 'ITAPEVI'}, {'ano': 2026, 'municipios': ['COTIA']})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['summary']['people'], 0)
        self.assertEqual(result['options']['cities'], ['ITAPEVI'])

    def test_complete_list_and_pending_identity_have_different_denominators(self):
        people = self.people
        source = {'row': 5, 'nome': 'José Silva', 'comum': self.catalog[0]['comum'], 'municipio': 'ITAPEVI',
                  'roles': ['ENCARREGADO_LOCAL'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        key = match_person(source, people)[0]['key']
        result = event_payload(raw_event(lista_completa=True), people, [source], [{'row': 5, 'key': key}])
        self.assertEqual({r['nome']: r['situacao'] for r in result['registros']},
                         {'José Silva': 'PRESENTE', 'Maria Souza': 'SEM_REGISTRO'})
        with self.assertRaises(ValueError):
            event_payload(raw_event(), people, [source], [{'row': 5, 'key': 'sam:2'}])

    def test_rt_family_never_creates_absence_for_another_family(self):
        source = {'row': 5, 'nome': 'José Silva', 'comum': self.catalog[0]['comum'], 'municipio': 'ITAPEVI',
                  'roles': ['ENCARREGADO_LOCAL'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        key = match_person(source, self.people)[0]['key']
        result = event_payload(raw_event(tipo='REUNIAO_TECNICA', familia='CORDAS', lista_completa=True),
                               self.people, [source], [{'row': 5, 'key': key}])
        self.assertEqual(len(result['registros']), 1)

    def test_import_identity_can_be_used_in_following_year(self):
        directory = [{'person_key': 'importado:stable', 'nome': 'Outra pessoa', 'comum': self.catalog[0]['comum'],
                      'municipio': 'ITAPEVI', 'roles': ['ENCARREGADO_LOCAL']}]
        people = include_directory(self.people, directory)
        matches = match_person({'nome': 'Outra pessoa', 'comum': self.catalog[0]['comum']}, people)
        self.assertEqual(matches[0]['key'], 'importado:stable')

    def test_confirmed_alias_uses_registry_name_and_counts_presence_once(self):
        canonical = next(p for p in self.people if p['nome'] == 'José Silva')
        old = {'event_id': 'bras', 'person_key': 'importado:old', 'nome': 'José da Silva',
               'comum': canonical['comum'], 'municipio': canonical['municipio'], 'roles': canonical['roles'],
               'situacao': 'NAO_APLICA', 'observacoes': '', 'source': {'canonical_person_key': canonical['key']}}
        current = {**old, 'person_key': canonical['key'], 'nome': canonical['nome'], 'situacao': 'PRESENTE', 'source': {}}
        directory = [{'person_key': 'importado:old', 'nome': old['nome'], 'comum': old['comum'],
                      'municipio': old['municipio'], 'roles': []}]
        people = include_directory(self.people, directory, [old])
        self.assertEqual(match_person({'nome': old['nome'], 'comum': old['comum']}, people)[0]['key'], canonical['key'])
        event = dict(id='bras', titulo='Reunião no Brás', tipo='REUNIAO_MINISTERIO', data_evento='2026-10-06',
                     local='Brás', modalidade='PRESENCIAL')
        result = history(people, [event], [old, current], [], [], self.catalog, {'level': 'regional'},
                         {'ano': 2026, 'evento': 'bras', 'situacao': 'PRESENTE'})
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['nome'], 'José Silva')
        self.assertEqual(result['rows'][0]['present'], 1)
        self.assertNotIn('importado:old', [p['key'] for p in result['rows']])

    def workbook(self, formula=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['REUNIÃO DE 06/10/2026'])
        sheet.append(['Nome', 'Ministério/Cargo', 'Localidade', 'Cidade', 'Presença'])
        sheet.append(['=1+1' if formula else 'José Silva', 'Encarregado Local', 'BR-22-1 - Central', 'ITAPEVI', 'Sim'])
        stream = BytesIO()
        workbook.save(stream)
        return stream.getvalue()

    def test_parser_reads_header_date_and_canonical_common(self):
        result = parse_meeting(self.workbook(), self.catalog)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['suggested_date'], '2026-10-06')
        self.assertTrue(result['records'][0]['common_resolved'])

    def test_parser_rejects_formula_cells(self):
        with self.assertRaisesRegex(ValueError, 'fórmulas'):
            parse_meeting(self.workbook(True), self.catalog)


class MinistryApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def request(self, url='/', data=None):
        request = self.factory.get(url, data or {})
        request.session = {'authenticated': True, 'user_id': 'operator',
                           'user_profile': {'full_name': 'Operador', 'role_id': 1}}
        return request

    @patch.object(api.music_events, '_allowed', return_value=False)
    def test_read_and_export_require_authorization(self, _):
        self.assertEqual(api.api_dashboard(self.request()).status_code, 403)
        self.assertEqual(api.export(self.request(), 'pdf').status_code, 403)

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, 'user_scope', return_value={'level': 'local', 'comum': 'BR-22-1 - Central', 'municipio': 'ITAPEVI'})
    def test_local_user_cannot_write(self, *_):
        request = self.factory.post('/', '{}', content_type='application/json')
        request.session = self.request().session
        self.assertEqual(api.api_manage(request, 'salvar').status_code, 403)

    @patch.object(api, '_sources', return_value=source_data())
    def test_filters_are_shared_with_exports(self, _):
        data = api.dashboard_data(self.request(data={'municipio': ['COTIA'], 'cargo': ''}))
        self.assertEqual(data['selected_cities'], ['COTIA'])
        self.assertEqual(data['summary']['people'], 1)
        pdf = PdfReader(BytesIO(build_pdf(data, 'Teste', datetime(2026,11,3,12,30))))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)
        self.assertIn('Maria Souza', text)
        self.assertNotIn('José Silva', text)
        self.assertIn('03/11/2026 12:30', text)
        excel = load_workbook(BytesIO(build_excel(data, 'Teste', datetime(2026,11,3,12,30))))
        self.assertEqual(excel['Resumo']['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(excel['Resumo']['B8'].value, 'Maria Souza')
        self.assertEqual(excel['Resumo'].freeze_panes, 'A8')
        for sheet in excel:
            self.assertFalse(sheet.sheet_view.showGridLines)
            self.assertEqual(sheet.page_setup.fitToWidth, 1)
            self.assertEqual(sheet['A7'].fill.fgColor.rgb, '001E4B7A')

    @patch.object(api, '_sources', return_value=source_data())
    def test_page_renders_export_toolbar(self, _):
        with patch.object(api.music_events, '_allowed', return_value=True):
            response = api.page(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ministry-pdf', response.content)
        self.assertIn(b'ministry-city', response.content)

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc', return_value={'id': 'event', 'existing': False})
    def test_planned_meeting_is_saved_with_no_data_states(self, rpc, *_):
        raw = raw_event(conferido=True)
        request = self.factory.post('/', json.dumps(raw), content_type='application/json')
        request.session = self.request().session
        response = api.api_manage(request, 'salvar')
        self.assertEqual(response.status_code, 200)
        saved = rpc.call_args.args[1]['p_evento']
        self.assertTrue(all(row['situacao'] == 'SEM_DADOS' for row in saved['registros']))

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc')
    def test_complete_list_without_a_preview_cannot_create_absences(self, rpc, *_):
        request = self.factory.post('/', json.dumps(raw_event(conferido=True, lista_completa=True)), content_type='application/json')
        request.session = self.request().session
        response = api.api_manage(request, 'salvar')
        self.assertEqual(response.status_code, 400)
        rpc.assert_not_called()

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc')
    def test_preview_token_cannot_be_used_by_another_operator(self, rpc, *_):
        cache.set('music-ministry:preview:another:secret-token', {'records': []}, 1800)
        request = self.factory.post('/', json.dumps(raw_event(conferido=True, token='secret-token')), content_type='application/json')
        request.session = self.request().session
        self.assertEqual(api.api_manage(request, 'salvar').status_code, 400)
        rpc.assert_not_called()

    @patch.object(api.music_events, '_allowed', return_value=True)
    def test_bras_present_export_is_a_filtered_nominal_list(self, _):
        sources = source_data()
        event = dict(id='bras', titulo='Reunião do Ministério da Música', tipo='REUNIAO_MINISTERIO',
                     data_evento='2026-10-06', modalidade='PRESENCIAL', local='Brás')
        sources['events'] = [event]
        people = roster(sources['registry'], sources['members'], sources['catalog'])
        sources['entries'] = [dict(event_id='bras', person_key=p['key'], nome=p['nome'], comum=p['comum'],
            municipio=p['municipio'], roles=p['roles'], situacao='PRESENTE' if p['nome'] == 'José Silva' else 'SEM_REGISTRO',
            observacoes='', version=1) for p in people]
        request = self.request(data={'evento': 'bras', 'situacao': 'PRESENTE', 'cargo': ''})
        with patch.object(api, '_sources', return_value=sources):
            data = api.dashboard_data(request)
            pdf = api.export(request, 'pdf')
            excel = api.export(request, 'excel')
        self.assertEqual([p['nome'] for p in data['rows']], ['José Silva'])
        self.assertEqual(data['event_options'][0]['id'], 'bras')
        self.assertIn('REUNIÃO_MUSICAL_BRÁS_06_10_2026.pdf', pdf['Content-Disposition'])
        text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Lista de presentes', text)
        self.assertIn('06/10/2026', text)
        self.assertIn('José Silva', text)
        self.assertNotIn('Maria Souza', text)
        workbook = load_workbook(BytesIO(excel.content))
        self.assertEqual(workbook.sheetnames, ['Presenças'])
        self.assertEqual(workbook.active['B8'].value, 'José Silva')
        self.assertEqual(workbook.active.max_row, 8)

    @patch.object(api, '_sources', return_value=source_data())
    def test_invalid_state_filter_is_rejected(self, _):
        with self.assertRaises(ValueError):
            api.dashboard_data(self.request(data={'situacao': 'INVALIDA'}))
